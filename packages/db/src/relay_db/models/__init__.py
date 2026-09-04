"""Importing this package registers every model on Base.metadata.

SQLAlchemy only registers a class with the declarative Base when its
module actually executes. migrations/env.py imports Base for
target_metadata — it must also import this package, or autogenerate
would silently see zero tables and think the schema is already empty.
"""

from relay_db.models.api_key import ApiKey
from relay_db.models.attempt import JobAttempt
from relay_db.models.audit import AuditLog
from relay_db.models.base import Base
from relay_db.models.handler_schema import HandlerSchema
from relay_db.models.idempotency import IdempotencyKey
from relay_db.models.invitation import Invitation
from relay_db.models.job import Job
from relay_db.models.membership import Membership, OrgMembership
from relay_db.models.organization import Organization
from relay_db.models.project import Project
from relay_db.models.queue import Queue
from relay_db.models.refresh_token import RefreshToken
from relay_db.models.user import User

__all__ = [
    "ApiKey",
    "JobAttempt",
    "AuditLog",
    "Base",
    "Invitation",
    "HandlerSchema",
    "IdempotencyKey",
    "Job",
    "Membership",
    "OrgMembership",
    "Organization",
    "Project",
    "Queue",
    "RefreshToken",
    "User",
]
