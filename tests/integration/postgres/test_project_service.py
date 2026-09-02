"""Proves relay_api.services.project_service against real Postgres: the
full invite/accept flow at both scopes, self-grant with its audit
requirement, and every escalation guard from docs/auth/plan.md —
including the last-owner guard, which needs a multi-actor sequence to
exercise honestly (an owner can never act on their own role, so proving
"the sole owner cannot be demoted" requires a second owner to attempt
it, then verifying the guard fires once only one remains).
"""

import os
import uuid
from collections.abc import AsyncIterator

import pytest
from relay_api.auth.rbac import PermissionDeniedError
from relay_api.auth.tenancy import Identity, OrgContext, ProjectContext
from relay_api.services.project_service import (
    AlreadyAMemberError,
    EscalationError,
    InvitationEmailMismatchError,
    InvitationInvalidError,
    LastOwnerError,
    NotAnOrgMemberError,
    accept_invitation,
    change_org_role,
    change_project_role,
    invite_to_org,
    invite_to_project,
    remove_org_member,
    remove_project_member,
    self_grant_project_membership,
)
from relay_db.connection import create_engine, create_session_factory
from relay_db.models.audit import AuditLog
from relay_db.models.organization import Organization
from relay_db.models.user import User
from relay_db.unit_of_work import TenantUnitOfWork
from relay_domain.enums.role import OrgRole, Role
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@pytest.fixture
async def app_sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    url = os.environ.get("DATABASE_URL")
    if url is None:
        pytest.skip("DATABASE_URL not set — start the stack to run this suite")
    engine = create_engine(url)
    try:
        yield create_session_factory(engine)
    except OSError as exc:
        pytest.skip(f"Postgres not reachable: {exc}")
    finally:
        await engine.dispose()


@pytest.fixture
async def admin_sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    url = os.environ.get("DATABASE_ADMIN_URL")
    if url is None:
        pytest.skip("DATABASE_ADMIN_URL not set — start the stack to run this suite")
    engine = create_engine(url)
    try:
        yield create_session_factory(engine)
    except OSError as exc:
        pytest.skip(f"Postgres not reachable: {exc}")
    finally:
        await engine.dispose()


def org_ctx(user_id: uuid.UUID, org_id: uuid.UUID, role: OrgRole) -> OrgContext:
    return OrgContext(
        identity=Identity(kind="user", user_id=user_id, api_key_id=None),
        org_id=org_id,
        org_role=role,
    )


def proj_ctx(
    user_id: uuid.UUID, org_id: uuid.UUID, project_id: uuid.UUID, role: Role
) -> ProjectContext:
    return ProjectContext(
        identity=Identity(kind="user", user_id=user_id, api_key_id=None),
        org_id=org_id,
        project_id=project_id,
        role=role,
    )


async def _make_org_with_owner(
    sessions: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, User]:
    org_id = uuid.uuid4()
    async with sessions() as session, TenantUnitOfWork(session, org_id=org_id) as uow:
        uow.session.add(Organization(id=org_id, name="t", slug=str(org_id)))
        owner = await uow.users.create(email=f"{uuid.uuid4()}@x.com", password_hash="x" * 60)
        await uow.org_memberships.create(user_id=owner.id, role=OrgRole.OWNER)
    return org_id, owner


async def _add_org_member(
    sessions: async_sessionmaker[AsyncSession], org_id: uuid.UUID, role: OrgRole
) -> User:
    async with sessions() as session, TenantUnitOfWork(session) as uow:
        user = await uow.users.create(email=f"{uuid.uuid4()}@x.com", password_hash="x" * 60)
    async with sessions() as session, TenantUnitOfWork(session, org_id=org_id) as uow:
        await uow.org_memberships.create(user_id=user.id, role=role)
    return user


