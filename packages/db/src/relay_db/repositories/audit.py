"""Write-only, org_id-scoped. Only what Task 10's mutating operations
need to satisfy their own audit requirement (docs/auth/plan.md: an org
role self-grant "is an audited event") — reads, filtering, and the
dashboard view are Task 13's job, not built here.
"""

import uuid
from typing import TYPE_CHECKING

from relay_db.models.audit import AuditLog

if TYPE_CHECKING:
    from relay_db.unit_of_work import TenantUnitOfWork


class AuditRepo:
    def __init__(self, uow: "TenantUnitOfWork") -> None:
        self._uow = uow

    async def write(
        self,
        *,
        actor_type: str,
        actor_id: uuid.UUID,
        action: str,
        target: str,
        project_id: uuid.UUID | None = None,
        extra: dict[str, object] | None = None,
    ) -> AuditLog:
        if self._uow.org_id is None:
            raise ValueError("AuditRepo.write requires an org-scoped UnitOfWork")
        entry = AuditLog(
            id=uuid.uuid4(),
            org_id=self._uow.org_id,
            project_id=project_id,
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            target=target,
            extra=extra or {},
        )
        self._uow.session.add(entry)
        await self._uow.session.flush()
        return entry
