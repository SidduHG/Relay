"""project_id-scoped, like MembershipRepo — create() and revoke() are
for an authenticated admin managing their own project's keys, and both
require knowing the project already. Finding a key WITHOUT knowing its
project first (verifying one presented by the SDK) is a different,
pre-tenant operation that cannot go through this repo at all — RLS
would filter it to nothing before the caller even knows which project
to scope by. See apps/api/auth/api_keys.py's verify_api_key.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import select, update

from relay_db.models.api_key import ApiKey

if TYPE_CHECKING:
    from relay_db.unit_of_work import TenantUnitOfWork


class ApiKeyRepo:
    def __init__(self, uow: "TenantUnitOfWork") -> None:
        self._uow = uow

    async def list_for_project(self) -> Sequence[ApiKey]:
        result = await self._uow.session.scalars(select(ApiKey))
        return result.all()

    async def create(self, *, prefix: str, key_hash: str, name: str) -> ApiKey:
        if self._uow.project_id is None:
            # Same guard as MembershipRepo.create: RLS fails a write
            # closed on its own, but there's no correct project_id to
            # invent for a NOT NULL column — fail loud instead of guessing.
            raise ValueError("ApiKeyRepo.create requires a project-scoped UnitOfWork")
        key = ApiKey(
            id=uuid.uuid4(),
            project_id=self._uow.project_id,
            prefix=prefix,
            key_hash=key_hash,
            name=name,
        )
        self._uow.session.add(key)
        await self._uow.session.flush()
        return key

    async def revoke(self, key_id: uuid.UUID, *, now: datetime) -> None:
        await self._uow.session.execute(
            update(ApiKey).where(ApiKey.id == key_id).values(revoked_at=now)
        )