async def test_org_invite_escalation_guard(
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    org_id, owner = await _make_org_with_owner(app_sessions)
    admin = await _add_org_member(app_sessions, org_id, OrgRole.ADMIN)

    async with app_sessions() as session, TenantUnitOfWork(session, org_id=org_id) as uow:
        with pytest.raises(EscalationError):
            await invite_to_org(
                uow, org_ctx(admin.id, org_id, OrgRole.ADMIN), "x@x.com", OrgRole.OWNER
            )


async def test_org_invite_requires_permission(
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    org_id, owner = await _make_org_with_owner(app_sessions)
    member = await _add_org_member(app_sessions, org_id, OrgRole.MEMBER)

    async with app_sessions() as session, TenantUnitOfWork(session, org_id=org_id) as uow:
        with pytest.raises(PermissionDeniedError):
            await invite_to_org(
                uow, org_ctx(member.id, org_id, OrgRole.MEMBER), "x@x.com", OrgRole.MEMBER
            )


async def test_org_invite_accept_creates_membership_and_is_audited(
    app_sessions: async_sessionmaker[AsyncSession],
    admin_sessions: async_sessionmaker[AsyncSession],
) -> None:
    org_id, owner = await _make_org_with_owner(app_sessions)
    email = f"invitee-{uuid.uuid4()}@example.com"

    async with app_sessions() as session, TenantUnitOfWork(session, org_id=org_id) as uow:
        token = await invite_to_org(
            uow, org_ctx(owner.id, org_id, OrgRole.OWNER), email, OrgRole.ADMIN
        )

    async with app_sessions() as session, TenantUnitOfWork(session) as uow:
        invitee = await uow.users.create(email=email, password_hash="x" * 60)

    async with admin_sessions() as admin_s, app_sessions() as app_s:
        await accept_invitation(admin_s, app_s, token, invitee)

    async with app_sessions() as session, TenantUnitOfWork(session, org_id=org_id) as uow:
        membership = await uow.org_memberships.get(invitee.id)
        assert membership is not None
        assert membership.role == OrgRole.ADMIN

        audit_rows = (
            await uow.session.scalars(
                select(AuditLog).where(AuditLog.action == "org.member_invited")
            )
        ).all()
        assert any(row.target == email for row in audit_rows)


async def test_accept_invitation_rejects_email_mismatch(
    app_sessions: async_sessionmaker[AsyncSession],
    admin_sessions: async_sessionmaker[AsyncSession],
) -> None:
    org_id, owner = await _make_org_with_owner(app_sessions)
    async with app_sessions() as session, TenantUnitOfWork(session, org_id=org_id) as uow:
        token = await invite_to_org(
            uow, org_ctx(owner.id, org_id, OrgRole.OWNER), "intended@example.com", OrgRole.MEMBER
        )
    async with app_sessions() as session, TenantUnitOfWork(session) as uow:
        wrong_user = await uow.users.create(
            email=f"{uuid.uuid4()}@example.com", password_hash="x" * 60
        )

    async with admin_sessions() as admin_s, app_sessions() as app_s:
        with pytest.raises(InvitationEmailMismatchError):
            await accept_invitation(admin_s, app_s, token, wrong_user)


async def test_accept_invitation_rejects_reuse(
    app_sessions: async_sessionmaker[AsyncSession],
    admin_sessions: async_sessionmaker[AsyncSession],
) -> None:
    org_id, owner = await _make_org_with_owner(app_sessions)
    email = f"reuse-{uuid.uuid4()}@example.com"
    async with app_sessions() as session, TenantUnitOfWork(session, org_id=org_id) as uow:
        token = await invite_to_org(
            uow, org_ctx(owner.id, org_id, OrgRole.OWNER), email, OrgRole.MEMBER
        )
    async with app_sessions() as session, TenantUnitOfWork(session) as uow:
        invitee = await uow.users.create(email=email, password_hash="x" * 60)

    async with admin_sessions() as admin_s, app_sessions() as app_s:
        await accept_invitation(admin_s, app_s, token, invitee)

    async with admin_sessions() as admin_s, app_sessions() as app_s:
        with pytest.raises(InvitationInvalidError):
            await accept_invitation(admin_s, app_s, token, invitee)


async def test_project_invite_requires_invitee_to_already_be_an_org_member(
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    org_id, owner = await _make_org_with_owner(app_sessions)
    async with app_sessions() as session, TenantUnitOfWork(session, org_id=org_id) as uow:
        project = await uow.projects.create(name="t", slug=str(uuid.uuid4()))
    async with (
        app_sessions() as session,
        TenantUnitOfWork(session, org_id=org_id, project_id=project.id) as uow,
    ):
        await uow.memberships.create(user_id=owner.id, role=Role.OWNER)

    async with (
        app_sessions() as session,
        TenantUnitOfWork(session, org_id=org_id, project_id=project.id) as uow,
    ):
        with pytest.raises(NotAnOrgMemberError):
            await invite_to_project(
                uow,
                proj_ctx(owner.id, org_id, project.id, Role.OWNER),
                "stranger@example.com",
                Role.MEMBER,
            )


async def test_project_invite_accept_works_once_invitee_is_an_org_member(
    app_sessions: async_sessionmaker[AsyncSession],
    admin_sessions: async_sessionmaker[AsyncSession],
) -> None:
    org_id, owner = await _make_org_with_owner(app_sessions)
    async with app_sessions() as session, TenantUnitOfWork(session, org_id=org_id) as uow:
        project = await uow.projects.create(name="t", slug=str(uuid.uuid4()))
    async with (
        app_sessions() as session,
        TenantUnitOfWork(session, org_id=org_id, project_id=project.id) as uow,
    ):
        await uow.memberships.create(user_id=owner.id, role=Role.OWNER)

    newcomer = await _add_org_member(app_sessions, org_id, OrgRole.MEMBER)

    async with (
        app_sessions() as session,
        TenantUnitOfWork(session, org_id=org_id, project_id=project.id) as uow,
    ):
        token = await invite_to_project(
            uow, proj_ctx(owner.id, org_id, project.id, Role.OWNER), newcomer.email, Role.MEMBER
        )

    async with admin_sessions() as admin_s, app_sessions() as app_s:
        await accept_invitation(admin_s, app_s, token, newcomer)

    async with (
        app_sessions() as session,
        TenantUnitOfWork(session, org_id=org_id, project_id=project.id) as uow,
    ):
        membership = await uow.memberships.get(newcomer.id)
        assert membership is not None
        assert membership.role == Role.MEMBER


async def test_self_grant_creates_membership_and_is_audited(
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    org_id, owner = await _make_org_with_owner(app_sessions)
    async with app_sessions() as session, TenantUnitOfWork(session, org_id=org_id) as uow:
        project = await uow.projects.create(name="t", slug=str(uuid.uuid4()))

    admin = await _add_org_member(app_sessions, org_id, OrgRole.ADMIN)

    async with app_sessions() as session, TenantUnitOfWork(session, org_id=org_id) as uow:
        await self_grant_project_membership(
            uow, org_ctx(admin.id, org_id, OrgRole.ADMIN), project.id, Role.ADMIN
        )

    async with (
        app_sessions() as session,
        TenantUnitOfWork(session, org_id=org_id, project_id=project.id) as uow,
    ):
        membership = await uow.memberships.get(admin.id)
        assert membership is not None
        assert membership.role == Role.ADMIN

    async with app_sessions() as session, TenantUnitOfWork(session, org_id=org_id) as uow:
        audit_rows = (
            await uow.session.scalars(
                select(AuditLog).where(AuditLog.action == "project.self_granted")
            )
        ).all()
        assert len(audit_rows) == 1


async def test_self_grant_twice_is_rejected(
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    org_id, owner = await _make_org_with_owner(app_sessions)
    async with app_sessions() as session, TenantUnitOfWork(session, org_id=org_id) as uow:
        project = await uow.projects.create(name="t", slug=str(uuid.uuid4()))
    admin = await _add_org_member(app_sessions, org_id, OrgRole.ADMIN)

    async with app_sessions() as session, TenantUnitOfWork(session, org_id=org_id) as uow:
        await self_grant_project_membership(
            uow, org_ctx(admin.id, org_id, OrgRole.ADMIN), project.id, Role.ADMIN
        )

    async with app_sessions() as session, TenantUnitOfWork(session, org_id=org_id) as uow:
        with pytest.raises(AlreadyAMemberError):
            await self_grant_project_membership(
                uow, org_ctx(admin.id, org_id, OrgRole.ADMIN), project.id, Role.ADMIN
            )


async def test_cannot_change_own_org_role_or_remove_self(
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    org_id, owner = await _make_org_with_owner(app_sessions)

    async with app_sessions() as session, TenantUnitOfWork(session, org_id=org_id) as uow:
        with pytest.raises(EscalationError):
            await change_org_role(
                uow, org_ctx(owner.id, org_id, OrgRole.OWNER), owner.id, OrgRole.ADMIN
            )

    async with app_sessions() as session, TenantUnitOfWork(session, org_id=org_id) as uow:
        with pytest.raises(EscalationError):
            await remove_org_member(uow, org_ctx(owner.id, org_id, OrgRole.OWNER), owner.id)


async def test_last_org_owner_cannot_be_demoted_or_removed(
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Needs two owners to exercise honestly: an owner can never act on
    their own role, so a second owner demotes the first down to one
    owner total, then a third actor's attempt on that sole owner must
    hit the guard."""
    org_id, owner1 = await _make_org_with_owner(app_sessions)
    owner2 = await _add_org_member(app_sessions, org_id, OrgRole.OWNER)

    async with app_sessions() as session, TenantUnitOfWork(session, org_id=org_id) as uow:
        await change_org_role(
            uow, org_ctx(owner1.id, org_id, OrgRole.OWNER), owner2.id, OrgRole.ADMIN
        )

    async with app_sessions() as session, TenantUnitOfWork(session, org_id=org_id) as uow:
        with pytest.raises(LastOwnerError):
            await change_org_role(
                uow, org_ctx(owner2.id, org_id, OrgRole.ADMIN), owner1.id, OrgRole.ADMIN
            )

    async with app_sessions() as session, TenantUnitOfWork(session, org_id=org_id) as uow:
        with pytest.raises(LastOwnerError):
            await remove_org_member(uow, org_ctx(owner2.id, org_id, OrgRole.ADMIN), owner1.id)


async def test_last_project_owner_cannot_be_demoted_or_removed(
    app_sessions: async_sessionmaker[AsyncSession],
) -> None:
    org_id, owner1 = await _make_org_with_owner(app_sessions)
    async with app_sessions() as session, TenantUnitOfWork(session, org_id=org_id) as uow:
        project = await uow.projects.create(name="t", slug=str(uuid.uuid4()))

    owner2 = await _add_org_member(app_sessions, org_id, OrgRole.MEMBER)
    async with (
        app_sessions() as session,
        TenantUnitOfWork(session, org_id=org_id, project_id=project.id) as uow,
    ):
        await uow.memberships.create(user_id=owner1.id, role=Role.OWNER)
        await uow.memberships.create(user_id=owner2.id, role=Role.OWNER)

    async with (
        app_sessions() as session,
        TenantUnitOfWork(session, org_id=org_id, project_id=project.id) as uow,
    ):
        await change_project_role(
            uow, proj_ctx(owner1.id, org_id, project.id, Role.OWNER), owner2.id, Role.ADMIN
        )

    async with (
        app_sessions() as session,
        TenantUnitOfWork(session, org_id=org_id, project_id=project.id) as uow,
    ):
        with pytest.raises(LastOwnerError):
            await change_project_role(
                uow, proj_ctx(owner2.id, org_id, project.id, Role.ADMIN), owner1.id, Role.ADMIN
            )

    async with (
        app_sessions() as session,
        TenantUnitOfWork(session, org_id=org_id, project_id=project.id) as uow,
    ):
        with pytest.raises(LastOwnerError):
            await remove_project_member(
                uow, proj_ctx(owner2.id, org_id, project.id, Role.ADMIN), owner1.id
            )
