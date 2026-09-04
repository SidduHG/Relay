"""Post-commit Redis stream indexing; every entry is only a durable-row pointer."""

from datetime import datetime
from uuid import UUID

import redis.asyncio as redis

from relay_redis.keys import queue_stream_key


async def index_job(
    client: redis.Redis,
    *,
    project_id: UUID,
    queue: str,
    job_id: UUID,
    priority: int,
    enqueued_at: datetime,
    maxlen: int = 100_000,
) -> str:
    entry_id = await client.xadd(
        queue_stream_key(project_id, queue, priority),
        {
            "job_id": str(job_id),
            "priority": str(priority),
            "enqueued_at": enqueued_at.isoformat(),
        },
        maxlen=maxlen,
        approximate=True,
    )
    return str(entry_id)


async def trim_queue(client: redis.Redis, project_id: UUID, queue: str) -> None:
    async with client.pipeline(transaction=False) as pipeline:
        for priority in range(4):
            pipeline.xtrim(queue_stream_key(project_id, queue, priority), maxlen=0)
        await pipeline.execute()
