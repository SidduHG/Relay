"""Proves relay_api.auth.tenancy against real Postgres. This is where
RELAY-SPEC.md F1's actual "done when" bar first gets implemented: an
identity authenticated for one org/project gets a clean 404-shaped
failure (TenantNotFoundError) on another org/project's resources,
including nested ones, and an OrgAdmin with no project membership gets
the same 404 on that project — an org role grants zero data access.
"""

import os
import uuid
from collections.abc import AsyncIterator

import pytest
from relay_api.auth.api_keys import issue_api_key
from relay_api.auth.jwt import issue_access_token
from relay_api.auth.tenancy import (
    Identity,
    TenantNotFoundError,
    resolve_identity,
    resolve_org_context,
    resolve_project_context,
)
from relay_db.connection import create_engine, create_session_factory
from relay_db.models.organization import Organization
from relay_db.unit_of_work import TenantUnitOfWork
from relay_domain.enums.role import OrgRole, Role
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

SECRET = "a" * 32


@pytest.fixture
async def app_sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    url = os.environ.get("DATABASE_URL")
    if url is None:
        pytest.skip("DATABASE_URL not set — start the stack to run this suite")
    engine = create_engine(url)
    try:
        yield create_session_factory(engine)
    except OSError as exc:
        pytest.skip(f"Postgres not reachable: {exc}")
    finally:
        await engine.dispose()


@pytest.fixture
async def admin_sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    url = os.environ.get("DATABASE_ADMIN_URL")
    if url is None:
        pytest.skip("DATABASE_ADMIN_URL not set — start the stack to run this suite")
    engine = create_engine(url)
    try:
        yield create_session_factory(engine)
    except OSError as exc:
        pytest.skip(f"Postgres not reachable: {exc}")
    finally:
        await engine.dispose()


async def _make_org_with_admin_user(
    sessions: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, uuid.UUID]:
    """Returns (org_id, user_id). The user is an OrgAdmin but holds no
    project membership anywhere yet."""
    org_id = uuid.uuid4()
    async with sessions() as session, TenantUnitOfWork(session, org_id=org_id) as uow:
        uow.session.add(Organization(id=org_id, name="t", slug=str(org_id)))
        user = await uow.users.create(email=f"{uuid.uuid4()}@x.com", password_hash="x" * 60)
        await uow.org_memberships.create(user_id=user.id, role=OrgRole.ADMIN)
    return org_id, user.id


async def _make_project(
    sessions: async_sessionmaker[AsyncSession], org_id: uuid.UUID
) -> uuid.UUID:
    async with (
        sessions() as session,
        TenantUnitOfWork(session, org_id=org_id) as uow,
    ):
        project = await uow.projects.create(name="t", slug=str(uuid.uuid4()))
    return project.id


async def _add_project_membership(
    sessions: async_sessionmaker[AsyncSession],
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    role: Role,
) -> None:
    async with (
        sessions() as session,
        TenantUnitOfWork(session, org_id=org_id, project_id=project_id) as uow,
    ):
        await uow.memberships.create(user_id=user_id, role=role)


