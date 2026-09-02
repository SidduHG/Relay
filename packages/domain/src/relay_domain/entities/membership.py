"""The two membership shapes: org-level and project-level.

A user's role is never a global property of the user — it's a property of
*this* membership row. The same person can be OrgOwner of one
organization and hold no membership at all in another; ProjectOwner of
one project and Viewer of a different project in the same org.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from relay_domain.enums.role import OrgRole, Role


@dataclass(frozen=True, slots=True)
class OrgMembership:
    id: UUID
    user_id: UUID
    org_id: UUID
    role: OrgRole
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Membership:
    id: UUID
    user_id: UUID
    project_id: UUID
    role: Role
    created_at: datetime
