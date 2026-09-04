import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class QueueOut(BaseModel):
    id: uuid.UUID
    name: str
    max_attempts: int
    job_timeout_seconds: int
    lease_duration_seconds: int
    default_priority: int
    rate_limit_per_second: int | None
    max_depth: int | None
    paused_at: datetime | None
    paused_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class QueueDefaultsPatch(BaseModel):
    max_attempts: int | None = Field(default=None, ge=1, le=25)
    job_timeout_seconds: int | None = Field(default=None, ge=1, le=86_400)
    lease_duration_seconds: int | None = Field(default=None, ge=10, le=3_600)
    default_priority: int | None = Field(default=None, ge=0, le=3)
    rate_limit_per_second: int | None = Field(default=None, ge=1)
    max_depth: int | None = Field(default=None, ge=1)


class PurgeTokenOut(BaseModel):
    token: str
    expires_at: datetime
    queue: str
    job_count: int


class PurgeOut(BaseModel):
    cancelled: int
    still_running: int


class HandlerSchemaIn(BaseModel):
    schema_: dict[str, Any] = Field(alias="schema")

    model_config = {"populate_by_name": True}


class HandlerSchemaOut(BaseModel):
    id: uuid.UUID
    handler: str
    schema_: dict[str, Any] = Field(alias="schema")
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}
