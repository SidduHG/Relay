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
import os
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import unquote, urlparse

from fastapi import FastAPI
from relay_db.bootstrap import ensure_default_organization
from relay_db.connection import create_engine, create_session_factory
from relay_redis.connection import create_redis_client
from relay_redis.queues import QueueConfigCache
from relay_storage import LocalBlobStore

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

    app.state.redis = create_redis_client(settings.redis_url)
    parsed_store = urlparse(settings.blob_store_url)
    if parsed_store.scheme != "file":
        raise ValueError("F2 supports only file:// blob_store_url values")
    store_path = unquote(parsed_store.path)
    if os.name == "nt" and re.match(r"^/[A-Za-z]:", store_path):
        store_path = store_path[1:]
    app.state.blob_store = LocalBlobStore(Path(store_path))
    app.state.queue_config_cache = QueueConfigCache(settings.queue_config_cache_seconds)

    yield

    await admin_engine.dispose()
    await engine.dispose()
    await app.state.redis.aclose()
