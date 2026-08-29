"""FastAPI startup/shutdown orchestration.

Two engines live for the app's whole lifetime, not just bootstrap. The
admin engine was originally disposed right after bootstrap — but by
Task 11, verify_api_key, tenancy.py's project-context resolution (the
`projects` self-reference), and invitation-token lookup all need a live
admin session on every authenticated request, the same structural
pattern bootstrap.py hit with organizations. Every authenticated request
now opens both an admin session (briefly, for whichever pre-tenant
lookup it needs) and an app session (for the properly RLS-scoped work)
— two lightweight pooled connections, not two new TCP connections each
time.
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
    logger.info("startup complete", extra={"org_id": str(org.id), "org_slug": org.slug})

    app.state.admin_sessions = admin_sessions

    engine = create_engine(settings.database_url)
    app.state.db_sessions = create_session_factory(engine)

    yield

    await admin_engine.dispose()
    await engine.dispose()
