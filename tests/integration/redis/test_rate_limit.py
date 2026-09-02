"""Proves relay_redis.rate_limit.limiter against real Redis: the fixed
window itself, that the TTL is actually set (not just that the count is
right), and — the property a naive INCR-then-separate-EXPIRE can't
guarantee — that the counter is genuinely atomic under real concurrency.
"""

import asyncio
import os
import uuid
from collections.abc import AsyncIterator

import pytest
import redis.asyncio as redis
from relay_redis.connection import create_redis_client
from relay_redis.rate_limit.limiter import check_rate_limit


@pytest.fixture
async def client() -> AsyncIterator[redis.Redis]:
    url = os.environ.get("REDIS_URL")
    if url is None:
        pytest.skip("REDIS_URL not set — start the stack to run this suite")
    conn = create_redis_client(url)
    try:
        await conn.ping()
    except OSError as exc:
        pytest.skip(f"Redis not reachable: {exc}")
    yield conn
    await conn.aclose()


def _key() -> str:
    return f"test:ratelimit:{uuid.uuid4()}"


async def test_allows_up_to_the_limit_then_rejects(client: redis.Redis) -> None:
    key = _key()
    results = [await check_rate_limit(client, key, limit=3, window_seconds=5) for _ in range(5)]
    assert results == [True, True, True, False, False]


async def test_sets_a_ttl_on_first_increment(client: redis.Redis) -> None:
    key = _key()
    await check_rate_limit(client, key, limit=3, window_seconds=10)
    ttl = await client.ttl(key)
    assert 0 < ttl <= 10


async def test_resets_after_the_window_expires(client: redis.Redis) -> None:
    key = _key()
    for _ in range(3):
        await check_rate_limit(client, key, limit=3, window_seconds=1)
    assert await check_rate_limit(client, key, limit=3, window_seconds=1) is False

    await asyncio.sleep(1.5)
    assert await check_rate_limit(client, key, limit=3, window_seconds=1) is True


async def test_is_atomic_under_real_concurrency(client: redis.Redis) -> None:
    """The reason this is a Lua script and not INCR-then-EXPIRE: prove
    that even with many requests racing simultaneously, exactly `limit`
    of them are allowed — never more, from a lost check-then-act race."""
    key = _key()
    results = await asyncio.gather(
        *[check_rate_limit(client, key, limit=10, window_seconds=5) for _ in range(30)]
    )
    assert sum(results) == 10
