"""API key issuance, revocation, and verification.

Issuing and revoking a key are things an already-authenticated project
admin does to their own project — both go through the normal
TenantUnitOfWork, project-scoped like any other write.

Verifying a presented key is a different kind of operation entirely: at
the moment a request arrives, nothing is known about which project it
belongs to — that's exactly what the key is there to establish. Since
api_keys is RLS-scoped by project_id (docs/auth/plan.md), a project-
scoped connection structurally cannot find a key before knowing its
project — the same self-referential problem Task 4's bootstrap hit with
organizations. verify_api_key takes a raw, admin-connected session
instead of a UoW, the same pattern bootstrap.py uses, for the same
reason: this is a pre-tenant lookup, not a scoped one.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from relay_db.models.api_key import ApiKey
from relay_security.hashing import hash_token
from relay_security.secrets import generate_api_key, visible_prefix
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from relay_db.unit_of_work import TenantUnitOfWork


class InvalidApiKeyError(Exception):
    """Unknown or revoked API key."""


@dataclass(frozen=True, slots=True)
class IssuedApiKey:
    secret: str  # the full rly_live_... string — shown once, never stored
    record: ApiKey


async def issue_api_key(uow: "TenantUnitOfWork", *, name: str) -> IssuedApiKey:
    secret = generate_api_key()
    record = await uow.api_keys.create(
        prefix=visible_prefix(secret), key_hash=hash_token(secret), name=name
    )
    return IssuedApiKey(secret=secret, record=record)


async def revoke_api_key(
    uow: "TenantUnitOfWork", key_id: uuid.UUID, *, now: datetime | None = None
) -> None:
    await uow.api_keys.revoke(key_id, now=now or datetime.now(UTC))


async def verify_api_key(
    admin_session: AsyncSession, presented_key: str, *, now: datetime | None = None
) -> ApiKey:
    """Deliberately takes a raw session, not a UoW — see module docstring.
    Updates last_used_at as a side effect and commits it immediately: this
    is its own standalone fact ("this key was used at this instant"), not
    part of whatever transaction the caller opens next with the project
    it resolves to."""
    current_time = now or datetime.now(UTC)
    row = await admin_session.scalar(
        select(ApiKey).where(ApiKey.key_hash == hash_token(presented_key))
    )
    if row is None or row.revoked_at is not None:
        raise InvalidApiKeyError("API key is unknown or revoked")

    row.last_used_at = current_time
    await admin_session.commit()
    return row
