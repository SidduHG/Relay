"""Proves migrations/versions/0002_audit_log_append_only.py's REVOKE
actually holds — not that AuditRepo happens to be write-only (it is,
but that's a convention a future bug or a raw query could break), but
that Postgres itself refuses UPDATE and DELETE against audit_log for
relay_app, the role every app connection uses. INSERT and SELECT stay
untouched, so the row is provably written and then provably
unrewritable and undeletable, by the database, not by discipline.

Same relay_app / asyncpg pattern as test_tenant_isolation.py.
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


async def _seed_org_and_audit_row(conn: asyncpg.Connection) -> tuple[uuid.UUID, uuid.UUID]:
    org = uuid.uuid4()
    entry = uuid.uuid4()
    async with conn.transaction():
        await conn.execute(f"SET LOCAL app.org_id = '{org}'")
        await conn.execute(
            "INSERT INTO organizations (id, name, slug) VALUES ($1, $2, $3)", org, "t", str(org)
        )
        await conn.execute(
            "INSERT INTO audit_log (id, org_id, actor_type, actor_id, action, target, metadata) "
            "VALUES ($1, $2, 'user', $3, 'test.action', 'test-target', '{}')",
            entry,
            org,
            uuid.uuid4(),
        )
    return org, entry


async def test_relay_app_can_insert_and_read_its_own_audit_rows(
    conn: asyncpg.Connection,
) -> None:
    org, entry = await _seed_org_and_audit_row(conn)
    async with conn.transaction():
        await conn.execute(f"SET LOCAL app.org_id = '{org}'")
        row = await conn.fetchrow("SELECT id FROM audit_log WHERE id = $1", entry)
    assert row is not None


async def test_relay_app_cannot_update_an_audit_row(conn: asyncpg.Connection) -> None:
    org, entry = await _seed_org_and_audit_row(conn)
    with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.org_id = '{org}'")
            await conn.execute(
                "UPDATE audit_log SET action = 'tampered' WHERE id = $1", entry
            )


async def test_relay_app_cannot_delete_an_audit_row(conn: asyncpg.Connection) -> None:
    org, entry = await _seed_org_and_audit_row(conn)
    with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
        async with conn.transaction():
            await conn.execute(f"SET LOCAL app.org_id = '{org}'")
            await conn.execute("DELETE FROM audit_log WHERE id = $1", entry)
