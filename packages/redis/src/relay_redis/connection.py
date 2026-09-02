"""Client construction. Deliberately thin, matching
packages/db/connection.py's own shape: apps own the client's lifetime
(created at startup, closed at shutdown), this just knows how to build
one from a URL.
"""

import redis.asyncio as redis


def create_redis_client(redis_url: str) -> redis.Redis:
    return redis.from_url(redis_url, decode_responses=True)
