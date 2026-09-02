"""Proves TenantUnitOfWork preserves the isolation guarantee that
tests/integration/postgres/test_tenant_isolation.py already proved at
the raw-SQL level — this time through the actual code routes and
services will use, not hand-written asyncpg. Also proves the two things
that are new at this layer: MembershipRepo refuses to write without a
project scope, and __aexit__'s commit/rollback lifecycle is honest about
transaction boundaries.
"""

import os
import uuid
from collections.abc import AsyncIterator

import pytest
from relay_db.connection import create_engine, create_session_factory
from relay_db.models.organization import Organization
from relay_db.unit_of_work import TenantUnitOfWork
from relay_domain.enums.role import Role
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
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


async def _make_org_and_project(
    sessions: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, uuid.UUID]:
    org_id = uuid.uuid4()
    async with sessions() as session, TenantUnitOfWork(session, org_id=org_id) as uow:
        uow.session.add(Organization(id=org_id, name="t", slug=str(org_id)))
        project = await uow.projects.create(name="t", slug=str(uuid.uuid4()))
        return org_id, project.id


async def test_org_scoped_uow_sees_only_its_own_projects(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org_a, _ = await _make_org_and_project(session_factory)
    org_b, proj_b = await _make_org_and_project(session_factory)

    async with session_factory() as session, TenantUnitOfWork(session, org_id=org_a) as uow:
        visible = {p.id for p in await uow.projects.list_all()}
        assert proj_b not in visible

    async with session_factory() as session, TenantUnitOfWork(session, org_id=org_b) as uow:
        visible = {p.id for p in await uow.projects.list_all()}
        assert visible == {proj_b}


async def test_project_scoped_uow_sees_only_its_own_memberships(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org_a, proj_a = await _make_org_and_project(session_factory)
    org_b, proj_b = await _make_org_and_project(session_factory)

    async with (
        session_factory() as session,
        TenantUnitOfWork(session, org_id=org_a, project_id=proj_a) as uow,
    ):
        user = await uow.users.create(email=f"{uuid.uuid4()}@x.com", password_hash="x" * 60)
        await uow.memberships.create(user_id=user.id, role=Role.OWNER)

    async with (
        session_factory() as session,
        TenantUnitOfWork(session, org_id=org_b, project_id=proj_b) as uow,
    ):
        assert await uow.memberships.get(user.id) is None

    async with (
        session_factory() as session,
        TenantUnitOfWork(session, org_id=org_a, project_id=proj_a) as uow,
    ):
        mine = await uow.memberships.get(user.id)
        assert mine is not None
        assert mine.role == Role.OWNER


async def test_membership_create_requires_project_scope(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org_id, _ = await _make_org_and_project(session_factory)

    async with session_factory() as session, TenantUnitOfWork(session, org_id=org_id) as uow:
        with pytest.raises(ValueError, match="project-scoped"):
            await uow.memberships.create(user_id=uuid.uuid4(), role=Role.VIEWER)


async def test_exception_rolls_back_uncommitted_work(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    org_id = uuid.uuid4()
    slug = str(uuid.uuid4())

    with pytest.raises(RuntimeError):
        async with session_factory() as session, TenantUnitOfWork(session, org_id=org_id) as uow:
            uow.session.add(Organization(id=org_id, name="t", slug=str(org_id)))
            await uow.projects.create(name="t", slug=slug)
            raise RuntimeError("simulated failure")

    async with session_factory() as session, TenantUnitOfWork(session, org_id=org_id) as uow:
        # the org insert rolled back too — nothing to see under this org_id
        assert await uow.projects.list_all() == []
