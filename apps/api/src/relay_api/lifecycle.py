"""FastAPI startup/shutdown orchestration.

Two engines exist here, briefly, for one reason: bootstrap needs elevated
access (see config.py's database_admin_url), everything after it doesn't
and shouldn't have that access. The admin engine lives only for the
duration of bootstrap and is disposed immediately after.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from relay_db.bootstrap import ensure_default_organization
from relay_db.connection import create_engine, create_session_factory

from relay_api.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    admin_engine = create_engine(settings.database_admin_url)
    admin_sessions = create_session_factory(admin_engine)
    async with admin_sessions() as session:
        org = await ensure_default_organization(
            session, name=settings.default_org_name, slug=settings.default_org_slug
        )
    await admin_engine.dispose()
    logger.info("startup complete", extra={"org_id": str(org.id), "org_slug": org.slug})

    engine = create_engine(settings.database_url)
    app.state.db_sessions = create_session_factory(engine)

    yield

    await engine.dispose()
