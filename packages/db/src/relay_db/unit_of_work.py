"""The tenant-scoping chokepoint.

RLS is the guarantee that holds even if this class has a bug — every
policy fails closed on its own. What this class adds is the other half
of RELAY-SPEC.md F1's "must handle": scoping enforced *below* the
middleware, meaning there is no path from "I have a session" to "I can
query" that skips setting a scope. A TenantUnitOfWork cannot be built
without an org_id, and every repository comes from it, not from a bare
session — so using RLS correctly isn't a discipline problem, it's the
only path that compiles.

One class handles both org-only and project-scoped work, not two. Every
project already carries its own org_id, so a project-scoped unit of work
sets both GUCs together; an org-level operation (list this org's
projects) just leaves project_id unset, which correctly makes every
project-scoped table invisible for that request — an org-level operation
has no business touching them anyway.

org_id is optional for the same reason project_id already was: signup
and login (services/auth_service.py) touch only users and refresh_tokens
— both global, with no RLS policy at all — and forcing them through a
throwaway org_id to satisfy this constructor would be worse than
useless: a meaningless UUID sitting in the constructor is exactly the
kind of thing that hides a real mistake later, if an org-scoped
operation ever got added to a signup flow and nobody noticed the org_id
was fake. Leaving it unset makes every org/project-scoped table
correctly invisible, the identical fail-closed behavior already proven
for an unset project_id.
"""

import uuid
from types import TracebackType

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from relay_db.repositories.api_keys import ApiKeyRepo
from relay_db.repositories.attempts import AttemptRepo
from relay_db.repositories.audit import AuditRepo
from relay_db.repositories.handler_schemas import HandlerSchemaRepo
from relay_db.repositories.idempotency import IdempotencyRepo
from relay_db.repositories.invitations import InvitationRepo
from relay_db.repositories.jobs import JobRepo
from relay_db.repositories.memberships import MembershipRepo, OrgMembershipRepo
from relay_db.repositories.projects import ProjectRepo
from relay_db.repositories.queues import QueueRepo
from relay_db.repositories.refresh_tokens import RefreshTokenRepo
from relay_db.repositories.users import UserRepo


class TenantUnitOfWork:
    def __init__(
        self,
        session: AsyncSession,
        *,
        org_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
    ) -> None:
        self.session = session
        self.org_id = org_id
        self.project_id = project_id

        self.users = UserRepo(self)
        self.org_memberships = OrgMembershipRepo(self)
        self.memberships = MembershipRepo(self)
        self.projects = ProjectRepo(self)
        self.refresh_tokens = RefreshTokenRepo(self)
        self.api_keys = ApiKeyRepo(self)
        self.invitations = InvitationRepo(self)
        self.audit = AuditRepo(self)
        self.queues = QueueRepo(self)
        self.jobs = JobRepo(self)
        self.attempts = AttemptRepo(self)
        self.idempotency = IdempotencyRepo(self)
        self.handler_schemas = HandlerSchemaRepo(self)

    async def __aenter__(self) -> "TenantUnitOfWork":
        # SET LOCAL rejects bind parameters outright — verified directly
        # while building bootstrap.py (asyncpg sends "$1", Postgres
        # errors: SET is a utility statement, never goes through
        # parameter binding). Interpolating is safe here specifically
        # because org_id/project_id are uuid.UUID, never raw user input:
        # str(UUID) always renders as the fixed hex-dash form.
        if self.org_id is not None:
            await self.session.execute(text(f"SET LOCAL app.org_id = '{self.org_id}'"))
        if self.project_id is not None:
            await self.session.execute(text(f"SET LOCAL app.project_id = '{self.project_id}'"))
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc_type is None:
            await self.session.commit()
        else:
            await self.session.rollback()
