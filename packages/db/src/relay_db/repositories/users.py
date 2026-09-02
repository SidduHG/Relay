"""Users are global — see relay_domain's User entity docstring — so this
repository, unlike every other one in this package, reads and writes
without any tenant scope at all. It still lives behind the UnitOfWork
for one reason: every repository comes from the same place, so calling
code never has to know which ones happen to be scoped.
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select

from relay_db.models.user import User

if TYPE_CHECKING:
    from relay_db.unit_of_work import TenantUnitOfWork


class UserRepo:
    def __init__(self, uow: "TenantUnitOfWork") -> None:
        self._uow = uow

    async def get_by_email(self, email: str) -> User | None:
        found: User | None = await self._uow.session.scalar(
            select(User).where(User.email == email)
        )
        return found

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        found: User | None = await self._uow.session.scalar(select(User).where(User.id == user_id))
        return found

    async def create(self, *, email: str, password_hash: str) -> User:
        user = User(id=uuid.uuid4(), email=email, password_hash=password_hash)
        self._uow.session.add(user)
        await self._uow.session.flush()
        return user
