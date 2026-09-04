import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import redis.asyncio as redis
from relay_redis.connection import create_redis_client
from relay_redis.keys import queue_stream_key
from relay_redis.streams import index_job


@pytest.fixture
async def client() -> AsyncIterator[redis.Redis]:
    url = os.environ.get("REDIS_URL")
    if url is None:
        pytest.skip("REDIS_URL not set — start the stack to run this suite")
    connection = create_redis_client(url)
    try:
        await connection.ping()
    except OSError as exc:
        pytest.skip(f"Redis not reachable: {exc}")
    yield connection
    await connection.aclose()


async def test_index_job_uses_the_effective_priority_lane(client: redis.Redis) -> None:
    project_id = uuid.uuid4()
    job_id = uuid.uuid4()
    key = queue_stream_key(project_id, "emails", 1)
    await index_job(
        client,
        project_id=project_id,
        queue="emails",
        job_id=job_id,
        priority=1,
        enqueued_at=datetime.now(UTC),
        maxlen=10,
    )
    entries = await client.xrange(key)
    assert entries[-1][1]["job_id"] == str(job_id)
    await client.delete(key)
