"""Engine and session factory construction.

Deliberately thin — apps own their own engine's lifetime (created at
startup, disposed at shutdown), this just knows how to build one from a
URL so that logic isn't duplicated between apps/api and apps/worker.
"""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # expire_on_commit=False: without it, every attribute read after a
    # commit triggers a fresh SELECT. Our session lifetime is short
    # (one request or one bootstrap call), so there's no staleness risk
    # worth paying that cost for.
    return async_sessionmaker(engine, expire_on_commit=False)
