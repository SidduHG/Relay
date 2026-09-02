"""org_id-scoped. Reads rely on RLS alone (a query for another org's
project simply returns nothing); create() still has to supply org_id
explicitly — RLS validates a write, it doesn't populate columns for you.
"""

import uuid
from collections.abc import Sequence
from typing import TYPE_CHECKING

from sqlalchemy import select

from relay_db.models.project import Project

if TYPE_CHECKING:
    from relay_db.unit_of_work import TenantUnitOfWork


class ProjectRepo:
    def __init__(self, uow: "TenantUnitOfWork") -> None:
        self._uow = uow

    async def get(self, project_id: uuid.UUID) -> Project | None:
        found: Project | None = await self._uow.session.scalar(
            select(Project).where(Project.id == project_id)
        )
        return found

    async def list_all(self) -> Sequence[Project]:
        result = await self._uow.session.scalars(select(Project))
        return result.all()

    async def create(self, *, name: str, slug: str) -> Project:
        project = Project(id=uuid.uuid4(), org_id=self._uow.org_id, name=name, slug=slug)
        self._uow.session.add(project)
        await self._uow.session.flush()
        return project
