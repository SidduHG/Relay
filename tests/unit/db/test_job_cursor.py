from datetime import UTC, datetime
from uuid import UUID

import pytest
from relay_db.queries.job_queries import (
    InvalidCursorError,
    JobFilters,
    decode_cursor,
    encode_cursor,
)
from relay_domain.enums.job_state import JobState


def test_cursor_round_trips_exact_microseconds() -> None:
    created = datetime(2026, 9, 4, 12, 0, 0, 123456, tzinfo=UTC)
    job_id = UUID("00000000-0000-0000-0000-000000000001")
    filters = JobFilters(state=JobState.QUEUED, queue="emails")
    assert decode_cursor(encode_cursor(created, job_id, filters), filters) == (created, job_id)


def test_cursor_cannot_be_reused_with_different_filters() -> None:
    created = datetime(2026, 9, 4, tzinfo=UTC)
    job_id = UUID("00000000-0000-0000-0000-000000000001")
    cursor = encode_cursor(created, job_id, JobFilters(state=JobState.QUEUED))
    with pytest.raises(InvalidCursorError):
        decode_cursor(cursor, JobFilters(state=JobState.FAILED))
