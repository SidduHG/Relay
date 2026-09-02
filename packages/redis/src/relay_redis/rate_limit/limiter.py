"""A generic, reusable fixed-window rate limiter. No FastAPI or HTTP
knowledge — apps/api/middleware/rate_limit.py is what turns "allowed"
into a 429.

INCR then a separate EXPIRE has a real race: two concurrent requests can
both read the pre-increment count before either sets a TTL, and if the
process dies between the two calls, the counter is left with no expiry
at all and effectively never resets. A Lua script closes both gaps —
Redis runs it as a single atomic unit, so no other command can interleave.

bucket.py, alongside this file, is F8's per-queue token bucket — a
different algorithm for a different problem (smoothing dispatch
throughput, not rejecting auth abuse) — not built here.
"""

import redis.asyncio as redis

_INCR_AND_EXPIRE = """
local current = redis.call('INCR', KEYS[1])
if tonumber(current) == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""


async def check_rate_limit(
    client: redis.Redis, key: str, *, limit: int, window_seconds: int
) -> bool:
    """True if this request is allowed, False if the caller should be
    rejected. Fixed window: a key like "login:ip:1.2.3.4" accumulates a
    count that resets window_seconds after its first hit in the window."""
    current = await client.eval(_INCR_AND_EXPIRE, 1, key, window_seconds)
    return int(current) <= limit
