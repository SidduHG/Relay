import uuid
from datetime import datetime

from relay_domain.enums.attempt_outcome import AttemptOutcome
from sqlalchemy import DateTime, Enum, Integer, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from relay_db.models.base import Base


class JobAttempt(Base):
    __tablename__ = "job_attempts"
    __table_args__ = ({"postgresql_partition_by": "RANGE (created_at)"},)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, server_default=func.now()
    )
    project_id: Mapped[uuid.UUID] = mapped_column()
    job_id: Mapped[uuid.UUID] = mapped_column()
    attempt_number: Mapped[int] = mapped_column(SmallInteger)
    worker_id: Mapped[str | None] = mapped_column(String(255))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    outcome: Mapped[AttemptOutcome] = mapped_column(
        Enum(AttemptOutcome, name="attempt_outcome", values_callable=lambda e: [x.value for x in e])
    )
    error_class: Mapped[str | None] = mapped_column(String(255))
    error_message: Mapped[str | None] = mapped_column(Text)
    error_stack: Mapped[str | None] = mapped_column(Text)
    error_category: Mapped[str | None] = mapped_column(String(30))
    retry_after_seconds: Mapped[int | None] = mapped_column(Integer)
