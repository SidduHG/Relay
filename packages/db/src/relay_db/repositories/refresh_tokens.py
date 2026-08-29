"""Unscoped, like UserRepo — refresh_tokens has no RLS policy. A refresh
token belongs to one user, not an org or a project; there is no tenant
to scope by. It sits behind the UoW for the same reason UserRepo does:
every repository comes from the same place, so calling code never has
to know which ones happen to be scoped.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import select, update

from relay_db.models.refresh_token import RefreshToken

if TYPE_CHECKING:
    from relay_db.unit_of_work import TenantUnitOfWork


class RefreshTokenRepo:
    def __init__(self, uow: "TenantUnitOfWork") -> None:
        self._uow = uow

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        found: RefreshToken | None = await self._uow.session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        return found

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        family_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> RefreshToken:
        token = RefreshToken(
            id=uuid.uuid4(),
            user_id=user_id,
            family_id=family_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self._uow.session.add(token)
        await self._uow.session.flush()
        return token

    async def mark_used(self, token_id: uuid.UUID, *, now: datetime) -> None:
        await self._uow.session.execute(
            update(RefreshToken).where(RefreshToken.id == token_id).values(used_at=now)
        )

    async def revoke_family(self, family_id: uuid.UUID, *, now: datetime) -> None:
        """Every token sharing this family_id gets revoked at once — the
        response to a reuse signal (docs/auth/plan.md): a spent token
        presented again means the family may be stolen, so the whole
        chain dies, not just the one row."""
        await self._uow.session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
