import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from relay_domain.enums.attempt_outcome import AttemptOutcome
from relay_domain.enums.job_state import JobState


class EnqueueRequest(BaseModel):
    handler: str = Field(min_length=1, max_length=255)
    payload: Any
    metadata: dict[str, Any] = Field(default_factory=dict)
    priority: int | None = Field(default=None, ge=0, le=3)
    run_at: datetime | None = None
    handler_version: str | None = Field(default=None, max_length=100)


class AttemptOut(BaseModel):
    id: uuid.UUID
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

    model_config = {"from_attributes": True}


class JobOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    queue: str
    handler: str
    handler_version: str | None
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
    cancel_requested_at: datetime | None
    created: bool | None = None
    indexed: bool
    attempts: list[AttemptOut] = Field(default_factory=list)


class CancelOut(BaseModel):
    job: JobOut
    pending: bool
