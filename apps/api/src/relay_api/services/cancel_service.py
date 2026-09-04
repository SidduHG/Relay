from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from relay_api.auth.tenancy import ProjectContext
from relay_api.services.job_errors import JobNotFoundError
from relay_db.models.job import Job
from relay_db.unit_of_work import TenantUnitOfWork
from relay_domain.enums.job_state import JobState
from relay_domain.state_machine import IllegalTransitionError
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class CancelOutcome:
    job: Job
    pending: bool


async def cancel_job(session: AsyncSession, ctx: ProjectContext, job_id: UUID) -> CancelOutcome:
    now = datetime.now(UTC)
    async with TenantUnitOfWork(session, org_id=ctx.org_id, project_id=ctx.project_id) as uow:
        job = await uow.jobs.get(job_id)
        if job is None:
            raise JobNotFoundError(f"job {job_id} was not found")
        if job.state == JobState.RUNNING:
            requested = await uow.jobs.request_cancel(job_id, now)
            if requested is None:
                raise IllegalTransitionError("job state changed while cancellation was requested")
            return CancelOutcome(job=requested, pending=True)
        if job.state in {JobState.QUEUED, JobState.SCHEDULED, JobState.BLOCKED}:
            cancelled = await uow.jobs.transition(
                job_id,
                from_state=job.state,
                to_state=JobState.CANCELLED,
                finished_at=now,
                cancel_reason="operator",
            )
            return CancelOutcome(job=cancelled, pending=False)
        raise IllegalTransitionError(f"cannot cancel a job in state {job.state.value}")