async def test_org_context_resolves_for_a_member_and_404s_for_a_stranger(
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    org_a, user_a = await _make_org_with_admin_user(app_sessions)
    org_b, _ = await _make_org_with_admin_user(app_sessions)
    identity = Identity(kind="user", user_id=user_a, api_key_id=None)

    async with app_sessions() as session:
        ctx = await resolve_org_context(identity, org_a, app_session=session)
    assert ctx.org_role == OrgRole.ADMIN

    async with app_sessions() as session:
        with pytest.raises(TenantNotFoundError):
            await resolve_org_context(identity, org_b, app_session=session)


async def test_project_context_resolves_for_a_member_and_404s_across_projects(
    app_sessions: async_sessionmaker[AsyncSession],
    admin_sessions: async_sessionmaker[AsyncSession],
) -> None:
    """The spec's literal bar: authenticated as project A, every
    project-B resource is 404 — proved here at the layer that decides
    whether a request even resolves to a tenant at all."""
    org_a, user_a = await _make_org_with_admin_user(app_sessions)
    proj_a = await _make_project(app_sessions, org_a)
    await _add_project_membership(app_sessions, org_a, proj_a, user_a, Role.OWNER)

    org_b, _ = await _make_org_with_admin_user(app_sessions)
    proj_b = await _make_project(app_sessions, org_b)

    identity = Identity(kind="user", user_id=user_a, api_key_id=None)

    async with admin_sessions() as admin_s, app_sessions() as app_s:
        ctx = await resolve_project_context(
            identity, proj_a, admin_session=admin_s, app_session=app_s
        )
    assert ctx.role == Role.OWNER
    assert ctx.org_id == org_a

    async with admin_sessions() as admin_s, app_sessions() as app_s:
        with pytest.raises(TenantNotFoundError):
            await resolve_project_context(
                identity, proj_b, admin_session=admin_s, app_session=app_s
            )


async def test_org_admin_with_no_project_membership_gets_404(
    app_sessions: async_sessionmaker[AsyncSession],
    admin_sessions: async_sessionmaker[AsyncSession],
) -> None:
    """The spec's third bar: an org role grants zero data access. An
    OrgAdmin of the project's own org, with no project membership row,
    is denied exactly like a total stranger would be."""
    org_id, admin_user_id = await _make_org_with_admin_user(app_sessions)
    project_id = await _make_project(app_sessions, org_id)
    # deliberately no membership created for admin_user_id in this project

    identity = Identity(kind="user", user_id=admin_user_id, api_key_id=None)

    async with admin_sessions() as admin_s, app_sessions() as app_s:
        with pytest.raises(TenantNotFoundError):
            await resolve_project_context(
                identity, project_id, admin_session=admin_s, app_session=app_s
            )


async def test_unknown_project_id_is_404_not_a_crash(
    app_sessions: async_sessionmaker[AsyncSession],
    admin_sessions: async_sessionmaker[AsyncSession],
) -> None:
    _, user_id = await _make_org_with_admin_user(app_sessions)
    identity = Identity(kind="user", user_id=user_id, api_key_id=None)

    async with admin_sessions() as admin_s, app_sessions() as app_s:
        with pytest.raises(TenantNotFoundError):
            await resolve_project_context(
                identity, uuid.uuid4(), admin_session=admin_s, app_session=app_s
            )


async def test_api_key_identity_resolves_its_own_project_at_fixed_member_role(
    app_sessions: async_sessionmaker[AsyncSession],
    admin_sessions: async_sessionmaker[AsyncSession],
) -> None:
    org_id, user_id = await _make_org_with_admin_user(app_sessions)
    project_id = await _make_project(app_sessions, org_id)
    await _add_project_membership(app_sessions, org_id, project_id, user_id, Role.OWNER)

    async with (
        app_sessions() as session,
        TenantUnitOfWork(session, org_id=org_id, project_id=project_id) as uow,
    ):
        issued = await issue_api_key(uow, name="sdk-key")

    async with admin_sessions() as admin_s:
        identity = await resolve_identity(issued.secret, secret_key=SECRET, admin_session=admin_s)
    assert identity.kind == "api_key"

    # An API key is bound to exactly one project. A different project in
    # the URL must be indistinguishable from an unknown project.
    async with admin_sessions() as admin_s, app_sessions() as app_s:
        with pytest.raises(TenantNotFoundError):
            await resolve_project_context(
                identity, uuid.uuid4(), admin_session=admin_s, app_session=app_s
            )

    async with admin_sessions() as admin_s, app_sessions() as app_s:
        ctx = await resolve_project_context(
            identity, project_id, admin_session=admin_s, app_session=app_s
        )
    assert ctx.project_id == project_id
    assert ctx.role == Role.MEMBER  # fixed, never looked up


async def test_api_key_identity_cannot_resolve_an_org_context(
    app_sessions: async_sessionmaker[AsyncSession],
    admin_sessions: async_sessionmaker[AsyncSession],
) -> None:
    org_id, user_id = await _make_org_with_admin_user(app_sessions)
    project_id = await _make_project(app_sessions, org_id)
    await _add_project_membership(app_sessions, org_id, project_id, user_id, Role.OWNER)

    async with (
        app_sessions() as session,
        TenantUnitOfWork(session, org_id=org_id, project_id=project_id) as uow,
    ):
        issued = await issue_api_key(uow, name="sdk-key")

    async with admin_sessions() as admin_s:
        identity = await resolve_identity(issued.secret, secret_key=SECRET, admin_session=admin_s)

    async with app_sessions() as app_s:
        with pytest.raises(TenantNotFoundError):
            await resolve_org_context(identity, org_id, app_session=app_s)


async def test_resolve_identity_handles_both_token_shapes(
    app_sessions: async_sessionmaker[AsyncSession],
    admin_sessions: async_sessionmaker[AsyncSession],
) -> None:
    _, user_id = await _make_org_with_admin_user(app_sessions)
    jwt_token = issue_access_token(user_id, secret_key=SECRET)

    async with admin_sessions() as admin_s:
        identity = await resolve_identity(jwt_token, secret_key=SECRET, admin_session=admin_s)
    assert identity.kind == "user"
    assert identity.user_id == user_id
