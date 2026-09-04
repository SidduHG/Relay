import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from relay_db.models.base import Base


class Queue(Base):
    __tablename__ = "queues"
    __table_args__ = (
        UniqueConstraint("project_id", "name"),
        CheckConstraint("name ~ '^[a-z0-9][a-z0-9_-]{0,62}$'", name="name_valid"),
        CheckConstraint("max_attempts BETWEEN 1 AND 25", name="max_attempts_valid"),
        CheckConstraint("job_timeout_seconds BETWEEN 1 AND 86400", name="timeout_valid"),
        CheckConstraint("lease_duration_seconds BETWEEN 10 AND 3600", name="lease_valid"),
        CheckConstraint("default_priority BETWEEN 0 AND 3", name="priority_valid"),
        CheckConstraint(
            "rate_limit_per_second IS NULL OR rate_limit_per_second >= 1", name="rate_valid"
        ),
        CheckConstraint("max_depth IS NULL OR max_depth >= 1", name="depth_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(63))
    max_attempts: Mapped[int] = mapped_column(SmallInteger, default=5)
    job_timeout_seconds: Mapped[int] = mapped_column(Integer, default=300)
    lease_duration_seconds: Mapped[int] = mapped_column(Integer, default=60)
    default_priority: Mapped[int] = mapped_column(SmallInteger, default=2)
    rate_limit_per_second: Mapped[int | None] = mapped_column(Integer)
    max_depth: Mapped[int | None] = mapped_column(Integer)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paused_by: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
