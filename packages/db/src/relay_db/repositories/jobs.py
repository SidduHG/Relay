import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from relay_domain.enums.job_state import JobState
from relay_domain.state_machine import StaleTransitionError, assert_transition
from sqlalchemy import func, select, update

from relay_db.models.job import Job

if TYPE_CHECKING:
    from relay_db.unit_of_work import TenantUnitOfWork


class JobRepo:
    def __init__(self, uow: "TenantUnitOfWork") -> None:
        self._uow = uow

    async def add(self, **values: Any) -> Job:
        job = Job(**values)
        self._uow.session.add(job)
        await self._uow.session.flush()
        return job

    async def get(self, job_id: uuid.UUID, *, created_at: datetime | None = None) -> Job | None:
        statement = select(Job).where(Job.id == job_id)
        if created_at is not None:
            statement = statement.where(Job.created_at == created_at)
        found: Job | None = await self._uow.session.scalar(statement)
        return found

    async def transition(
        self,
        job_id: uuid.UUID,
        *,
        from_state: JobState,
        to_state: JobState,
        **fields: Any,
    ) -> Job:
        assert_transition(from_state, to_state)
        statement = (
            update(Job)
            .where(Job.id == job_id, Job.state == from_state)
            .values(state=to_state, updated_at=func.now(), **fields)
            .returning(Job)
        )
        job = await self._uow.session.scalar(statement)
        if job is None:
            raise StaleTransitionError(
                f"job {job_id} is no longer in expected state {from_state.value}"
            )
        return job

    async def request_cancel(self, job_id: uuid.UUID, at: datetime) -> Job | None:
        return await self._uow.session.scalar(
            update(Job)
            .where(Job.id == job_id, Job.state == JobState.RUNNING)
            .values(cancel_requested_at=at, cancel_reason="operator", updated_at=func.now())
            .returning(Job)
        )

    async def mark_indexed(self, job_id: uuid.UUID, at: datetime) -> None:
        await self._uow.session.execute(
            update(Job).where(Job.id == job_id).values(redis_indexed_at=at, updated_at=func.now())
        )

    async def purge_backlog(self, queue_id: uuid.UUID) -> int:
        result = await self._uow.session.execute(
            update(Job)
            .where(Job.queue_id == queue_id, Job.state.in_([JobState.QUEUED, JobState.SCHEDULED]))
            .values(state=JobState.CANCELLED, cancel_reason="queue_purged", updated_at=func.now())
        )
        return int(result.rowcount)  # type: ignore[attr-defined]

    async def count_running(self, queue_id: uuid.UUID) -> int:
        count = await self._uow.session.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.queue_id == queue_id, Job.state == JobState.RUNNING)
        )
        return int(count or 0)

    async def count_backlog(self, queue_id: uuid.UUID) -> int:
        count = await self._uow.session.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.queue_id == queue_id, Job.state.in_([JobState.QUEUED, JobState.SCHEDULED]))
        )
        return int(count or 0)
