from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from relay_domain.enums.job_state import JobState


@dataclass(frozen=True, slots=True)
class Job:
    id: UUID
    created_at: datetime
    project_id: UUID
    queue_id: UUID
    queue_name: str
    handler: str
    payload: Any | None
    payload_ref: str | None
    payload_bytes: int
    metadata: dict[str, Any]
    state: JobState
    priority: int
    priority_effective: int
    attempt: int
    max_attempts: int
    timeout_seconds: int
    lease_seconds: int
    run_at: datetime | None
    redis_indexed_at: datetime | None
    enqueued_by_type: str
    enqueued_by_id: UUID
    updated_at: datetime
