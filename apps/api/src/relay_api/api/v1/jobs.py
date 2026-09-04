import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from relay_api.api.deps import get_app_session, require_project_permission
from relay_api.auth.permissions import Permission
from relay_api.auth.tenancy import ProjectContext
from relay_api.config import settings
from relay_api.schemas.common import CursorPage
from relay_api.schemas.job import AttemptOut, CancelOut, EnqueueRequest, JobOut
from relay_api.services.cancel_service import cancel_job
from relay_api.services.enqueue_service import EnqueueCommand, enqueue
from relay_api.services.job_errors import JobNotFoundError
from relay_db.models.attempt import JobAttempt
from relay_db.models.job import Job
from relay_db.queries.job_queries import JobFilters, list_jobs
from relay_db.unit_of_work import TenantUnitOfWork
from relay_domain.enums.job_state import JobState
from relay_storage import rehydrate_payload
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/v1/projects/{project_id}", tags=["jobs"])


def _job_out(
    job: Job,
    *,
    attempts: list[JobAttempt] | None = None,
    created: bool | None = None,
    indexed: bool | None = None,
    payload: Any = ...,
) -> JobOut:
    body = job.payload if payload is ... else payload
    return JobOut(
        id=job.id,
        created_at=job.created_at,
        queue=job.queue_name,
        handler=job.handler,
        handler_version=job.handler_version,
        payload=body,
        payload_ref=job.payload_ref,
        payload_bytes=job.payload_bytes,
        metadata=job.extra,
        state=job.state,
        priority=job.priority,
        priority_effective=job.priority_effective,
        attempt=job.attempt,
        max_attempts=job.max_attempts,
        timeout_seconds=job.timeout_seconds,
        lease_seconds=job.lease_seconds,
        run_at=job.run_at,
        cancel_requested_at=job.cancel_requested_at,
        created=created,
        indexed=job.redis_indexed_at is not None if indexed is None else indexed,
        attempts=[AttemptOut.model_validate(value) for value in attempts or []],
    )


@router.post("/queues/{queue_name}/jobs", response_model=JobOut, status_code=201)
async def enqueue_job_route(
    project_id: uuid.UUID,
    queue_name: str,
    body: EnqueueRequest,
    request: Request,
    response: Response,
    ctx: ProjectContext = Depends(require_project_permission(Permission.JOB_ENQUEUE)),
    session: AsyncSession = Depends(get_app_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    traceparent: str | None = Header(default=None),
) -> JobOut:
    outcome = await enqueue(
        session,
        request.app.state.redis,
        request.app.state.blob_store,
        request.app.state.queue_config_cache,
        settings,
        ctx,
        queue_name,
        EnqueueCommand(
            handler=body.handler,
            payload=body.payload,
            metadata=body.metadata,
            priority=body.priority,
            run_at=body.run_at,
            idempotency_key=idempotency_key,
            handler_version=body.handler_version,
            traceparent=traceparent,
        ),
    )
    response.status_code = 201 if outcome.result.created else 200
    return _job_out(
        outcome.result.job,
        created=outcome.result.created,
        indexed=outcome.indexed,
    )


@router.get("/jobs", response_model=CursorPage[JobOut])
async def list_jobs_route(
    project_id: uuid.UUID,
    ctx: ProjectContext = Depends(require_project_permission(Permission.PROJECT_READ)),
    session: AsyncSession = Depends(get_app_session),
    state: JobState | None = None,
    handler: str | None = None,
    queue: str | None = None,
    from_time: datetime | None = Query(default=None, alias="from"),
    to_time: datetime | None = Query(default=None, alias="to"),
    limit: int = Query(default=settings.job_list_page_size_default, ge=1),
    cursor: str | None = None,
) -> CursorPage[JobOut]:
    limit = min(limit, settings.job_list_page_size_max)
    filters = JobFilters(
        state=state,
        handler=handler,
        queue=queue,
        from_time=from_time,
        to_time=to_time,
    )
    async with TenantUnitOfWork(session, org_id=ctx.org_id, project_id=ctx.project_id) as uow:
        page = await list_jobs(uow, filters=filters, limit=limit, cursor=cursor)
    return CursorPage(
        items=[_job_out(job) for job in page.items],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
    )


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job_route(
    project_id: uuid.UUID,
    job_id: uuid.UUID,
    request: Request,
    include: str | None = None,
    ctx: ProjectContext = Depends(require_project_permission(Permission.PROJECT_READ)),
    session: AsyncSession = Depends(get_app_session),
) -> JobOut:
    async with TenantUnitOfWork(session, org_id=ctx.org_id, project_id=ctx.project_id) as uow:
        job = await uow.jobs.get(job_id)
        if job is None:
            raise JobNotFoundError(f"job {job_id} was not found")
        attempts = list(await uow.attempts.list_for_job(job_id))
    payload = job.payload
    if include == "payload" and job.payload_ref:
        payload = await rehydrate_payload(request.app.state.blob_store, job.payload_ref)
    return _job_out(job, attempts=attempts, payload=payload)


@router.post("/jobs/{job_id}/cancel", response_model=CancelOut)
async def cancel_job_route(
    project_id: uuid.UUID,
    job_id: uuid.UUID,
    response: Response,
    ctx: ProjectContext = Depends(require_project_permission(Permission.JOB_CANCEL)),
    session: AsyncSession = Depends(get_app_session),
) -> CancelOut:
    outcome = await cancel_job(session, ctx, job_id)
    response.status_code = 202 if outcome.pending else 200
    return CancelOut(job=_job_out(outcome.job), pending=outcome.pending)
