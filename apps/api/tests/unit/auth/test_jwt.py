"""Access-token issuance and verification — no database involved, so
these run as plain unit tests. Every expiry case is driven by an
explicit `now` passed to issue_access_token, never by monkeypatching the
clock or PyJWT's internals: issue a token whose `now` is already in the
past, then verify it with the real clock and confirm it's expired.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from relay_api.auth.jwt import (
    ACCESS_TOKEN_TTL,
    InvalidAccessTokenError,
    issue_access_token,
    verify_access_token,
)

SECRET = "a" * 32  # HS256's own floor (RFC 7518 §3.2) — see config.py


def test_roundtrip_recovers_the_same_user_id() -> None:
    user_id = uuid.uuid4()
    token = issue_access_token(user_id, secret_key=SECRET)
    assert verify_access_token(token, secret_key=SECRET) == user_id


def test_wrong_secret_is_rejected() -> None:
    token = issue_access_token(uuid.uuid4(), secret_key=SECRET)
    with pytest.raises(InvalidAccessTokenError):
        verify_access_token(token, secret_key="b" * 32)


def test_expired_token_is_rejected() -> None:
    issued_in_the_past = datetime.now(UTC) - ACCESS_TOKEN_TTL - timedelta(seconds=1)
    token = issue_access_token(uuid.uuid4(), secret_key=SECRET, now=issued_in_the_past)
    with pytest.raises(InvalidAccessTokenError):
        verify_access_token(token, secret_key=SECRET)


def test_token_issued_now_is_not_yet_expired() -> None:
    """The boundary case for the fake-clock approach above: a token
    issued at the real 'now' must still verify — proves the expiry test
    is actually exercising the TTL, not a token that's always rejected."""
    token = issue_access_token(uuid.uuid4(), secret_key=SECRET)
    verify_access_token(token, secret_key=SECRET)  # must not raise


def test_malformed_token_is_rejected() -> None:
    with pytest.raises(InvalidAccessTokenError):
        verify_access_token("not-a-jwt-at-all", secret_key=SECRET)
