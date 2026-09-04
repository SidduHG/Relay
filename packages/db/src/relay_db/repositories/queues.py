import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from relay_db.models.queue import Queue

if TYPE_CHECKING:
    from relay_db.unit_of_work import TenantUnitOfWork


class QueueRepo:
    def __init__(self, uow: "TenantUnitOfWork") -> None:
        self._uow = uow

    async def get(self, name: str) -> Queue | None:
        found: Queue | None = await self._uow.session.scalar(
            select(Queue).where(Queue.name == name)
        )
        return found

    async def get_by_id(self, queue_id: uuid.UUID) -> Queue | None:
        return await self._uow.session.get(Queue, queue_id)

    async def list_all(self) -> Sequence[Queue]:
        result = await self._uow.session.scalars(select(Queue).order_by(Queue.name))
        return result.all()

    async def get_or_create(self, name: str) -> Queue:
        existing = await self.get(name)
        if existing is not None:
            return existing
        if self._uow.project_id is None:
            raise ValueError("QueueRepo requires a project-scoped UnitOfWork")
        await self._uow.session.execute(
            insert(Queue)
            .values(id=uuid.uuid4(), project_id=self._uow.project_id, name=name)
            .on_conflict_do_nothing(index_elements=[Queue.project_id, Queue.name])
        )
        found = await self.get(name)
        if found is None:
            raise RuntimeError("queue upsert completed without a visible row")
        return found

    async def update_defaults(self, queue_id: uuid.UUID, values: Mapping[str, Any]) -> Queue:
        statement = (
            update(Queue)
            .where(Queue.id == queue_id)
            .values(**values, updated_at=func.now())
            .returning(Queue)
        )
        queue = await self._uow.session.scalar(statement)
        if queue is None:
            raise LookupError("queue not found")
        return queue

    async def set_paused(
        self, queue_id: uuid.UUID, *, at: datetime | None, actor_id: uuid.UUID | None
    ) -> Queue:
        return await self.update_defaults(queue_id, {"paused_at": at, "paused_by": actor_id})
