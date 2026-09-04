import uuid
from datetime import datetime
from typing import Any

from relay_domain.enums.job_state import JobState
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from relay_db.models.base import Base


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "(payload IS NULL) <> (payload_ref IS NULL)", name="payload_location_valid"
        ),
        CheckConstraint("priority BETWEEN 0 AND 3", name="priority_valid"),
        CheckConstraint("priority_effective BETWEEN 0 AND 3", name="effective_priority_valid"),
        CheckConstraint("attempt >= 0", name="attempt_valid"),
        CheckConstraint("payload_bytes >= 0", name="payload_bytes_valid"),
        {"postgresql_partition_by": "RANGE (created_at)"},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, server_default=func.now()
    )
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    queue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("queues.id", ondelete="RESTRICT"))
    queue_name: Mapped[str] = mapped_column(String(63))
    handler: Mapped[str] = mapped_column(String(255))
    handler_version: Mapped[str | None] = mapped_column(String(100))
    payload: Mapped[Any | None] = mapped_column(JSONB)
    payload_ref: Mapped[str | None] = mapped_column(Text)
    payload_bytes: Mapped[int] = mapped_column(Integer)
    extra: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    state: Mapped[JobState] = mapped_column(
        Enum(JobState, name="job_state", values_callable=lambda e: [x.value for x in e])
    )
    priority: Mapped[int] = mapped_column(SmallInteger)
    priority_effective: Mapped[int] = mapped_column(SmallInteger)
    attempt: Mapped[int] = mapped_column(SmallInteger, default=0)
    max_attempts: Mapped[int] = mapped_column(SmallInteger)
    timeout_seconds: Mapped[int] = mapped_column(Integer)
    lease_seconds: Mapped[int] = mapped_column(Integer)
    reclaim_count: Mapped[int] = mapped_column(SmallInteger, default=0)
    run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(255))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[Any | None] = mapped_column(JSONB)
    result_ref: Mapped[str | None] = mapped_column(Text)
    dependency_count: Mapped[int] = mapped_column(SmallInteger, default=0)
    replayed_from: Mapped[uuid.UUID | None] = mapped_column()
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(String(50))
    trace_id: Mapped[str | None] = mapped_column(String(32))
    span_id: Mapped[str | None] = mapped_column(String(16))
    trace_flags: Mapped[int | None] = mapped_column(SmallInteger)
    enqueued_by_type: Mapped[str] = mapped_column(String(20))
    enqueued_by_id: Mapped[uuid.UUID] = mapped_column()
    idempotency_key_hash: Mapped[str | None] = mapped_column(String(64))
    redis_indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
