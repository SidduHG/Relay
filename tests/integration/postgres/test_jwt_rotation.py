"""Proves relay_api.auth.jwt.issue_pair/rotate against real Postgres —
specifically the property that can't be tested without a database at
all: that a refresh token, once rotated, cannot be used a second time,
and that reusing one revokes its entire family (docs/auth/plan.md's
stolen-token response).

Expiry is tested the same way apps/api/tests/unit/auth/test_jwt.py tests
access-token expiry: pass an explicit `now` to rotate() that's past the
refresh token's real expires_at, rather than monkeypatching the clock.
"""

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from relay_api.auth.jwt import (
    REFRESH_TOKEN_TTL,
    InvalidRefreshTokenError,
    RefreshTokenReuseError,
    issue_pair,
    rotate,
    verify_access_token,
)
from relay_db.connection import create_engine, create_session_factory
from relay_db.models.organization import Organization
from relay_db.unit_of_work import TenantUnitOfWork
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

SECRET = "a" * 32


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


async def _make_user(sessions: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    org_id = uuid.uuid4()
    async with sessions() as session, TenantUnitOfWork(session, org_id=org_id) as uow:
        uow.session.add(Organization(id=org_id, name="t", slug=str(org_id)))
        user = await uow.users.create(email=f"{uuid.uuid4()}@x.com", password_hash="x" * 60)
        return user.id


async def test_issued_access_token_verifies_and_refresh_token_is_usable(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _make_user(session_factory)

    async with session_factory() as session, TenantUnitOfWork(session, org_id=uuid.uuid4()) as uow:
        pair = await issue_pair(uow, user_id, secret_key=SECRET)

    assert verify_access_token(pair.access_token, secret_key=SECRET) == user_id

    async with session_factory() as session, TenantUnitOfWork(session, org_id=uuid.uuid4()) as uow:
        rotated = await rotate(uow, pair.refresh_token, secret_key=SECRET)

    assert verify_access_token(rotated.access_token, secret_key=SECRET) == user_id
    assert rotated.refresh_token != pair.refresh_token


async def test_rotated_token_cannot_be_used_a_second_time(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _make_user(session_factory)
    async with session_factory() as session, TenantUnitOfWork(session, org_id=uuid.uuid4()) as uow:
        pair = await issue_pair(uow, user_id, secret_key=SECRET)

    async with session_factory() as session, TenantUnitOfWork(session, org_id=uuid.uuid4()) as uow:
        await rotate(uow, pair.refresh_token, secret_key=SECRET)  # first use: fine

    async with session_factory() as session, TenantUnitOfWork(session, org_id=uuid.uuid4()) as uow:
        with pytest.raises(RefreshTokenReuseError):
            await rotate(uow, pair.refresh_token, secret_key=SECRET)  # second use: reuse


async def test_reuse_revokes_the_entire_family(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The actual security property this whole mechanism exists for: a
    stolen, already-spent token being replayed doesn't just fail on its
    own — it kills every token descended from the same login, including
    ones that were legitimately rotated and never misused."""
    user_id = await _make_user(session_factory)
    async with session_factory() as session, TenantUnitOfWork(session, org_id=uuid.uuid4()) as uow:
        pair = await issue_pair(uow, user_id, secret_key=SECRET)

    async with session_factory() as session, TenantUnitOfWork(session, org_id=uuid.uuid4()) as uow:
        legitimate_next = await rotate(uow, pair.refresh_token, secret_key=SECRET)

    # replay the original (already-used) token -> reuse detected, family revoked
    async with session_factory() as session, TenantUnitOfWork(session, org_id=uuid.uuid4()) as uow:
        with pytest.raises(RefreshTokenReuseError):
            await rotate(uow, pair.refresh_token, secret_key=SECRET)

    # the legitimately-rotated token is now also dead, even though it was
    # never itself reused — the whole chain is burned, per design.
    async with session_factory() as session, TenantUnitOfWork(session, org_id=uuid.uuid4()) as uow:
        with pytest.raises(InvalidRefreshTokenError):
            await rotate(uow, legitimate_next.refresh_token, secret_key=SECRET)


async def test_expired_refresh_token_is_rejected(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _make_user(session_factory)
    async with session_factory() as session, TenantUnitOfWork(session, org_id=uuid.uuid4()) as uow:
        pair = await issue_pair(uow, user_id, secret_key=SECRET)

    long_after_expiry = datetime.now(UTC) + REFRESH_TOKEN_TTL + timedelta(days=1)
    async with session_factory() as session, TenantUnitOfWork(session, org_id=uuid.uuid4()) as uow:
        with pytest.raises(InvalidRefreshTokenError):
            await rotate(uow, pair.refresh_token, secret_key=SECRET, now=long_after_expiry)


async def test_unknown_refresh_token_is_rejected(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session, TenantUnitOfWork(session, org_id=uuid.uuid4()) as uow:
        with pytest.raises(InvalidRefreshTokenError):
            await rotate(uow, "this-token-was-never-issued", secret_key=SECRET)
