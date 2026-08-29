"""Org and project membership: invite, accept, self-grant, role change,
remove — every escalation guard from docs/auth/plan.md in one place.

accept_invitation deliberately requires an already-authenticated user
(their User row, resolved by the caller from a valid session), not an
email+password of its own: RELAY-SPEC.md never asks for signup-during-
accept, and every mainstream implementation of this flow (GitHub, Slack)
already requires signing up separately first, then accepting while
logged in. Building a second signup path here would be speculative
scope, not something the spec or a concrete requirement asked for.

Every mutating function here writes an audit_log entry — pulled in now
from Task 13's scope specifically because the plan states the org
self-grant "is an audited event" as a safety property of the capability
itself, not an add-on; shipping self-grant without it would leave the
one guard the design explicitly relies on unbuilt. Reads, filtering, and
the dashboard view stay Task 13's job.
"""

import uuid
from datetime import UTC, datetime, timedelta

from relay_api.auth.permissions import Permission
from relay_api.auth.rbac import require_org, require_project
from relay_api.auth.tenancy import OrgContext, ProjectContext
from relay_db.models.invitation import Invitation
from relay_db.models.user import User
from relay_db.unit_of_work import TenantUnitOfWork
from relay_domain.enums.role import ORG_RANK, RANK, OrgRole, Role
from relay_security.hashing import hash_token
from relay_security.secrets import generate_url_token
from relay_security.validation import is_valid_email, normalize_email
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

INVITATION_TTL = timedelta(days=7)


class InvalidEmailError(Exception):
    pass


class EscalationError(Exception):
    """Attempted to grant a role above the actor's own, or to change/
    remove the actor's own membership."""


class LastOwnerError(Exception):
    """Would leave zero Owners (project) or OrgOwners (org) — an
    orphaned tenant nobody can administer."""


class NotAMemberError(Exception):
    """The target has no membership row to change or remove."""


class NotAnOrgMemberError(Exception):
    """A project invite's target must already belong to the org."""


class InvitationInvalidError(Exception):
    """Unknown token, expired, or already accepted."""


class InvitationEmailMismatchError(Exception):
    """The accepting user's email does not match the invitation."""


class AlreadyAMemberError(Exception):
    pass


# --- invitations -------------------------------------------------------


async def invite_to_org(uow: TenantUnitOfWork, actor: OrgContext, email: str, role: OrgRole) -> str:
    require_org(actor.org_role, Permission.ORG_INVITE_MEMBER)
    if ORG_RANK[role] > ORG_RANK[actor.org_role]:
        raise EscalationError("cannot grant a role above your own")

    normalized = normalize_email(email)
    if not is_valid_email(normalized):
        raise InvalidEmailError(email)

    token = generate_url_token()
    now = datetime.now(UTC)
    await uow.invitations.create(
        project_id=None,
        email=normalized,
        role=role.value,
        token_hash=hash_token(token),
        expires_at=now + INVITATION_TTL,
    )
    await uow.audit.write(
        actor_type="user",
        actor_id=uuid.UUID(str(actor.identity.user_id)),
        action="org.member_invited",
        target=normalized,
        extra={"role": role.value},
    )
    return token


async def invite_to_project(
    uow: TenantUnitOfWork, actor: ProjectContext, email: str, role: Role
) -> str:
    require_project(actor.role, Permission.PROJECT_INVITE_MEMBER)
    if RANK[role] > RANK[actor.role]:
        raise EscalationError("cannot grant a role above your own")

    normalized = normalize_email(email)
    if not is_valid_email(normalized):
        raise InvalidEmailError(email)

    invitee = await uow.users.get_by_email(normalized)
    if invitee is None or await uow.org_memberships.get(invitee.id) is None:
        raise NotAnOrgMemberError(normalized)

    token = generate_url_token()
    now = datetime.now(UTC)
    await uow.invitations.create(
        project_id=actor.project_id,
        email=normalized,
        role=role.value,
        token_hash=hash_token(token),
        expires_at=now + INVITATION_TTL,
    )
    await uow.audit.write(
        actor_type="user",
        actor_id=uuid.UUID(str(actor.identity.user_id)),
        action="project.member_invited",
        target=normalized,
        project_id=actor.project_id,
        extra={"role": role.value},
    )
    return token


async def _find_invitation_by_token(admin_session: AsyncSession, token: str) -> Invitation | None:
    """Pre-tenant lookup, same reasoning as verify_api_key: invitations
    is RLS-scoped by org_id, and the accepting user has only a token —
    no org context to scope a normal connection by yet."""
    found: Invitation | None = await admin_session.scalar(
        select(Invitation).where(Invitation.token_hash == hash_token(token))
    )
    return found


async def accept_invitation(
    admin_session: AsyncSession,
    app_session: AsyncSession,
    token: str,
    accepting_user: User,
    *,
    now: datetime | None = None,
) -> None:
    current_time = now or datetime.now(UTC)
    invitation = await _find_invitation_by_token(admin_session, token)
    if (
        invitation is None
        or invitation.accepted_at is not None
        or invitation.expires_at < current_time
    ):
        raise InvitationInvalidError("token is unknown, expired, or already accepted")

    if invitation.email != normalize_email(accepting_user.email):
        raise InvitationEmailMismatchError("invitation was issued to a different email")

    if invitation.project_id is None:
        async with TenantUnitOfWork(app_session, org_id=invitation.org_id) as uow:
            if await uow.org_memberships.get(accepting_user.id) is not None:
                raise AlreadyAMemberError()
            await uow.org_memberships.create(
                user_id=accepting_user.id, role=OrgRole(invitation.role)
            )
            await uow.invitations.mark_accepted(invitation.id, now=current_time)
    else:
        async with TenantUnitOfWork(
            app_session, org_id=invitation.org_id, project_id=invitation.project_id
        ) as uow:
            if await uow.memberships.get(accepting_user.id) is not None:
                raise AlreadyAMemberError()
            await uow.memberships.create(user_id=accepting_user.id, role=Role(invitation.role))
            await uow.invitations.mark_accepted(invitation.id, now=current_time)


