"""Two repos, two scopes — matching OrgMembership (org_id) and
Membership (project_id) being genuinely different tables with different
RLS policies. Role always lives on the membership row, never on User;
see relay_domain's Membership entity docstring for why.
"""

import uuid
from collections.abc import Sequence
from typing import TYPE_CHECKING

from relay_domain.enums.role import OrgRole, Role
from sqlalchemy import delete as sa_delete
from sqlalchemy import select, update

from relay_db.models.membership import Membership, OrgMembership

if TYPE_CHECKING:
    from relay_db.unit_of_work import TenantUnitOfWork


class OrgMembershipRepo:
    def __init__(self, uow: "TenantUnitOfWork") -> None:
        self._uow = uow

    async def get(self, user_id: uuid.UUID) -> OrgMembership | None:
        found: OrgMembership | None = await self._uow.session.scalar(
            select(OrgMembership).where(OrgMembership.user_id == user_id)
        )
        return found

    async def create(self, *, user_id: uuid.UUID, role: OrgRole) -> OrgMembership:
        membership = OrgMembership(
            id=uuid.uuid4(), user_id=user_id, org_id=self._uow.org_id, role=role
        )
        self._uow.session.add(membership)
        await self._uow.session.flush()
        return membership

    async def list_all(self) -> Sequence[OrgMembership]:
        result = await self._uow.session.scalars(select(OrgMembership))
        return result.all()

    async def update_role(self, user_id: uuid.UUID, role: OrgRole) -> None:
        await self._uow.session.execute(
            update(OrgMembership).where(OrgMembership.user_id == user_id).values(role=role)
        )

    async def delete(self, user_id: uuid.UUID) -> None:
        await self._uow.session.execute(
            sa_delete(OrgMembership).where(OrgMembership.user_id == user_id)
        )


class MembershipRepo:
    def __init__(self, uow: "TenantUnitOfWork") -> None:
        self._uow = uow

    async def get(self, user_id: uuid.UUID) -> Membership | None:
        found: Membership | None = await self._uow.session.scalar(
            select(Membership).where(Membership.user_id == user_id)
        )
        return found

    async def create(self, *, user_id: uuid.UUID, role: Role) -> Membership:
        if self._uow.project_id is None:
            # Reads fail closed on their own (RLS returns nothing for an
            # org-only scope) — but a write has to supply a real value
            # for the NOT NULL project_id column, and there's no
            # correct one to guess. Fail loud instead of guessing.
            raise ValueError("MembershipRepo.create requires a project-scoped UnitOfWork")
        membership = Membership(
            id=uuid.uuid4(), user_id=user_id, project_id=self._uow.project_id, role=role
        )
        self._uow.session.add(membership)
        await self._uow.session.flush()
        return membership

    async def list_all(self) -> Sequence[Membership]:
        result = await self._uow.session.scalars(select(Membership))
        return result.all()

    async def update_role(self, user_id: uuid.UUID, role: Role) -> None:
        await self._uow.session.execute(
            update(Membership).where(Membership.user_id == user_id).values(role=role)
        )

    async def delete(self, user_id: uuid.UUID) -> None:
        await self._uow.session.execute(
            sa_delete(Membership).where(Membership.user_id == user_id)
        )
