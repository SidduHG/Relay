"""Application composition for durable enqueue and best-effort Redis indexing."""

import asyncio
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import jsonschema
import redis.asyncio as redis
from redis.exceptions import RedisError
from relay_api.auth.tenancy import ProjectContext
from relay_api.config import Settings
from relay_api.services.job_errors import DatabaseUnavailableError, SchemaValidationError
from relay_db.models.queue import Queue
from relay_db.transactions.enqueue import EnqueueResult, EnqueueValues, enqueue_job
from relay_db.unit_of_work import TenantUnitOfWork
from relay_domain.enums.job_state import JobState
from relay_domain.value_objects.queue_name import QueueName
from relay_redis.queues import QueueConfig, QueueConfigCache
from relay_redis.streams import index_job
from relay_storage import BlobStore, prepare_payload
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

_TRACEPARENT = re.compile(r"^[0-9a-f]{2}-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})(?:-.+)?$")
_schema_cache: dict[tuple[str, str], dict[str, Any] | None] = {}


@dataclass(frozen=True, slots=True)
class EnqueueCommand:
    handler: str
    payload: Any
    metadata: dict[str, Any]
    priority: int | None
    run_at: datetime | None
    idempotency_key: str | None
    handler_version: str | None
    traceparent: str | None


@dataclass(frozen=True, slots=True)
class EnqueueOutcome:
    result: EnqueueResult
    indexed: bool


def _queue_from_config(ctx: ProjectContext, name: str, config: QueueConfig) -> Queue:
    return Queue(
        id=config.queue_id,
        project_id=ctx.project_id,
        name=name,
        max_attempts=config.max_attempts,
        job_timeout_seconds=config.job_timeout_seconds,
        lease_duration_seconds=config.lease_duration_seconds,
        default_priority=config.default_priority,
        rate_limit_per_second=config.rate_limit_per_second,
        max_depth=config.max_depth,
    )


def queue_config(queue: Queue) -> QueueConfig:
    return QueueConfig(
        queue_id=queue.id,
        max_attempts=queue.max_attempts,
        job_timeout_seconds=queue.job_timeout_seconds,
        lease_duration_seconds=queue.lease_duration_seconds,
        default_priority=queue.default_priority,
        rate_limit_per_second=queue.rate_limit_per_second,
        max_depth=queue.max_depth,
    )


def invalidate_schema_cache(project_id: str, handler: str) -> None:
    _schema_cache.pop((project_id, handler), None)


async def _validate_handler_payload(
    uow: TenantUnitOfWork, project_id: str, handler: str, payload: Any
) -> None:
    cache_key = (project_id, handler)
    if cache_key not in _schema_cache:
        registered = await uow.handler_schemas.get(handler)
        _schema_cache[cache_key] = registered.schema if registered else None
    schema = _schema_cache[cache_key]
    if schema is None:
        return
    try:
        jsonschema.Draft202012Validator(schema).validate(payload)
    except jsonschema.ValidationError as exc:
        path = ".".join(str(part) for part in exc.absolute_path) or "payload"
        raise SchemaValidationError(f"{path}: {exc.message}") from exc


def _trace_fields(traceparent: str | None) -> tuple[str | None, str | None, int | None]:
    if traceparent is None:
        return None, None, None
    match = _TRACEPARENT.fullmatch(traceparent.strip().lower())
    if match is None:
        return None, None, None
    return match.group(1), match.group(2), int(match.group(3), 16)


async def enqueue(
    session: AsyncSession,
    redis_client: redis.Redis,
    blob_store: BlobStore,
    config_cache: QueueConfigCache,
    settings: Settings,
    ctx: ProjectContext,
    queue_name: str,
    command: EnqueueCommand,
) -> EnqueueOutcome:
    name = str(QueueName.parse(queue_name))
    prepared = prepare_payload(command.payload, max_bytes=settings.payload_max_bytes)
    if command.priority is not None and command.priority not in range(4):
        raise ValueError("priority must be between 0 and 3")
    trace_id, span_id, trace_flags = _trace_fields(command.traceparent)

    cached: QueueConfig | None = None
    try:
        cached = await config_cache.get(redis_client, ctx.project_id, name)
    except RedisError:
        pass

    try:
        async with TenantUnitOfWork(session, org_id=ctx.org_id, project_id=ctx.project_id) as uow:
            queue = (
                _queue_from_config(ctx, name, cached)
                if cached is not None
                else await uow.queues.get_or_create(name)
            )
            await _validate_handler_payload(
                uow, str(ctx.project_id), command.handler, command.payload
            )
            actor_id = ctx.identity.user_id or ctx.identity.api_key_id
            assert actor_id is not None
            result = await enqueue_job(
                uow,
                queue=queue,
                values=EnqueueValues(
                    handler=command.handler,
                    payload=prepared,
                    metadata=command.metadata,
                    priority=command.priority,
                    run_at=command.run_at,
                    idempotency_key=command.idempotency_key,
                    handler_version=command.handler_version,
                    trace_id=trace_id,
                    span_id=span_id,
                    trace_flags=trace_flags,
                ),
                blob_store=blob_store,
                actor_type=ctx.identity.kind,
                actor_id=actor_id,
                inline_max_bytes=settings.payload_inline_max_bytes,
                idempotency_window_hours=settings.idempotency_window_hours,
                blob_upload_timeout_seconds=settings.blob_upload_timeout_seconds,
            )
    except SQLAlchemyError as exc:
        raise DatabaseUnavailableError("database is unavailable") from exc

    if cached is None:
        try:
            await config_cache.put(redis_client, ctx.project_id, name, queue_config(queue))
        except RedisError:
            pass

    if not result.created or result.job.state != JobState.QUEUED:
        return EnqueueOutcome(result=result, indexed=result.job.redis_indexed_at is not None)

    indexed = False
    for attempt in range(settings.enqueue_redis_retry_attempts + 1):
        try:
            await index_job(
                redis_client,
                project_id=ctx.project_id,
                queue=name,
                job_id=result.job.id,
                priority=result.job.priority_effective,
                enqueued_at=result.job.created_at,
                maxlen=settings.queue_stream_maxlen,
            )
            indexed = True
            break
        except RedisError:
            if attempt < settings.enqueue_redis_retry_attempts:
                await asyncio.sleep(0.05 * (2**attempt))

    if indexed:
        try:
            async with TenantUnitOfWork(
                session, org_id=ctx.org_id, project_id=ctx.project_id
            ) as uow:
                await uow.jobs.mark_indexed(result.job.id, datetime.now(UTC))
        except SQLAlchemyError:
            indexed = False
    return EnqueueOutcome(result=result, indexed=indexed)
