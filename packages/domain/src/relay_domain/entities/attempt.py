from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from relay_domain.enums.attempt_outcome import AttemptOutcome


@dataclass(frozen=True, slots=True)
class Attempt:
    id: UUID
    created_at: datetime
    project_id: UUID
    job_id: UUID
    attempt_number: int
    worker_id: str | None
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None
    outcome: AttemptOutcome
    error_class: str | None
    error_message: str | None
    error_stack: str | None
    error_category: str | None
    retry_after_seconds: int | None
