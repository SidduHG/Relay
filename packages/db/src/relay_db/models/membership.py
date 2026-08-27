import uuid
from datetime import datetime

from relay_domain.enums.role import OrgRole, Role
from sqlalchemy import DateTime, Enum, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from relay_db.models.base import Base

# sa.Enum(SomeEnum) defaults to storing the member's .name ("OWNER"), not
# its .value ("org_owner") — verified this live before writing these
# models. values_callable overrides that, so the column actually stores
# the same string the domain layer and RANK dicts use.
_org_role_type = Enum(
    OrgRole, name="org_role", values_callable=lambda enum_cls: [e.value for e in enum_cls]
)
_project_role_type = Enum(
    Role, name="project_role", values_callable=lambda enum_cls: [e.value for e in enum_cls]
)


class OrgMembership(Base):
    __tablename__ = "org_memberships"
    __table_args__ = (UniqueConstraint("user_id", "org_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[OrgRole] = mapped_column(_org_role_type)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Membership(Base):
    """Role lives on this row, never on User — the same person can be
    OrgOwner of one org and Viewer of a single project inside a different
    org they hold no admin power in at all."""

    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "project_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[Role] = mapped_column(_project_role_type)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
