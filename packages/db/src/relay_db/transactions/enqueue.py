"""The durable enqueue transaction: claim, offload, insert, then commit outside."""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from relay_domain.enums.job_state import JobState
from relay_security.hashing import hash_token
from relay_storage import (
    INLINE_MAX_BYTES,
    BlobStore,
    PreparedPayload,
    StorageUnavailableError,
    offload_payload,
)

from relay_db.models.job import Job
from relay_db.models.queue import Queue
from relay_db.unit_of_work import TenantUnitOfWork


@dataclass(frozen=True, slots=True)
class EnqueueValues:
    handler: str
    payload: PreparedPayload
    metadata: dict[str, Any] = field(default_factory=dict)
    priority: int | None = None
    run_at: datetime | None = None
    idempotency_key: str | None = None
    handler_version: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    trace_flags: int | None = None


@dataclass(frozen=True, slots=True)
class EnqueueResult:
    job: Job
    created: bool


async def enqueue_job(
    uow: TenantUnitOfWork,
    *,
    queue: Queue,
    values: EnqueueValues,
    blob_store: BlobStore,
    actor_type: Literal["user", "api_key", "schedule", "replay"],
    actor_id: uuid.UUID,
    inline_max_bytes: int = INLINE_MAX_BYTES,
    idempotency_window_hours: int = 24,
    blob_upload_timeout_seconds: int = 10,
    now: datetime | None = None,
) -> EnqueueResult:
    """Run before the UoW context exits; that exit is the durability commit."""
    if uow.project_id is None:
        raise ValueError("enqueue requires a project-scoped UnitOfWork")
    created_at = now or datetime.now(UTC)
    job_id = uuid.uuid4()
    key_hash = hash_token(values.idempotency_key) if values.idempotency_key else None

    if key_hash is not None:
        won = await uow.idempotency.claim(
            queue_id=queue.id,
            key_hash=key_hash,
            job_id=job_id,
            job_created_at=created_at,
            expires_at=created_at + timedelta(hours=idempotency_window_hours),
        )
        if not won:
            claim = await uow.idempotency.get(queue.id, key_hash)
            if claim is None:
                raise RuntimeError("idempotency conflict completed without a visible claim")
            existing = await uow.jobs.get(claim.job_id, created_at=claim.job_created_at)
            if existing is None:
                raise RuntimeError("idempotency claim points to a missing job")
            return EnqueueResult(job=existing, created=False)

    payload_ref: str | None = None
    inline_payload: Any | None = values.payload.value
    if values.payload.size > inline_max_bytes:
        try:
            async with asyncio.timeout(blob_upload_timeout_seconds):
                payload_ref = await offload_payload(
                    blob_store,
                    values.payload,
                    project_id=uow.project_id,
                    job_id=job_id,
                    created_at=created_at,
                )
        except TimeoutError as exc:
            raise StorageUnavailableError("payload storage timed out") from exc
        inline_payload = None

    state = (
        JobState.SCHEDULED
        if values.run_at is not None and values.run_at > created_at
        else JobState.QUEUED
    )
    priority = values.priority if values.priority is not None else queue.default_priority
    job = await uow.jobs.add(
        id=job_id,
        created_at=created_at,
        project_id=uow.project_id,
        queue_id=queue.id,
        queue_name=queue.name,
        handler=values.handler,
        handler_version=values.handler_version,
        payload=inline_payload,
        payload_ref=payload_ref,
        payload_bytes=values.payload.size,
        extra=values.metadata,
        state=state,
        priority=priority,
        priority_effective=priority,
        max_attempts=queue.max_attempts,
        timeout_seconds=queue.job_timeout_seconds,
        lease_seconds=queue.lease_duration_seconds,
        run_at=values.run_at,
        trace_id=values.trace_id,
        span_id=values.span_id,
        trace_flags=values.trace_flags,
        enqueued_by_type=actor_type,
        enqueued_by_id=actor_id,
        idempotency_key_hash=key_hash,
    )
    return EnqueueResult(job=job, created=True)
