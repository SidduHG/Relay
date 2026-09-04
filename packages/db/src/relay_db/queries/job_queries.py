"""Stable cursor pagination for the partitioned jobs read model."""

import base64
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from relay_domain.enums.job_state import JobState
from sqlalchemy import Select, select, tuple_

from relay_db.models.job import Job
from relay_db.unit_of_work import TenantUnitOfWork


class InvalidCursorError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class JobFilters:
    state: JobState | None = None
    handler: str | None = None
    queue: str | None = None
    from_time: datetime | None = None
    to_time: datetime | None = None


@dataclass(frozen=True, slots=True)
class JobPage:
    items: list[Job]
    next_cursor: str | None
    has_more: bool


def _fingerprint(filters: JobFilters) -> str:
    values = {
        "from": filters.from_time.isoformat() if filters.from_time else None,
        "handler": filters.handler,
        "queue": filters.queue,
        "state": filters.state.value if filters.state else None,
        "to": filters.to_time.isoformat() if filters.to_time else None,
    }
    raw = json.dumps(values, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:8]


def _micros(value: datetime) -> int:
    aware = value if value.tzinfo else value.replace(tzinfo=UTC)
    delta = aware.astimezone(UTC) - datetime(1970, 1, 1, tzinfo=UTC)
    return (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds


def encode_cursor(created_at: datetime, job_id: uuid.UUID, filters: JobFilters) -> str:
    value = f"v1:{_micros(created_at)}:{job_id}:{_fingerprint(filters)}"
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def decode_cursor(cursor: str, filters: JobFilters) -> tuple[datetime, uuid.UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        version, micros, job_id, fingerprint = base64.urlsafe_b64decode(padded).decode().split(":")
        if version != "v1" or fingerprint != _fingerprint(filters):
            raise InvalidCursorError("cursor does not match these filters")
        created = datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=int(micros))
        return created, uuid.UUID(job_id)
    except InvalidCursorError:
        raise
    except (ValueError, UnicodeDecodeError) as exc:
        raise InvalidCursorError("invalid job cursor") from exc


def _with_filters(statement: Select[tuple[Job]], filters: JobFilters) -> Select[tuple[Job]]:
    if filters.state is not None:
        statement = statement.where(Job.state == filters.state)
    if filters.handler is not None:
        statement = statement.where(Job.handler == filters.handler)
    if filters.queue is not None:
        statement = statement.where(Job.queue_name == filters.queue)
    if filters.from_time is not None:
        statement = statement.where(Job.created_at >= filters.from_time)
    if filters.to_time is not None:
        statement = statement.where(Job.created_at <= filters.to_time)
    return statement


async def list_jobs(
    uow: TenantUnitOfWork,
    *,
    filters: JobFilters,
    limit: int,
    cursor: str | None = None,
) -> JobPage:
    if not 1 <= limit <= 200:
        raise ValueError("limit must be between 1 and 200")
    statement = _with_filters(select(Job), filters)
    if cursor:
        created_at, job_id = decode_cursor(cursor, filters)
        statement = statement.where(tuple_(Job.created_at, Job.id) < (created_at, job_id))
    result = await uow.session.scalars(
        statement.order_by(Job.created_at.desc(), Job.id.desc()).limit(limit + 1)
    )
    rows = list(result.all())
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = (
        encode_cursor(items[-1].created_at, items[-1].id, filters) if has_more and items else None
    )
    return JobPage(items=items, next_cursor=next_cursor, has_more=has_more)
