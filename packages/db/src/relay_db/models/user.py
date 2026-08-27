import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from relay_db.models.base import Base


class User(Base):
    """Global — no org_id. One account can belong to many organizations
    through OrgMembership; see docs/auth/plan.md."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    # bcrypt's own output format is always exactly 60 chars; a longer value
    # here would mean something wrote a hash from a different algorithm.
    password_hash: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
