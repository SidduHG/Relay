"""Ensures a fresh, self-hosted deployment has exactly one organization.

RELAY-SPEC.md defers hosted multi-org to v2 — v1 is "self-hosted, one
org per deployment" — but the schema itself supports many organizations
(docs/auth/plan.md). Rather than special-case "no org yet" throughout
the app, a fresh deployment gets a real Organization row the very first
time the API starts, and every request onward has one to attach to.
"""

import logging
import uuid

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from relay_db.models.organization import Organization

logger = logging.getLogger(__name__)


async def ensure_default_organization(
    session: AsyncSession, *, name: str = "Default", slug: str = "default"
) -> Organization:
    existing = await session.scalar(select(Organization).limit(1))
    if existing is not None:
        return existing

    # organizations is RLS-protected, policy: id = current_setting('app.org_id').
    # Creating a brand-new org means scoping the transaction to its own
    # about-to-exist id — the same self-referential pattern proven in
    # tests/integration/postgres/test_tenant_isolation.py.
    #
    # SET LOCAL cannot take a bind parameter at all (verified: asyncpg
    # sends it as "$1" and Postgres rejects it — SET is a utility
    # statement, not DML, and never goes through parameter binding).
    # Interpolating is safe here specifically because org_id is a
    # uuid.UUID, not user input: str(UUID) always renders as the fixed
    # 8-4-4-4-12 hex form with no character that could break out of it.
    org_id = uuid.uuid4()
    await session.execute(text(f"SET LOCAL app.org_id = '{org_id}'"))

    org = Organization(id=org_id, name=name, slug=slug)
    session.add(org)
    try:
        await session.commit()
    except IntegrityError:
        # Another replica bootstrapped first between our check and our
        # insert — the unique slug constraint caught it. Not an error:
        # exactly one organization now exists, which is the goal.
        await session.rollback()
        recovered: Organization | None = await session.scalar(select(Organization).limit(1))
        assert recovered is not None, "unique violation implies a row exists"
        return recovered

    logger.info("bootstrapped default organization", extra={"org_id": str(org_id)})
    return org
