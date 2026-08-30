"""RELAY-SPEC.md F1: "Login and key-auth endpoints get their own
aggressive rate limit." Two limiters, deliberately shaped differently
around what's actually being defended against:

Login rate-limits EVERY attempt, success or failure, on two independent
keys: per-IP (stops one source spraying many accounts) and per-email
(stops many sources — a botnet — targeting one specific account; a
per-IP-only limit would never trip for a distributed attack). A real
user never logs in 20 times in 5 minutes, so limiting every attempt
costs nothing for legitimate use.

API-key verification rate-limits only FAILURES, per-IP. Legitimate SDK
traffic authenticates on every request and is expected to be frequent
and successful — limiting every attempt would throttle real usage. What
this defends against is specifically an attacker rapidly presenting
guessed key strings; a wrong key increments the counter, a valid one
never does.
"""

from fastapi import Request
from relay_redis.keys import (
    api_key_failure_rate_limit_key,
    login_email_rate_limit_key,
    login_ip_rate_limit_key,
)
from relay_redis.rate_limit.limiter import check_rate_limit

LOGIN_PER_IP_LIMIT = 20
LOGIN_PER_IP_WINDOW_SECONDS = 300
LOGIN_PER_EMAIL_LIMIT = 5
LOGIN_PER_EMAIL_WINDOW_SECONDS = 300

API_KEY_FAILURE_PER_IP_LIMIT = 20
API_KEY_FAILURE_PER_IP_WINDOW_SECONDS = 60


class RateLimitExceededError(Exception):
    pass


def _client_ip(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"


async def enforce_login_rate_limit(request: Request, email: str) -> None:
    redis_client = request.app.state.redis
    ip = _client_ip(request)

    ip_allowed = await check_rate_limit(
        redis_client,
        login_ip_rate_limit_key(ip),
        limit=LOGIN_PER_IP_LIMIT,
        window_seconds=LOGIN_PER_IP_WINDOW_SECONDS,
    )
    if not ip_allowed:
        raise RateLimitExceededError("too many login attempts from this address")

    email_allowed = await check_rate_limit(
        redis_client,
        login_email_rate_limit_key(email),
        limit=LOGIN_PER_EMAIL_LIMIT,
        window_seconds=LOGIN_PER_EMAIL_WINDOW_SECONDS,
    )
    if not email_allowed:
        raise RateLimitExceededError("too many login attempts for this account")


async def enforce_api_key_failure_rate_limit(request: Request) -> None:
    redis_client = request.app.state.redis
    ip = _client_ip(request)

    allowed = await check_rate_limit(
        redis_client,
        api_key_failure_rate_limit_key(ip),
        limit=API_KEY_FAILURE_PER_IP_LIMIT,
        window_seconds=API_KEY_FAILURE_PER_IP_WINDOW_SECONDS,
    )
    if not allowed:
        raise RateLimitExceededError("too many failed authentication attempts from this address")
