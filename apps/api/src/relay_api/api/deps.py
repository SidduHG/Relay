"""The FastAPI Depends() chain Tasks 8 and 9 deliberately deferred to
here: rbac.py's require_org/require_project need a resolved role to
check, and resolving one needs the Request object and route path
parameters, which only exist inside an actual route.
"""

import uuid
from collections.abc import AsyncIterator, Callable

from fastapi import Depends, Header, Request
from relay_api.auth.permissions import Permission
from relay_api.auth.rbac import require_org, require_project
from relay_api.auth.tenancy import (
    Identity,
    OrgContext,
    ProjectContext,
    parse_bearer_token,
    resolve_identity,
    resolve_org_context,
    resolve_project_context,
)
from relay_api.config import settings
from relay_db.models.user import User
from relay_db.unit_of_work import TenantUnitOfWork
from sqlalchemy.ext.asyncio import AsyncSession


async def get_admin_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.admin_sessions() as session:
        yield session


async def get_app_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.db_sessions() as session:
        yield session


async def get_identity(
    authorization: str | None = Header(default=None),
    admin_session: AsyncSession = Depends(get_admin_session),
) -> Identity:
    token = parse_bearer_token(authorization)
    return await resolve_identity(
        token, secret_key=settings.api_secret_key, admin_session=admin_session
    )


async def get_current_user(
    identity: Identity = Depends(get_identity),
    app_session: AsyncSession = Depends(get_app_session),
) -> User:
    """Only meaningful for a user identity — an API key has no User row
    of its own to resolve. Routes that need this (signup/login are
    exempt; they run before any identity exists) only ever sit behind
    the JWT-issued dashboard paths."""
    async with TenantUnitOfWork(app_session) as uow:
        user = await uow.users.get_by_id(identity.user_id) if identity.user_id else None
    assert user is not None  # a valid Identity(kind="user") always has a real user_id
    return user


async def get_org_context(
    org_id: uuid.UUID,
    identity: Identity = Depends(get_identity),
    app_session: AsyncSession = Depends(get_app_session),
) -> OrgContext:
    return await resolve_org_context(identity, org_id, app_session=app_session)


async def get_project_context(
    project_id: uuid.UUID,
    identity: Identity = Depends(get_identity),
    admin_session: AsyncSession = Depends(get_admin_session),
    app_session: AsyncSession = Depends(get_app_session),
) -> ProjectContext:
    return await resolve_project_context(
        identity, project_id, admin_session=admin_session, app_session=app_session
    )


def require_org_permission(
    *perms: Permission,
) -> Callable[[OrgContext], OrgContext]:
    def _check(ctx: OrgContext = Depends(get_org_context)) -> OrgContext:
        require_org(ctx.org_role, *perms)
        return ctx

    return _check


def require_project_permission(
    *perms: Permission,
) -> Callable[[ProjectContext], ProjectContext]:
    def _check(ctx: ProjectContext = Depends(get_project_context)) -> ProjectContext:
        require_project(ctx.role, *perms)
        return ctx

    return _check
