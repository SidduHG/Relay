"""Two different token shapes for two different jobs.

An access token proves identity on every request. It's deliberately
short-lived and stateless — a signed JWT, verified locally with no DB
round trip, so it stays fast on the hot path.

A refresh token exchanges for a new access token. It's deliberately
opaque and stateful — a random string (packages/security/secrets.py),
hashed at rest, checked against refresh_tokens. Statefulness is the
whole point: a stateless token can't be revoked before it expires, and
reuse detection needs somewhere to record "this one was already spent."

Every function that cares about time takes an explicit `now` parameter
instead of reading the clock itself, defaulting to the real time. Tests
inject a fixed or past `now` directly — no monkeypatching PyJWT or the
system clock required to prove an expired token is rejected.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import jwt
from relay_security.hashing import hash_token
from relay_security.secrets import generate_url_token

if TYPE_CHECKING:
    from relay_db.unit_of_work import TenantUnitOfWork

ACCESS_TOKEN_TTL = timedelta(minutes=15)
REFRESH_TOKEN_TTL = timedelta(days=30)
_ALGORITHM = "HS256"


class InvalidAccessTokenError(Exception):
    """Expired, tampered, or malformed access token."""


class InvalidRefreshTokenError(Exception):
    """Unknown, expired, or already-revoked refresh token."""


class RefreshTokenReuseError(Exception):
    """An already-rotated refresh token was presented again — a stolen-
    token signal. The caller's whole family has already been revoked by
    the time this is raised."""


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str


def issue_access_token(
    user_id: uuid.UUID, *, secret_key: str, now: datetime | None = None
) -> str:
    issued_at = now or datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": issued_at,
        "exp": issued_at + ACCESS_TOKEN_TTL,
    }
    return jwt.encode(payload, secret_key, algorithm=_ALGORITHM)


def verify_access_token(token: str, *, secret_key: str) -> uuid.UUID:
    try:
        payload = jwt.decode(token, secret_key, algorithms=[_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise InvalidAccessTokenError(str(exc)) from exc
    return uuid.UUID(payload["sub"])


async def issue_pair(
    uow: "TenantUnitOfWork",
    user_id: uuid.UUID,
    *,
    secret_key: str,
    family_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> TokenPair:
    """family_id absent means a fresh login — start a new rotation chain.
    Present means this call is part of an existing chain (rotation)."""
    current_time = now or datetime.now(UTC)
    refresh_secret = generate_url_token()
    await uow.refresh_tokens.create(
        user_id=user_id,
        family_id=family_id or uuid.uuid4(),
        token_hash=hash_token(refresh_secret),
        expires_at=current_time + REFRESH_TOKEN_TTL,
    )
    access_token = issue_access_token(user_id, secret_key=secret_key, now=current_time)
    return TokenPair(access_token=access_token, refresh_token=refresh_secret)


async def rotate(
    uow: "TenantUnitOfWork",
    presented_refresh_token: str,
    *,
    secret_key: str,
    now: datetime | None = None,
) -> TokenPair:
    """docs/auth/plan.md's refresh rotation, with reuse detection: if an
    already-rotated token is presented, the entire family is revoked and
    the caller must log in again. Raises rather than assuming an HTTP
    context — the route layer (Task 11) is what turns these into 401s.
    """
    current_time = now or datetime.now(UTC)
    row = await uow.refresh_tokens.get_by_hash(hash_token(presented_refresh_token))

    if row is None or row.revoked_at is not None or row.expires_at < current_time:
        raise InvalidRefreshTokenError("refresh token is unknown, expired, or revoked")

    if row.used_at is not None:
        await uow.refresh_tokens.revoke_family(row.family_id, now=current_time)
        # Commit immediately, before raising. Verified this matters: if a
        # caller catches RefreshTokenReuseError outside its own `async
        # with TenantUnitOfWork` block — a natural place to catch it, at
        # the HTTP layer — __aexit__ sees the exception propagate and
        # rolls back, silently undoing this revocation. That would mean
        # a replayed, already-detected stolen token still gets rejected
        # (this function still raises) but its family stays valid in the
        # database — the opposite of what reuse detection exists for.
        # This write is security-critical and must survive regardless of
        # what the caller does with the exception afterward.
        await uow.session.commit()
        raise RefreshTokenReuseError("refresh token was already used")

    await uow.refresh_tokens.mark_used(row.id, now=current_time)
    return await issue_pair(
        uow, row.user_id, secret_key=secret_key, family_id=row.family_id, now=current_time
    )
