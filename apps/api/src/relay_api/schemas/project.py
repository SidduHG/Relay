import uuid
from datetime import datetime

from pydantic import BaseModel
from relay_domain.enums.role import OrgRole, Role


class ProjectCreateRequest(BaseModel):
    name: str
    slug: str


class ProjectOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    slug: str
    created_at: datetime

    model_config = {"from_attributes": True}


class OrgInviteRequest(BaseModel):
    email: str
    role: OrgRole


class ProjectInviteRequest(BaseModel):
    email: str
    role: Role


class InvitationTokenOut(BaseModel):
    """The raw invitation token — shown once, to whoever sent it, so it
    can be relayed to the invitee out of band (email delivery is
    RELAY-SPEC.md's own explicitly deferred concern)."""

    token: str


class AcceptInvitationRequest(BaseModel):
    token: str


class OrgRoleChangeRequest(BaseModel):
    role: OrgRole


class ProjectRoleChangeRequest(BaseModel):
    role: Role


class SelfGrantRequest(BaseModel):
    project_id: uuid.UUID
    role: Role
