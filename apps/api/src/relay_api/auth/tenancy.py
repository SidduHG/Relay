"""Both auth doors converge here: a bearer token becomes an Identity,
and an Identity becomes a context an rbac.py check can run against.

No FastAPI Depends() wiring yet — that needs the Request object and
route path parameters, which only exist inside an actual route (Task
11). Everything here is plain, testable functions, same discipline as
jwt.py and api_keys.py: raise a plain exception, let the route layer
decide the status code.

middleware/auth.py from the plan's original file list doesn't exist as
a separate file: once "parse the header, verify, build an Identity" is
written, there's no non-trivial logic left over for it — it would be a
FastAPI dependency with a one-line body, which belongs with the rest of
Task 11's route wiring, not on its own.
"""

import uuid
from dataclasses import dataclass
from typing import Literal

from relay_db.models.project import Project
from relay_db.unit_of_work import TenantUnitOfWork
from relay_domain.enums.role import OrgRole, Role
from relay_security.secrets import API_KEY_PREFIX
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from relay_api.auth.api_keys import verify_api_key
from relay_api.auth.jwt import verify_access_token


class MissingCredentialsError(Exception):
    """No Authorization header, or not a well-formed 'Bearer <token>'."""


class TenantNotFoundError(Exception):
    """Unknown org/project, or the identity has no membership there.

    Deliberately one exception for both cases (RELAY-SPEC.md F1: another
    org's or project's resource is 404, never 403 — a 403 would confirm
    the resource exists). The route layer (Task 11) maps this to 404
    without needing to know which case it was.
    """


@dataclass(frozen=True, slots=True)
class Identity:
    kind: Literal["user", "api_key"]
    user_id: uuid.UUID | None
    api_key_id: uuid.UUID | None
    # Set only for kind="api_key". verify_api_key already resolves the
    # key's project in one call — re-deriving it later would mean a
    # second RLS-bypassing admin lookup for information already in hand.
    project_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class OrgContext:
    identity: Identity
    org_id: uuid.UUID
    org_role: OrgRole


@dataclass(frozen=True, slots=True)
class ProjectContext:
    identity: Identity
    org_id: uuid.UUID  # from project.org_id — never trusted from a client-supplied value
    project_id: uuid.UUID
    role: Role


def parse_bearer_token(header_value: str | None) -> str:
    if header_value is None:
        raise MissingCredentialsError("no Authorization header")
    scheme, _, token = header_value.partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token:
        raise MissingCredentialsError("expected 'Bearer <token>'")
    return token


async def resolve_identity(
    token: str, *, secret_key: str, admin_session: AsyncSession
) -> Identity:
    """Branches on the token's shape. Lets InvalidAccessTokenError and
    InvalidApiKeyError (jwt.py, api_keys.py) propagate as-is — the route
    layer maps either to 401, same as MissingCredentialsError above."""
    if token.startswith(API_KEY_PREFIX):
        key = await verify_api_key(admin_session, token)
        return Identity(kind="api_key", user_id=None, api_key_id=key.id, project_id=key.project_id)

    user_id = verify_access_token(token, secret_key=secret_key)
    return Identity(kind="user", user_id=user_id, api_key_id=None)


async def resolve_org_context(
    identity: Identity, org_id: uuid.UUID, *, app_session: AsyncSession
) -> OrgContext:
    """Org-level routes are dashboard-only — an API key is project-
    scoped by construction and has no org role to check."""
    if identity.kind != "user" or identity.user_id is None:
        raise TenantNotFoundError("API keys cannot access organization-level resources")

    async with TenantUnitOfWork(app_session, org_id=org_id) as uow:
        membership = await uow.org_memberships.get(identity.user_id)
    if membership is None:
        raise TenantNotFoundError(f"no membership in org {org_id}")

    return OrgContext(identity=identity, org_id=org_id, org_role=membership.role)


async def resolve_project_context(
    identity: Identity,
    project_id: uuid.UUID | None,
    *,
    admin_session: AsyncSession,
    app_session: AsyncSession,
) -> ProjectContext:
    """project_id is the URL path parameter for a user identity, and
    ignored (the key's own project wins) for an api_key identity.

    Finding the project's org_id from just its id needs the admin
    session regardless of identity kind: `projects` is RLS-scoped by
    org_id, so a project-scoped connection can't find the row before
    knowing the very org_id this lookup exists to discover — the same
    structural problem Task 4 hit with `organizations` and Task 7 hit
    with `api_keys`.
    """
    if identity.kind == "api_key":
        assert identity.project_id is not None  # guaranteed by resolve_identity
        target_project_id = identity.project_id
    else:
        if project_id is None:
            raise TenantNotFoundError("project_id is required")
        target_project_id = project_id

    project: Project | None = await admin_session.scalar(
        select(Project).where(Project.id == target_project_id)
    )
    if project is None:
        raise TenantNotFoundError(f"no project {target_project_id}")

    if identity.kind == "api_key":
        # Fixed, not looked up: an API key is the SDK's credential, and
        # the SDK's whole job — enqueue, cancel, replay — is exactly
        # Member's permission set (RELAY-SPEC.md F1). A leaked key is a
        # leaked bearer credential with no login flow behind it, so it
        # is capped at what the SDK legitimately needs, never Admin or
        # Owner power, regardless of who issued it or why.
        role = Role.MEMBER
    else:
        assert identity.user_id is not None  # guaranteed for kind="user"
        async with TenantUnitOfWork(
            app_session, org_id=project.org_id, project_id=project.id
        ) as uow:
            membership = await uow.memberships.get(identity.user_id)
        if membership is None:
            raise TenantNotFoundError(f"no membership in project {target_project_id}")
        role = membership.role

    return ProjectContext(
        identity=identity, org_id=project.org_id, project_id=project.id, role=role
    )
