import uuid
from datetime import datetime

from relay_domain.enums.role import OrgRole, Role
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from relay_db.models.base import Base

# role is polymorphic: an org invite (project_id IS NULL) carries an
# OrgRole value, a project invite carries a Role value — two different
# enum types, so this can't be a single native Postgres ENUM column the
# way OrgMembership/Membership's role columns are. Built from the actual
# enums rather than hand-typed, so it can't drift out of sync with them.
_valid_roles = sorted({r.value for r in Role} | {r.value for r in OrgRole})
_role_check_sql = "role IN (" + ", ".join(f"'{r}'" for r in _valid_roles) + ")"


class Invitation(Base):
    """Single-use, hashed at rest, 7-day expiry, bound to one email.
    project_id NULL means an org invite; set means a project invite."""

    __tablename__ = "invitations"
    # naming convention already prepends "ck_invitations_" to this
    __table_args__ = (CheckConstraint(_role_check_sql, name="role_valid"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(320), index=True)
    role: Mapped[str] = mapped_column(String(20))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
