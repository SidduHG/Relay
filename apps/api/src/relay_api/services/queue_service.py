import hmac
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jsonschema
import redis.asyncio as redis
from redis.exceptions import RedisError
from relay_api.auth.tenancy import ProjectContext
from relay_api.services.enqueue_service import invalidate_schema_cache
from relay_api.services.job_errors import (
    InvalidQueueDefaultsError,
    PurgeTokenInvalidError,
    QueueIndexUnavailableError,
    QueueNotFoundError,
    SchemaValidationError,
)
from relay_db.models.handler_schema import HandlerSchema
from relay_db.models.queue import Queue
from relay_db.unit_of_work import TenantUnitOfWork
from relay_domain.value_objects.queue_name import QueueName
from relay_redis.keys import purge_token_key
from relay_redis.queues.config_cache import QueueConfigCache, set_paused
from relay_redis.streams import trim_queue
from relay_security.hashing import hash_token
from relay_security.secrets import generate_url_token
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class PurgeToken:
    token: str
    expires_at: datetime
    queue: str
    job_count: int


@dataclass(frozen=True, slots=True)
class PurgeResult:
    cancelled: int
    still_running: int


async def get_queue(session: AsyncSession, ctx: ProjectContext, name: str) -> Queue:
    parsed = str(QueueName.parse(name))
    async with TenantUnitOfWork(session, org_id=ctx.org_id, project_id=ctx.project_id) as uow:
        queue = await uow.queues.get(parsed)
    if queue is None:
        raise QueueNotFoundError(f"queue {parsed} was not found")
    return queue


async def list_queues(session: AsyncSession, ctx: ProjectContext) -> list[Queue]:
    async with TenantUnitOfWork(session, org_id=ctx.org_id, project_id=ctx.project_id) as uow:
        return list(await uow.queues.list_all())


def _validate_defaults(values: dict[str, Any]) -> None:
    bounds = {
        "max_attempts": (1, 25),
        "job_timeout_seconds": (1, 86_400),
        "lease_duration_seconds": (10, 3_600),
        "default_priority": (0, 3),
    }
    for key, (minimum, maximum) in bounds.items():
        value = values.get(key)
        if value is not None and not minimum <= value <= maximum:
            raise InvalidQueueDefaultsError(f"{key} must be between {minimum} and {maximum}")
    for key in ("rate_limit_per_second", "max_depth"):
        value = values.get(key)
        if value is not None and value < 1:
            raise InvalidQueueDefaultsError(f"{key} must be at least 1")


async def update_defaults(
    session: AsyncSession,
    redis_client: redis.Redis,
    cache: QueueConfigCache,
    ctx: ProjectContext,
    name: str,
    values: dict[str, Any],
) -> Queue:
    _validate_defaults(values)
    queue = await get_queue(session, ctx, name)
    async with TenantUnitOfWork(session, org_id=ctx.org_id, project_id=ctx.project_id) as uow:
        updated = await uow.queues.update_defaults(queue.id, values)
    try:
        await cache.invalidate(redis_client, ctx.project_id, queue.name)
    except RedisError:
        pass
    return updated


async def change_pause(
    session: AsyncSession,
    redis_client: redis.Redis,
    ctx: ProjectContext,
    name: str,
    *,
    paused: bool,
) -> Queue:
    queue = await get_queue(session, ctx, name)
    now = datetime.now(UTC)
    actor_id = ctx.identity.user_id
    assert actor_id is not None
    async with TenantUnitOfWork(session, org_id=ctx.org_id, project_id=ctx.project_id) as uow:
        updated = await uow.queues.set_paused(
            queue.id, at=now if paused else None, actor_id=actor_id if paused else None
        )
        await uow.audit.write(
            actor_type="user",
            actor_id=actor_id,
            action="queue.paused" if paused else "queue.resumed",
            target=queue.name,
            project_id=ctx.project_id,
        )
    try:
        await set_paused(redis_client, ctx.project_id, queue.name, paused=paused)
    except RedisError as exc:
        raise QueueIndexUnavailableError(
            f"queue truth is {'paused' if paused else 'resumed'}, but Redis was not updated"
        ) from exc
    return updated


async def mint_purge_token(
    session: AsyncSession,
    redis_client: redis.Redis,
    ctx: ProjectContext,
    name: str,
    ttl_seconds: int,
) -> PurgeToken:
    queue = await get_queue(session, ctx, name)
    async with TenantUnitOfWork(session, org_id=ctx.org_id, project_id=ctx.project_id) as uow:
        count = await uow.jobs.count_backlog(queue.id)
    token = generate_url_token()
    try:
        await redis_client.set(
            purge_token_key(ctx.project_id, queue.name), hash_token(token), ex=ttl_seconds
        )
    except RedisError as exc:
        raise QueueIndexUnavailableError("could not store the purge confirmation") from exc
    return PurgeToken(
        token=token,
        expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
        queue=queue.name,
        job_count=count,
    )


async def purge_queue(
    session: AsyncSession,
    redis_client: redis.Redis,
    ctx: ProjectContext,
    name: str,
    confirmation: str,
) -> PurgeResult:
    queue = await get_queue(session, ctx, name)
    try:
        expected = await redis_client.getdel(purge_token_key(ctx.project_id, queue.name))
    except RedisError as exc:
        raise QueueIndexUnavailableError("could not consume the purge confirmation") from exc
    if expected is None or not hmac.compare_digest(str(expected), hash_token(confirmation)):
        raise PurgeTokenInvalidError("purge confirmation is invalid or expired")
    actor_id = ctx.identity.user_id
    assert actor_id is not None
    async with TenantUnitOfWork(session, org_id=ctx.org_id, project_id=ctx.project_id) as uow:
        cancelled = await uow.jobs.purge_backlog(queue.id)
        running = await uow.jobs.count_running(queue.id)
        await uow.audit.write(
            actor_type="user",
            actor_id=actor_id,
            action="queue.purged",
            target=queue.name,
            project_id=ctx.project_id,
            extra={"cancelled": cancelled, "still_running": running},
        )
    try:
        await trim_queue(redis_client, ctx.project_id, queue.name)
    except RedisError as exc:
        raise QueueIndexUnavailableError("backlog was cancelled but Redis trim failed") from exc
    return PurgeResult(cancelled=cancelled, still_running=running)


async def list_handler_schemas(session: AsyncSession, ctx: ProjectContext) -> list[HandlerSchema]:
    async with TenantUnitOfWork(session, org_id=ctx.org_id, project_id=ctx.project_id) as uow:
        return list(await uow.handler_schemas.list_all())


async def put_handler_schema(
    session: AsyncSession, ctx: ProjectContext, handler: str, schema: dict[str, Any]
) -> HandlerSchema:
    try:
        jsonschema.Draft202012Validator.check_schema(schema)
    except jsonschema.SchemaError as exc:
        raise SchemaValidationError(f"invalid JSON Schema: {exc.message}") from exc
    async with TenantUnitOfWork(session, org_id=ctx.org_id, project_id=ctx.project_id) as uow:
        result = await uow.handler_schemas.put(handler, schema)
    invalidate_schema_cache(str(ctx.project_id), handler)
    return result


async def delete_handler_schema(session: AsyncSession, ctx: ProjectContext, handler: str) -> None:
    async with TenantUnitOfWork(session, org_id=ctx.org_id, project_id=ctx.project_id) as uow:
        await uow.handler_schemas.delete(handler)
    invalidate_schema_cache(str(ctx.project_id), handler)
