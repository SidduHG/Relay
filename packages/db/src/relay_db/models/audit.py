import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from relay_db.models.base import Base


class AuditLog(Base):
    """Append-only. org_id is never nullable — every audited action
    belongs to an organization; project_id is nullable because org-level
    actions (inviting an org member, creating a project) have none.

    project_id cascades to SET NULL rather than CASCADE: deleting a
    project must not erase the history of what happened in it."""

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    # "user" | "api_key" | "staff" — staff is a seam for the platform-admin
    # tier deliberately excluded from F1 (RELAY-SPEC.md out-of-scope list).
    actor_type: Mapped[str] = mapped_column(String(20))
    # Polymorphic: points at users.id or api_keys.id depending on
    # actor_type. No FK — a single column can't reference two tables.
    actor_id: Mapped[uuid.UUID] = mapped_column()
    action: Mapped[str] = mapped_column(String(100), index=True)
    target: Mapped[str] = mapped_column(String(255))
    # `metadata` is a reserved attribute name on every SQLAlchemy
    # declarative model (it holds the table's own Column/Table registry) —
    # verified this raises InvalidRequestError before choosing this name.
    # The Python attribute is `extra`; the actual DB column stays `metadata`.
    extra: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, default=dict)
    ip: Mapped[str | None] = mapped_column(String(45))  # 45 = longest possible IPv6 literal
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
