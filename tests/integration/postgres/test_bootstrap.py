"""Proves relay_db.bootstrap.ensure_default_organization — both that it
works, and specifically that it requires the admin connection.

organizations' RLS policy is self-referential (id = current_setting
('app.org_id')), which makes "does any org exist?" undiscoverable to the
restricted relay_app role without already knowing an id to search for.
Verified directly while building this: relay_app could create the first
org but then could never find it again on a second call. See
apps/api/src/relay_api/config.py's database_admin_url docstring.
"""

import os
import uuid
from collections.abc import AsyncIterator

import pytest
from relay_db.bootstrap import ensure_default_organization
from relay_db.connection import create_engine, create_session_factory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
async def admin_session() -> AsyncIterator[AsyncSession]:
    url = os.environ.get("DATABASE_ADMIN_URL")
    if url is None:
        pytest.skip("DATABASE_ADMIN_URL not set — start the stack to run this suite")
    engine = create_engine(url)
    try:
        sessions = create_session_factory(engine)
        async with sessions() as session:
            # ensure_default_organization's real invariant is "a fresh
            # deployment gets exactly one org" — the admin role bypasses
            # RLS entirely, so it sees ANY pre-existing org regardless of
            # slug (correct production behavior: "does one exist at all?",
            # not "does this specific one"). Testing creation honestly
            # means actually starting from empty, not just a fresh slug.
            await session.execute(text("TRUNCATE organizations CASCADE"))
            await session.commit()
            yield session
    except OSError as exc:
        pytest.skip(f"Postgres not reachable: {exc}")
    finally:
        await engine.dispose()


@pytest.fixture
async def app_session() -> AsyncIterator[AsyncSession]:
    """The restricted role — used to prove it can't do what admin_session can."""
    url = os.environ.get("DATABASE_URL")
    if url is None:
        pytest.skip("DATABASE_URL not set — start the stack to run this suite")
    engine = create_engine(url)
    try:
        sessions = create_session_factory(engine)
        async with sessions() as session:
            yield session
    except OSError as exc:
        pytest.skip(f"Postgres not reachable: {exc}")
    finally:
        await engine.dispose()


async def test_creates_an_organization_when_none_matches_the_slug(
    admin_session: AsyncSession,
) -> None:
    slug = f"test-{uuid.uuid4()}"
    org = await ensure_default_organization(admin_session, name="Test Org", slug=slug)
    assert org.slug == slug
    assert org.name == "Test Org"


async def test_is_idempotent_across_repeated_calls(admin_session: AsyncSession) -> None:
    slug = f"test-{uuid.uuid4()}"
    first = await ensure_default_organization(admin_session, name="Test Org", slug=slug)
    second = await ensure_default_organization(admin_session, name="Test Org", slug=slug)
    third = await ensure_default_organization(admin_session, name="Test Org", slug=slug)
    assert first.id == second.id == third.id


async def test_restricted_role_cannot_perform_bootstrap(app_session: AsyncSession) -> None:
    """The bug this whole file exists to pin down: called with the
    RLS-restricted connection, the recovery path after a slug conflict
    can't find the row it just failed to see, and the function's own
    invariant (a row exists after a unique violation) breaks."""
    slug = f"test-{uuid.uuid4()}"
    await ensure_default_organization(app_session, name="Test Org", slug=slug)

    with pytest.raises(AssertionError, match="unique violation implies a row exists"):
        await ensure_default_organization(app_session, name="Test Org", slug=slug)
