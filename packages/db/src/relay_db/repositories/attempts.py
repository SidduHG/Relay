import uuid
from collections.abc import Sequence
from typing import TYPE_CHECKING

from sqlalchemy import select

from relay_db.models.attempt import JobAttempt

if TYPE_CHECKING:
    from relay_db.unit_of_work import TenantUnitOfWork


class AttemptRepo:
    def __init__(self, uow: "TenantUnitOfWork") -> None:
        self._uow = uow

    async def list_for_job(self, job_id: uuid.UUID) -> Sequence[JobAttempt]:
        result = await self._uow.session.scalars(
            select(JobAttempt)
            .where(JobAttempt.job_id == job_id)
            .order_by(JobAttempt.attempt_number)
        )
        return result.all()
