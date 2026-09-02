"""Proves relay_api.services.auth_service against real Postgres,
including the timing side-channel fix: verified directly before writing
this file that a naive login() implementation returns in ~0.002ms for
an unknown email but ~210ms for a known email with the wrong password
— a trivially measurable way to enumerate registered emails even with
an identical error message. The dummy-hash comparison closes that gap
to within normal jitter.
"""

import os
import time
import uuid
from collections.abc import AsyncIterator

import pytest
from relay_api.auth.jwt import verify_access_token
from relay_api.services.auth_service import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidEmailError,
    WeakPasswordError,
    login,
    signup,
)
from relay_db.connection import create_engine, create_session_factory
from relay_db.unit_of_work import TenantUnitOfWork
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

SECRET = "a" * 32


@pytest.fixture
async def sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
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


async def test_signup_creates_a_user_with_normalized_email(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session, TenantUnitOfWork(session) as uow:
        user = await signup(uow, f"  Test-{uuid.uuid4()}@Example.COM ", "correct-horse-battery")
    assert user.email == user.email.strip().lower()


async def test_signup_rejects_a_duplicate_email(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    email = f"dup-{uuid.uuid4()}@example.com"
    async with sessions() as session, TenantUnitOfWork(session) as uow:
        await signup(uow, email, "correct-horse-battery")

    async with sessions() as session, TenantUnitOfWork(session) as uow:
        with pytest.raises(EmailAlreadyRegisteredError):
            await signup(uow, email, "a-different-password")


async def test_signup_rejects_an_invalid_email(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session, TenantUnitOfWork(session) as uow:
        with pytest.raises(InvalidEmailError):
            await signup(uow, "not-an-email", "correct-horse-battery")


async def test_signup_rejects_a_weak_password(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session, TenantUnitOfWork(session) as uow:
        with pytest.raises(WeakPasswordError):
            await signup(uow, f"weak-{uuid.uuid4()}@example.com", "short")


async def test_login_succeeds_and_the_access_token_verifies(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    email = f"login-{uuid.uuid4()}@example.com"
    async with sessions() as session, TenantUnitOfWork(session) as uow:
        user = await signup(uow, email, "correct-horse-battery")

    async with sessions() as session, TenantUnitOfWork(session) as uow:
        pair = await login(uow, email, "correct-horse-battery", secret_key=SECRET)

    assert verify_access_token(pair.access_token, secret_key=SECRET) == user.id


async def test_login_rejects_the_wrong_password(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    email = f"wrongpw-{uuid.uuid4()}@example.com"
    async with sessions() as session, TenantUnitOfWork(session) as uow:
        await signup(uow, email, "correct-horse-battery")

    async with sessions() as session, TenantUnitOfWork(session) as uow:
        with pytest.raises(InvalidCredentialsError):
            await login(uow, email, "wrong-password", secret_key=SECRET)


async def test_login_rejects_an_unknown_email(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session, TenantUnitOfWork(session) as uow:
        with pytest.raises(InvalidCredentialsError):
            await login(uow, "never-signed-up@example.com", "whatever", secret_key=SECRET)


async def test_login_timing_does_not_reveal_whether_the_email_is_registered(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    email = f"timing-{uuid.uuid4()}@example.com"
    async with sessions() as session, TenantUnitOfWork(session) as uow:
        await signup(uow, email, "correct-horse-battery")

    async with sessions() as session, TenantUnitOfWork(session) as uow:
        start = time.perf_counter()
        with pytest.raises(InvalidCredentialsError):
            await login(uow, "never-signed-up@example.com", "whatever", secret_key=SECRET)
        elapsed_unknown = time.perf_counter() - start

    async with sessions() as session, TenantUnitOfWork(session) as uow:
        start = time.perf_counter()
        with pytest.raises(InvalidCredentialsError):
            await login(uow, email, "wrong-password", secret_key=SECRET)
        elapsed_known = time.perf_counter() - start

    # bcrypt itself has natural jitter; the fix collapses a ~200ms gap
    # to well under 100ms, not to zero.
    assert abs(elapsed_unknown - elapsed_known) < 0.1