async def self_grant_project_membership(
    uow: TenantUnitOfWork, actor: OrgContext, project_id: uuid.UUID, role: Role
) -> None:
    """docs/auth/plan.md: an OrgAdmin/OrgOwner can add themselves to a
    project they created, but only to themselves — never to anyone
    else, and only ever audited."""
    require_org(actor.org_role, Permission.ORG_SELF_GRANT_PROJECT_MEMBERSHIP)
    actor_user_id = actor.identity.user_id
    assert actor_user_id is not None  # OrgContext is user-identity only, see tenancy.py

    async with TenantUnitOfWork(
        uow.session, org_id=actor.org_id, project_id=project_id
    ) as project_uow:
        if await project_uow.memberships.get(actor_user_id) is not None:
            raise AlreadyAMemberError()
        await project_uow.memberships.create(user_id=actor_user_id, role=role)
        await project_uow.audit.write(
            actor_type="user",
            actor_id=actor_user_id,
            action="project.self_granted",
            target=str(project_id),
            project_id=project_id,
            extra={"role": role.value},
        )


# --- role changes and removal ------------------------------------------


async def change_org_role(
    uow: TenantUnitOfWork, actor: OrgContext, target_user_id: uuid.UUID, new_role: OrgRole
) -> None:
    require_org(actor.org_role, Permission.ORG_INVITE_MEMBER)  # same tier as invite/remove
    if target_user_id == actor.identity.user_id:
        raise EscalationError("cannot change your own role")
    if ORG_RANK[new_role] > ORG_RANK[actor.org_role]:
        raise EscalationError("cannot grant a role above your own")

    current = await uow.org_memberships.get(target_user_id)
    if current is None:
        raise NotAMemberError()

    if current.role == OrgRole.OWNER and new_role != OrgRole.OWNER:
        owners = [m for m in await uow.org_memberships.list_all() if m.role == OrgRole.OWNER]
        if len(owners) <= 1:
            raise LastOwnerError()

    await uow.org_memberships.update_role(target_user_id, new_role)
    await uow.audit.write(
        actor_type="user",
        actor_id=uuid.UUID(str(actor.identity.user_id)),
        action="org.member_role_changed",
        target=str(target_user_id),
        extra={"new_role": new_role.value},
    )


async def remove_org_member(
    uow: TenantUnitOfWork, actor: OrgContext, target_user_id: uuid.UUID
) -> None:
    require_org(actor.org_role, Permission.ORG_REMOVE_MEMBER)
    if target_user_id == actor.identity.user_id:
        raise EscalationError("cannot remove yourself")

    current = await uow.org_memberships.get(target_user_id)
    if current is None:
        raise NotAMemberError()

    if current.role == OrgRole.OWNER:
        owners = [m for m in await uow.org_memberships.list_all() if m.role == OrgRole.OWNER]
        if len(owners) <= 1:
            raise LastOwnerError()

    await uow.org_memberships.delete(target_user_id)
    await uow.audit.write(
        actor_type="user",
        actor_id=uuid.UUID(str(actor.identity.user_id)),
        action="org.member_removed",
        target=str(target_user_id),
    )


async def change_project_role(
    uow: TenantUnitOfWork, actor: ProjectContext, target_user_id: uuid.UUID, new_role: Role
) -> None:
    require_project(actor.role, Permission.PROJECT_CHANGE_MEMBER_ROLE)
    if target_user_id == actor.identity.user_id:
        raise EscalationError("cannot change your own role")
    if RANK[new_role] > RANK[actor.role]:
        raise EscalationError("cannot grant a role above your own")

    current = await uow.memberships.get(target_user_id)
    if current is None:
        raise NotAMemberError()

    if current.role == Role.OWNER and new_role != Role.OWNER:
        owners = [m for m in await uow.memberships.list_all() if m.role == Role.OWNER]
        if len(owners) <= 1:
            raise LastOwnerError()

    await uow.memberships.update_role(target_user_id, new_role)
    await uow.audit.write(
        actor_type="user",
        actor_id=uuid.UUID(str(actor.identity.user_id)),
        action="project.member_role_changed",
        target=str(target_user_id),
        project_id=actor.project_id,
        extra={"new_role": new_role.value},
    )


async def remove_project_member(
    uow: TenantUnitOfWork, actor: ProjectContext, target_user_id: uuid.UUID
) -> None:
    require_project(actor.role, Permission.PROJECT_CHANGE_MEMBER_ROLE)
    if target_user_id == actor.identity.user_id:
        raise EscalationError("cannot remove yourself")

    current = await uow.memberships.get(target_user_id)
    if current is None:
        raise NotAMemberError()

    if current.role == Role.OWNER:
        owners = [m for m in await uow.memberships.list_all() if m.role == Role.OWNER]
        if len(owners) <= 1:
            raise LastOwnerError()

    await uow.memberships.delete(target_user_id)
    await uow.audit.write(
        actor_type="user",
        actor_id=uuid.UUID(str(actor.identity.user_id)),
        action="project.member_removed",
        target=str(target_user_id),
        project_id=actor.project_id,
    )
