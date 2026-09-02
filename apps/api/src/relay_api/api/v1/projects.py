"""Orgs, projects, members, invitations.

Deliberately no "create organization" route: RELAY-SPEC.md is
self-hosted, one org per deployment, and bootstrap.py already creates
the sole org at startup. Adding one now would be scope nothing in F1
asks for.
"""

import uuid

from fastapi import APIRouter, Depends
from relay_api.api.deps import (
    get_admin_session,
    get_app_session,
    get_current_user,
    get_org_context,
    get_project_context,
    require_org_permission,
)
from relay_api.auth.permissions import Permission
from relay_api.auth.tenancy import OrgContext, ProjectContext
from relay_api.schemas.project import (
    AcceptInvitationRequest,
    InvitationTokenOut,
    OrgInviteRequest,
    OrgRoleChangeRequest,
    ProjectCreateRequest,
    ProjectInviteRequest,
    ProjectOut,
    ProjectRoleChangeRequest,
    SelfGrantRequest,
)
from relay_api.services.project_service import accept_invitation as accept_invitation_service
from relay_api.services.project_service import (
    change_org_role,
    change_project_role,
    remove_org_member,
    remove_project_member,
)
from relay_api.services.project_service import invite_to_org as invite_to_org_service
from relay_api.services.project_service import invite_to_project as invite_to_project_service
from relay_api.services.project_service import (
    self_grant_project_membership as self_grant_service,
)
from relay_db.models.user import User
from relay_db.unit_of_work import TenantUnitOfWork
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["projects"])


@router.post("/v1/orgs/{org_id}/projects", response_model=ProjectOut, status_code=201)
async def create_project(
    org_id: uuid.UUID,
    body: ProjectCreateRequest,
    ctx: OrgContext = Depends(require_org_permission(Permission.ORG_CREATE_PROJECT)),
    app_session: AsyncSession = Depends(get_app_session),
) -> ProjectOut:
    async with TenantUnitOfWork(app_session, org_id=ctx.org_id) as uow:
        project = await uow.projects.create(name=body.name, slug=body.slug)
    return ProjectOut.model_validate(project)


@router.get("/v1/orgs/{org_id}/projects", response_model=list[ProjectOut])
async def list_projects(
    org_id: uuid.UUID,
    ctx: OrgContext = Depends(get_org_context),
    app_session: AsyncSession = Depends(get_app_session),
) -> list[ProjectOut]:
    # A read, not gated by a specific Permission — belonging to the org
    # (resolve_org_context already enforced that) is enough to see what
    # projects exist in it; org_role only governs org-level mutations.
    async with TenantUnitOfWork(app_session, org_id=ctx.org_id) as uow:
        projects = await uow.projects.list_all()
    return [ProjectOut.model_validate(p) for p in projects]


@router.post("/v1/orgs/{org_id}/invitations", response_model=InvitationTokenOut, status_code=201)
async def invite_to_org(
    org_id: uuid.UUID,
    body: OrgInviteRequest,
    ctx: OrgContext = Depends(get_org_context),
    app_session: AsyncSession = Depends(get_app_session),
) -> InvitationTokenOut:
    async with TenantUnitOfWork(app_session, org_id=ctx.org_id) as uow:
        token = await invite_to_org_service(uow, ctx, body.email, body.role)
    return InvitationTokenOut(token=token)


@router.post(
    "/v1/projects/{project_id}/invitations", response_model=InvitationTokenOut, status_code=201
)
async def invite_to_project(
    project_id: uuid.UUID,
    body: ProjectInviteRequest,
    ctx: ProjectContext = Depends(get_project_context),
    app_session: AsyncSession = Depends(get_app_session),
) -> InvitationTokenOut:
    async with TenantUnitOfWork(
        app_session, org_id=ctx.org_id, project_id=ctx.project_id
    ) as uow:
        token = await invite_to_project_service(uow, ctx, body.email, body.role)
    return InvitationTokenOut(token=token)


@router.post("/v1/invitations/accept", status_code=204)
async def accept_invitation(
    body: AcceptInvitationRequest,
    user: User = Depends(get_current_user),
    admin_session: AsyncSession = Depends(get_admin_session),
    app_session: AsyncSession = Depends(get_app_session),
) -> None:
    await accept_invitation_service(admin_session, app_session, body.token, user)


@router.post("/v1/orgs/{org_id}/self-grant", status_code=204)
async def self_grant_project_membership(
    org_id: uuid.UUID,
    body: SelfGrantRequest,
    ctx: OrgContext = Depends(get_org_context),
    app_session: AsyncSession = Depends(get_app_session),
) -> None:
    async with TenantUnitOfWork(app_session, org_id=ctx.org_id) as uow:
        await self_grant_service(uow, ctx, body.project_id, body.role)


@router.patch("/v1/orgs/{org_id}/members/{user_id}", status_code=204)
async def change_org_member_role(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    body: OrgRoleChangeRequest,
    ctx: OrgContext = Depends(get_org_context),
    app_session: AsyncSession = Depends(get_app_session),
) -> None:
    async with TenantUnitOfWork(app_session, org_id=ctx.org_id) as uow:
        await change_org_role(uow, ctx, user_id, body.role)


@router.delete("/v1/orgs/{org_id}/members/{user_id}", status_code=204)
async def remove_org_member_route(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    ctx: OrgContext = Depends(get_org_context),
    app_session: AsyncSession = Depends(get_app_session),
) -> None:
    async with TenantUnitOfWork(app_session, org_id=ctx.org_id) as uow:
        await remove_org_member(uow, ctx, user_id)


@router.patch("/v1/projects/{project_id}/members/{user_id}", status_code=204)
async def change_project_member_role(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    body: ProjectRoleChangeRequest,
    # Plain context, not require_project_permission: change_project_role
    # already enforces PROJECT_CHANGE_MEMBER_ROLE itself (Task 10), right
    # alongside the escalation guards it lives next to — gating here too
    # would just recheck the identical permission a second time.
    ctx: ProjectContext = Depends(get_project_context),
    app_session: AsyncSession = Depends(get_app_session),
) -> None:
    async with TenantUnitOfWork(
        app_session, org_id=ctx.org_id, project_id=ctx.project_id
    ) as uow:
        await change_project_role(uow, ctx, user_id, body.role)


@router.delete("/v1/projects/{project_id}/members/{user_id}", status_code=204)
async def remove_project_member_route(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    ctx: ProjectContext = Depends(get_project_context),
    app_session: AsyncSession = Depends(get_app_session),
) -> None:
    async with TenantUnitOfWork(
        app_session, org_id=ctx.org_id, project_id=ctx.project_id
    ) as uow:
        await remove_project_member(uow, ctx, user_id)
