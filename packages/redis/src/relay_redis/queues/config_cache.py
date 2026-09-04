"""Short-lived queue-default cache and the worker-visible pause flag."""

import time
from dataclasses import asdict, dataclass
from uuid import UUID

import redis.asyncio as redis

from relay_redis.keys import queue_config_key, queue_paused_key


@dataclass(frozen=True, slots=True)
class QueueConfig:
    queue_id: UUID
    max_attempts: int
    job_timeout_seconds: int
    lease_duration_seconds: int
    default_priority: int
    rate_limit_per_second: int | None
    max_depth: int | None


class QueueConfigCache:
    def __init__(self, ttl_seconds: int = 5) -> None:
        self._ttl = ttl_seconds
        self._local: dict[tuple[UUID, str], tuple[float, QueueConfig]] = {}

    async def get(self, client: redis.Redis, project_id: UUID, queue: str) -> QueueConfig | None:
        local_key = (project_id, queue)
        cached = self._local.get(local_key)
        if cached is not None and cached[0] > time.monotonic():
            return cached[1]
        values = await client.hgetall(queue_config_key(project_id, queue))
        if not values:
            self._local.pop(local_key, None)
            return None
        decoded = {
            key.decode() if isinstance(key, bytes) else key: (
                value.decode() if isinstance(value, bytes) else value
            )
            for key, value in values.items()
        }
        config = QueueConfig(
            queue_id=UUID(decoded["queue_id"]),
            max_attempts=int(decoded["max_attempts"]),
            job_timeout_seconds=int(decoded["job_timeout_seconds"]),
            lease_duration_seconds=int(decoded["lease_duration_seconds"]),
            default_priority=int(decoded["default_priority"]),
            rate_limit_per_second=(
                int(decoded["rate_limit_per_second"])
                if decoded.get("rate_limit_per_second")
                else None
            ),
            max_depth=int(decoded["max_depth"]) if decoded.get("max_depth") else None,
        )
        self._local[local_key] = (time.monotonic() + self._ttl, config)
        return config

    async def put(
        self, client: redis.Redis, project_id: UUID, queue: str, config: QueueConfig
    ) -> None:
        redis_value = bytes | bytearray | memoryview | str | int | float
        values: dict[redis_value, redis_value] = {}
        for key, value in asdict(config).items():
            values[key] = "" if value is None else str(value)
        await client.hset(queue_config_key(project_id, queue), mapping=values)
        await client.expire(queue_config_key(project_id, queue), self._ttl)
        self._local[(project_id, queue)] = (time.monotonic() + self._ttl, config)

    async def invalidate(self, client: redis.Redis, project_id: UUID, queue: str) -> None:
        self._local.pop((project_id, queue), None)
        await client.delete(queue_config_key(project_id, queue))


async def set_paused(client: redis.Redis, project_id: UUID, queue: str, *, paused: bool) -> None:
    key = queue_paused_key(project_id, queue)
    if paused:
        await client.set(key, "1")
    else:
        await client.delete(key)
