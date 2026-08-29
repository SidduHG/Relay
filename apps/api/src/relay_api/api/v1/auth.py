"""Signup, login, refresh, logout, and API key CRUD.

API keys are grouped in this file per the plan's file table, but the
routes themselves live under /v1/projects/{project_id}/api-keys — a key
is a project sub-resource, so the URL says so even though the file that
defines it is here.
"""

import uuid

from fastapi import APIRouter, Depends
from relay_api.api.deps import (
    get_app_session,
    get_current_user,
    require_project_permission,
)
from relay_api.auth.api_keys import issue_api_key, revoke_api_key
from relay_api.auth.jwt import logout as jwt_logout
from relay_api.auth.jwt import rotate
from relay_api.auth.permissions import Permission
from relay_api.auth.tenancy import ProjectContext
from relay_api.config import settings
from relay_api.schemas.auth import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    LoginRequest,
    RefreshRequest,
    SignupRequest,
    TokenPairOut,
    UserOut,
)
from relay_api.services.auth_service import login as login_service
from relay_api.services.auth_service import signup as signup_service
from relay_db.models.user import User
from relay_db.unit_of_work import TenantUnitOfWork
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/v1/auth", tags=["auth"])
api_keys_router = APIRouter(prefix="/v1/projects/{project_id}/api-keys", tags=["api-keys"])


@router.post("/signup", response_model=UserOut, status_code=201)
async def signup(
    body: SignupRequest, app_session: AsyncSession = Depends(get_app_session)
) -> UserOut:
    async with TenantUnitOfWork(app_session) as uow:
        user = await signup_service(uow, body.email, body.password)
    return UserOut.model_validate(user)


@router.post("/login", response_model=TokenPairOut)
async def login(
    body: LoginRequest, app_session: AsyncSession = Depends(get_app_session)
) -> TokenPairOut:
    async with TenantUnitOfWork(app_session) as uow:
        pair = await login_service(
            uow, body.email, body.password, secret_key=settings.api_secret_key
        )
    return TokenPairOut(access_token=pair.access_token, refresh_token=pair.refresh_token)


@router.post("/refresh", response_model=TokenPairOut)
async def refresh(
    body: RefreshRequest, app_session: AsyncSession = Depends(get_app_session)
) -> TokenPairOut:
    async with TenantUnitOfWork(app_session) as uow:
        pair = await rotate(uow, body.refresh_token, secret_key=settings.api_secret_key)
    return TokenPairOut(access_token=pair.access_token, refresh_token=pair.refresh_token)


@router.post("/logout", status_code=204)
async def logout(
    body: RefreshRequest, app_session: AsyncSession = Depends(get_app_session)
) -> None:
    async with TenantUnitOfWork(app_session) as uow:
        await jwt_logout(uow, body.refresh_token)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)


@api_keys_router.post("", response_model=ApiKeyCreateResponse, status_code=201)
async def create_api_key(
    body: ApiKeyCreateRequest,
    ctx: ProjectContext = Depends(require_project_permission(Permission.API_KEY_CREATE)),
    app_session: AsyncSession = Depends(get_app_session),
) -> ApiKeyCreateResponse:
    async with TenantUnitOfWork(
        app_session, org_id=ctx.org_id, project_id=ctx.project_id
    ) as uow:
        issued = await issue_api_key(uow, name=body.name)
    return ApiKeyCreateResponse(
        id=issued.record.id, secret=issued.secret, prefix=issued.record.prefix, name=body.name
    )


@api_keys_router.delete("/{key_id}", status_code=204)
async def delete_api_key(
    key_id: uuid.UUID,
    ctx: ProjectContext = Depends(require_project_permission(Permission.API_KEY_REVOKE)),
    app_session: AsyncSession = Depends(get_app_session),
) -> None:
    async with TenantUnitOfWork(
        app_session, org_id=ctx.org_id, project_id=ctx.project_id
    ) as uow:
        await revoke_api_key(uow, key_id)
