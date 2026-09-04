import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from relay_db.models.idempotency import IdempotencyKey

if TYPE_CHECKING:
    from relay_db.unit_of_work import TenantUnitOfWork


class IdempotencyRepo:
    def __init__(self, uow: "TenantUnitOfWork") -> None:
        self._uow = uow

    async def claim(
        self,
        *,
        queue_id: uuid.UUID,
        key_hash: str,
        job_id: uuid.UUID,
        job_created_at: datetime,
        expires_at: datetime,
    ) -> bool:
        if self._uow.project_id is None:
            raise ValueError("IdempotencyRepo requires a project-scoped UnitOfWork")
        won = await self._uow.session.scalar(
            insert(IdempotencyKey)
            .values(
                project_id=self._uow.project_id,
                queue_id=queue_id,
                key_hash=key_hash,
                job_id=job_id,
                job_created_at=job_created_at,
                expires_at=expires_at,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    IdempotencyKey.project_id,
                    IdempotencyKey.queue_id,
                    IdempotencyKey.key_hash,
                ]
            )
            .returning(IdempotencyKey.job_id)
        )
        return won is not None

    async def get(self, queue_id: uuid.UUID, key_hash: str) -> IdempotencyKey | None:
        found: IdempotencyKey | None = await self._uow.session.scalar(
            select(IdempotencyKey).where(
                IdempotencyKey.queue_id == queue_id,
                IdempotencyKey.key_hash == key_hash,
            )
        )
        return found
