import uuid
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from relay_db.models.handler_schema import HandlerSchema

if TYPE_CHECKING:
    from relay_db.unit_of_work import TenantUnitOfWork


class HandlerSchemaRepo:
    def __init__(self, uow: "TenantUnitOfWork") -> None:
        self._uow = uow

    async def get(self, handler: str) -> HandlerSchema | None:
        found: HandlerSchema | None = await self._uow.session.scalar(
            select(HandlerSchema).where(HandlerSchema.handler == handler)
        )
        return found

    async def list_all(self) -> Sequence[HandlerSchema]:
        result = await self._uow.session.scalars(
            select(HandlerSchema).order_by(HandlerSchema.handler)
        )
        return result.all()

    async def put(self, handler: str, schema: dict[str, Any]) -> HandlerSchema:
        if self._uow.project_id is None:
            raise ValueError("HandlerSchemaRepo requires a project-scoped UnitOfWork")
        statement = (
            insert(HandlerSchema)
            .values(
                id=uuid.uuid4(),
                project_id=self._uow.project_id,
                handler=handler,
                schema=schema,
            )
            .on_conflict_do_update(
                index_elements=[HandlerSchema.project_id, HandlerSchema.handler],
                set_={"schema": schema},
            )
            .returning(HandlerSchema)
        )
        result = await self._uow.session.scalar(statement)
        assert result is not None
        return result

    async def delete(self, handler: str) -> bool:
        result = await self._uow.session.execute(
            delete(HandlerSchema).where(HandlerSchema.handler == handler)
        )
        return bool(result.rowcount)  # type: ignore[attr-defined]
