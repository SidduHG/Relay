from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Queue:
    id: UUID
    project_id: UUID
    name: str
    max_attempts: int
    job_timeout_seconds: int
    lease_duration_seconds: int
    default_priority: int
    rate_limit_per_second: int | None
    max_depth: int | None
    paused_at: datetime | None
    paused_by: UUID | None
    created_at: datetime
    updated_at: datetime
