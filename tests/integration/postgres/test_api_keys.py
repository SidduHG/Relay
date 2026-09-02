"""Proves relay_api.auth.api_keys against real Postgres — including the
structural reason verify_api_key takes a raw admin session instead of a
TenantUnitOfWork: api_keys is RLS-scoped by project_id, so a project-
scoped connection cannot find a key before knowing which project it
belongs to. That's the same self-referential problem Task 4's bootstrap
hit with organizations. test_project_scoped_session_cannot_find_a_key_
across_projects proves it directly rather than just asserting it.
"""

import os
import uuid
from collections.abc import AsyncIterator

import pytest
from relay_api.auth.api_keys import (
    InvalidApiKeyError,
    issue_api_key,
    revoke_api_key,
    verify_api_key,
)
from relay_db.connection import create_engine, create_session_factory
from relay_db.models.api_key import ApiKey
from relay_db.models.organization import Organization
from relay_db.unit_of_work import TenantUnitOfWork
from relay_security.hashing import hash_token
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


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


async def _make_project(sessions: async_sessionmaker[AsyncSession]) -> tuple[uuid.UUID, uuid.UUID]:
    org_id = uuid.uuid4()
    async with sessions() as session, TenantUnitOfWork(session, org_id=org_id) as uow:
        uow.session.add(Organization(id=org_id, name="t", slug=str(org_id)))
        project = await uow.projects.create(name="t", slug=str(uuid.uuid4()))
        return org_id, project.id


async def test_issued_key_verifies_via_admin_session(
    app_sessions: async_sessionmaker[AsyncSession],
    admin_sessions: async_sessionmaker[AsyncSession],
) -> None:
    org_id, project_id = await _make_project(app_sessions)
    async with (
        app_sessions() as session,
        TenantUnitOfWork(session, org_id=org_id, project_id=project_id) as uow,
    ):
        issued = await issue_api_key(uow, name="sdk-key")

    async with admin_sessions() as admin_session:
        found = await verify_api_key(admin_session, issued.secret)
    assert found.project_id == project_id
    assert found.name == "sdk-key"


async def test_project_scoped_session_cannot_find_a_key_across_projects(
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    """The reason verify_api_key can't use a TenantUnitOfWork at all: a
    session scoped to any project other than the key's own sees nothing,
    which is exactly correct RLS behavior — but it means there's no
    project to scope by until the key is already found."""
    org_id, project_id = await _make_project(app_sessions)
    async with (
        app_sessions() as session,
        TenantUnitOfWork(session, org_id=org_id, project_id=project_id) as uow,
    ):
        issued = await issue_api_key(uow, name="sdk-key")

    async with (
        app_sessions() as session,
        TenantUnitOfWork(session, org_id=uuid.uuid4(), project_id=uuid.uuid4()) as uow,
    ):
        row = await uow.session.scalar(
            select(ApiKey).where(ApiKey.key_hash == hash_token(issued.secret))
        )
        assert row is None


async def test_unknown_key_is_rejected(
    admin_sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with admin_sessions() as admin_session:
        with pytest.raises(InvalidApiKeyError):
            await verify_api_key(admin_session, "rly_live_" + "x" * 24)


async def test_verify_updates_last_used_at(
    app_sessions: async_sessionmaker[AsyncSession],
    admin_sessions: async_sessionmaker[AsyncSession],
) -> None:
    org_id, project_id = await _make_project(app_sessions)
    async with (
        app_sessions() as session,
        TenantUnitOfWork(session, org_id=org_id, project_id=project_id) as uow,
    ):
        issued = await issue_api_key(uow, name="sdk-key")
    assert issued.record.last_used_at is None

    async with admin_sessions() as admin_session:
        found = await verify_api_key(admin_session, issued.secret)
    assert found.last_used_at is not None


async def test_overlap_rotation_both_keys_valid_until_old_is_revoked(
    app_sessions: async_sessionmaker[AsyncSession],
    admin_sessions: async_sessionmaker[AsyncSession],
) -> None:
    """RELAY-SPEC.md F1: create the new key, run both, then revoke the
    old — the old key must keep working right up until the explicit
    revoke, and the new key must be unaffected by revoking the old one."""
    org_id, project_id = await _make_project(app_sessions)
    async with (
        app_sessions() as session,
        TenantUnitOfWork(session, org_id=org_id, project_id=project_id) as uow,
    ):
        old = await issue_api_key(uow, name="old-key")

    async with (
        app_sessions() as session,
        TenantUnitOfWork(session, org_id=org_id, project_id=project_id) as uow,
    ):
        new = await issue_api_key(uow, name="new-key")

    async with admin_sessions() as s1, admin_sessions() as s2:
        assert (await verify_api_key(s1, old.secret)).name == "old-key"
        assert (await verify_api_key(s2, new.secret)).name == "new-key"

    async with (
        app_sessions() as session,
        TenantUnitOfWork(session, org_id=org_id, project_id=project_id) as uow,
    ):
        await revoke_api_key(uow, old.record.id)

    async with admin_sessions() as admin_session:
        with pytest.raises(InvalidApiKeyError):
            await verify_api_key(admin_session, old.secret)

    async with admin_sessions() as admin_session:
        still_works = await verify_api_key(admin_session, new.secret)
    assert still_works.name == "new-key"
