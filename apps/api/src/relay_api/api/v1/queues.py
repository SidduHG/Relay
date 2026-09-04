import uuid

from fastapi import APIRouter, Depends, Query, Request
from relay_api.api.deps import get_app_session, require_project_permission
from relay_api.auth.permissions import Permission
from relay_api.auth.tenancy import ProjectContext
from relay_api.config import settings
from relay_api.schemas.queue import (
    HandlerSchemaIn,
    HandlerSchemaOut,
    PurgeOut,
    PurgeTokenOut,
    QueueDefaultsPatch,
    QueueOut,
)
from relay_api.services.queue_service import (
    change_pause,
    delete_handler_schema,
    get_queue,
    list_handler_schemas,
    list_queues,
    mint_purge_token,
    purge_queue,
    put_handler_schema,
    update_defaults,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/v1/projects/{project_id}", tags=["queues"])


@router.get("/queues", response_model=list[QueueOut])
async def list_queues_route(
    project_id: uuid.UUID,
    ctx: ProjectContext = Depends(require_project_permission(Permission.PROJECT_READ)),
    session: AsyncSession = Depends(get_app_session),
) -> list[QueueOut]:
    return [QueueOut.model_validate(item) for item in await list_queues(session, ctx)]


@router.get("/queues/{queue_name}", response_model=QueueOut)
async def get_queue_route(
    project_id: uuid.UUID,
    queue_name: str,
    ctx: ProjectContext = Depends(require_project_permission(Permission.PROJECT_READ)),
    session: AsyncSession = Depends(get_app_session),
) -> QueueOut:
    return QueueOut.model_validate(await get_queue(session, ctx, queue_name))


@router.patch("/queues/{queue_name}", response_model=QueueOut)
async def update_queue_route(
    project_id: uuid.UUID,
    queue_name: str,
    body: QueueDefaultsPatch,
    request: Request,
    ctx: ProjectContext = Depends(require_project_permission(Permission.QUEUE_EDIT_DEFAULTS)),
    session: AsyncSession = Depends(get_app_session),
) -> QueueOut:
    queue = await update_defaults(
        session,
        request.app.state.redis,
        request.app.state.queue_config_cache,
        ctx,
        queue_name,
        body.model_dump(exclude_unset=True),
    )
    return QueueOut.model_validate(queue)


@router.post("/queues/{queue_name}/pause", response_model=QueueOut)
async def pause_queue_route(
    project_id: uuid.UUID,
    queue_name: str,
    request: Request,
    ctx: ProjectContext = Depends(require_project_permission(Permission.QUEUE_PAUSE)),
    session: AsyncSession = Depends(get_app_session),
) -> QueueOut:
    return QueueOut.model_validate(
        await change_pause(session, request.app.state.redis, ctx, queue_name, paused=True)
    )


@router.post("/queues/{queue_name}/resume", response_model=QueueOut)
async def resume_queue_route(
    project_id: uuid.UUID,
    queue_name: str,
    request: Request,
    ctx: ProjectContext = Depends(require_project_permission(Permission.QUEUE_PAUSE)),
    session: AsyncSession = Depends(get_app_session),
) -> QueueOut:
    return QueueOut.model_validate(
        await change_pause(session, request.app.state.redis, ctx, queue_name, paused=False)
    )


@router.post("/queues/{queue_name}/purge-token", response_model=PurgeTokenOut)
async def purge_token_route(
    project_id: uuid.UUID,
    queue_name: str,
    request: Request,
    ctx: ProjectContext = Depends(require_project_permission(Permission.QUEUE_PURGE)),
    session: AsyncSession = Depends(get_app_session),
) -> PurgeTokenOut:
    token = await mint_purge_token(
        session,
        request.app.state.redis,
        ctx,
        queue_name,
        settings.purge_token_ttl_seconds,
    )
    return PurgeTokenOut(
        token=token.token,
        expires_at=token.expires_at,
        queue=token.queue,
        job_count=token.job_count,
    )


@router.delete("/queues/{queue_name}/jobs", response_model=PurgeOut)
async def purge_queue_route(
    project_id: uuid.UUID,
    queue_name: str,
    request: Request,
    confirm: str = Query(min_length=1),
    ctx: ProjectContext = Depends(require_project_permission(Permission.QUEUE_PURGE)),
    session: AsyncSession = Depends(get_app_session),
) -> PurgeOut:
    result = await purge_queue(session, request.app.state.redis, ctx, queue_name, confirm)
    return PurgeOut(cancelled=result.cancelled, still_running=result.still_running)


@router.get("/handler-schemas", response_model=list[HandlerSchemaOut])
async def list_handler_schemas_route(
    project_id: uuid.UUID,
    ctx: ProjectContext = Depends(require_project_permission(Permission.PROJECT_READ)),
    session: AsyncSession = Depends(get_app_session),
) -> list[HandlerSchemaOut]:
    return [
        HandlerSchemaOut.model_validate(value) for value in await list_handler_schemas(session, ctx)
    ]


@router.put("/handler-schemas/{handler}", response_model=HandlerSchemaOut)
async def put_handler_schema_route(
    project_id: uuid.UUID,
    handler: str,
    body: HandlerSchemaIn,
    ctx: ProjectContext = Depends(require_project_permission(Permission.QUEUE_EDIT_DEFAULTS)),
    session: AsyncSession = Depends(get_app_session),
) -> HandlerSchemaOut:
    return HandlerSchemaOut.model_validate(
        await put_handler_schema(session, ctx, handler, body.schema_)
    )


@router.delete("/handler-schemas/{handler}", status_code=204)
async def delete_handler_schema_route(
    project_id: uuid.UUID,
    handler: str,
    ctx: ProjectContext = Depends(require_project_permission(Permission.QUEUE_EDIT_DEFAULTS)),
    session: AsyncSession = Depends(get_app_session),
) -> None:
    await delete_handler_schema(session, ctx, handler)
