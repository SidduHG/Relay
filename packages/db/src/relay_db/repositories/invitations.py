"""org_id-scoped, like ProjectRepo — creating and listing invitations
is something an already-authenticated org admin does within their own
org. Finding an invitation BY TOKEN (accepting one) is a different,
pre-tenant operation: the accepting user has only a token, no org
context, and invitations is RLS-scoped by org_id — the same
self-referential problem Tasks 4, 7, and 9 all hit. That lookup lives
in services/project_service.py against a raw admin session, the same
pattern as verify_api_key, not here.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import update

from relay_db.models.invitation import Invitation

if TYPE_CHECKING:
    from relay_db.unit_of_work import TenantUnitOfWork


class InvitationRepo:
    def __init__(self, uow: "TenantUnitOfWork") -> None:
        self._uow = uow

    async def create(
        self,
        *,
        project_id: uuid.UUID | None,
        email: str,
        role: str,
        token_hash: str,
        expires_at: datetime,
    ) -> Invitation:
        if self._uow.org_id is None:
            raise ValueError("InvitationRepo.create requires an org-scoped UnitOfWork")
        invitation = Invitation(
            id=uuid.uuid4(),
            org_id=self._uow.org_id,
            project_id=project_id,
            email=email,
            role=role,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self._uow.session.add(invitation)
        await self._uow.session.flush()
        return invitation

    async def mark_accepted(self, invitation_id: uuid.UUID, *, now: datetime) -> None:
        await self._uow.session.execute(
            update(Invitation).where(Invitation.id == invitation_id).values(accepted_at=now)
        )
