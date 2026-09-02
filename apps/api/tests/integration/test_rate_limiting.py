"""Proves login and API-key rate limiting over real HTTP, against real
Postgres and real Redis. The primitive itself (fixed window, atomicity)
is already proven in tests/integration/redis/test_rate_limit.py; this
file proves the two limiters are wired to the right endpoints with the
right shape — login limits every attempt, API-key auth limits only
failures.

Same deferred-import pattern as test_http_e2e.py: relay_api.main builds
its Settings() singleton at import time, which needs the full app env.
"""

import os
import uuid
from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

REQUIRED_ENV = ["DATABASE_URL", "DATABASE_ADMIN_URL", "REDIS_URL", "API_SECRET_KEY"]


@pytest.fixture
def client() -> Iterator["TestClient"]:
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        pytest.skip(f"missing env for the full app: {', '.join(missing)}")

    import redis
    from fastapi.testclient import TestClient
    from relay_api.main import app

    try:
        redis.from_url(os.environ["REDIS_URL"]).ping()
    except redis.RedisError as exc:
        pytest.skip(f"Redis not reachable: {exc}")

    try:
        with TestClient(app) as test_client:
            yield test_client
    except OSError as exc:
        pytest.skip(f"Postgres not reachable: {exc}")


def test_login_per_email_limit_trips_after_repeated_attempts(client: "TestClient") -> None:
    email = f"{uuid.uuid4()}@example.com"
    client.post("/v1/auth/signup", json={"email": email, "password": "correct-horse-battery"})

    # Every attempt counts, success or failure — one deliberate correct
    # login first, matching real usage, then failures until it trips.
    statuses = [
        client.post(
            "/v1/auth/login", json={"email": email, "password": "correct-horse-battery"}
        ).status_code
    ]
    statuses += [
        client.post("/v1/auth/login", json={"email": email, "password": "wrong"}).status_code
        for _ in range(6)
    ]

    assert 429 in statuses
    # once tripped, it stays tripped for the rest of the window
    assert statuses[statuses.index(429) :] == [429] * len(statuses[statuses.index(429) :])


def test_valid_jwt_traffic_is_never_rate_limited(client: "TestClient") -> None:
    email = f"{uuid.uuid4()}@example.com"
    client.post("/v1/auth/signup", json={"email": email, "password": "correct-horse-battery"})
    resp = client.post("/v1/auth/login", json={"email": email, "password": "correct-horse-battery"})
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    statuses = {client.get("/v1/auth/me", headers=headers).status_code for _ in range(40)}
    assert statuses == {200}


def test_api_key_failures_eventually_trip_the_limiter_but_not_before(
    client: "TestClient",
) -> None:
    bad_headers = {"Authorization": "Bearer rly_live_" + "x" * 24}
    statuses = [client.get("/v1/auth/me", headers=bad_headers).status_code for _ in range(25)]

    assert statuses[:19] == [401] * 19
    assert 429 in statuses
