"""Proves the RLS policies from migrations/versions/0001_initial_schema.py
actually isolate tenants — not just that the policies exist, but that a
connection scoped to one org/project genuinely cannot see another's rows.

Connects as relay_app (DATABASE_URL), never as the admin/owner role: the
whole point of these tests is that they'd fail silently if run as a
superuser, since Postgres skips RLS for superusers unconditionally. That
exact mistake is what made the first version of this migration's RLS
inert — see docs/auth/plan.md and the 0001 migration's own comments.
"""

import os
import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest


def _dsn_from_env() -> str | None:
    url = os.environ.get("DATABASE_URL")
    if url is None:
        return None
    # asyncpg.connect wants a plain postgres:// DSN, not SQLAlchemy's
    # postgresql+asyncpg:// driver-qualified form.
    return url.replace("postgresql+asyncpg://", "postgresql://")


@pytest.fixture
async def conn() -> AsyncIterator[asyncpg.Connection]:
    dsn = _dsn_from_env()
    if dsn is None:
        pytest.skip("DATABASE_URL not set — start the stack to run this suite")
    try:
        connection = await asyncpg.connect(dsn, timeout=2)
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"Postgres not reachable: {exc}")
    yield connection
    await connection.close()


async def test_connects_as_the_restricted_app_role_not_the_owner(
    conn: asyncpg.Connection,
) -> None:
    """If this ever reports back a superuser, every test below would be
    silently meaningless — RLS is skipped for superusers regardless of
    policy, so this is the precondition the rest of the suite depends on.
    """
    row = await conn.fetchrow(
        "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
    )
    assert row is not None
    assert row["rolsuper"] is False
    assert row["rolbypassrls"] is False


async def test_unscoped_connection_sees_no_projects(conn: asyncpg.Connection) -> None:
    org = uuid.uuid4()
    async with conn.transaction():
        await conn.execute(f"SET LOCAL app.org_id = '{org}'")
        await conn.execute(
            "INSERT INTO organizations (id, name, slug) VALUES ($1, $2, $3)", org, "t", str(org)
        )
        await conn.execute(
            "INSERT INTO projects (id, org_id, name, slug) VALUES ($1, $2, $3, $4)",
            uuid.uuid4(),
            org,
            "t",
            str(uuid.uuid4()),
        )

    async with conn.transaction():
        rows = await conn.fetch("SELECT 1 FROM projects")
        assert rows == []


async def test_previously_touched_session_still_fails_closed_when_unset(
    conn: asyncpg.Connection,
) -> None:
    """The specific bug this migration's NULLIF fix exists for: once a
    custom GUC has been set anywhere in a session, Postgres reverts it to
    '' (not NULL) when the setting transaction ends — a bare ::uuid cast
    on that raises, instead of the intended zero rows. A connection pool
    reusing this connection for a later, unrelated request must still see
    nothing, not crash and not see the wrong tenant.
    """
    async with conn.transaction():
        await conn.execute(f"SET LOCAL app.org_id = '{uuid.uuid4()}'")

    async with conn.transaction():
        rows = await conn.fetch("SELECT 1 FROM projects")  # must not raise
        assert rows == []


async def test_org_scoped_connection_sees_only_its_own_project(
    conn: asyncpg.Connection,
) -> None:
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    proj_a, proj_b = uuid.uuid4(), uuid.uuid4()

    for org, proj in [(org_a, proj_a), (org_b, proj_b)]:
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.org_id = '{org}'")
            await conn.execute(
                "INSERT INTO organizations (id, name, slug) VALUES ($1, $2, $3)",
                org,
                "t",
                str(org),
            )
            await conn.execute(
                "INSERT INTO projects (id, org_id, name, slug) VALUES ($1, $2, $3, $4)",
                proj,
                org,
                "t",
                str(proj),
            )

    async with conn.transaction():
        await conn.execute(f"SET LOCAL app.org_id = '{org_a}'")
        visible = {r["id"] for r in await conn.fetch("SELECT id FROM projects")}
        assert visible == {proj_a}


async def test_project_scoped_connection_sees_only_its_own_memberships(
    conn: asyncpg.Connection,
) -> None:
    org = uuid.uuid4()
    proj_a, proj_b = uuid.uuid4(), uuid.uuid4()
    user_id = uuid.uuid4()

    async with conn.transaction():
        await conn.execute(f"SET LOCAL app.org_id = '{org}'")
        await conn.execute(
            "INSERT INTO organizations (id, name, slug) VALUES ($1, $2, $3)", org, "t", str(org)
        )
        for proj in (proj_a, proj_b):
            await conn.execute(
                "INSERT INTO projects (id, org_id, name, slug) VALUES ($1, $2, $3, $4)",
                proj,
                org,
                "t",
                str(proj),
            )

    async with conn.transaction():
        await conn.execute(f"SET LOCAL app.project_id = '{proj_a}'")
        await conn.execute(
            "INSERT INTO users (id, email, password_hash) VALUES ($1, $2, $3)",
            user_id,
            f"{user_id}@example.com",
            "x" * 60,
        )
        await conn.execute(
            "INSERT INTO memberships (id, user_id, project_id, role) VALUES ($1, $2, $3, 'owner')",
            uuid.uuid4(),
            user_id,
            proj_a,
        )

    async with conn.transaction():
        await conn.execute(f"SET LOCAL app.project_id = '{proj_b}'")
        await conn.execute(
            "INSERT INTO memberships (id, user_id, project_id, role) VALUES "
            "($1, $2, $3, 'viewer')",
            uuid.uuid4(),
            user_id,
            proj_b,
        )

    async with conn.transaction():
        await conn.execute(f"SET LOCAL app.project_id = '{proj_a}'")
        roles = {r["role"] for r in await conn.fetch("SELECT role FROM memberships")}
        assert roles == {"owner"}
