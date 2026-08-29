"""One Permission vocabulary, two role→permission matrices.

Every member here is grounded directly in a row of docs/auth/plan.md's
two tables — nothing invented beyond what the spec already lists. Rows
that bundle several verbs together for the table's readability ("Billing,
delete org, transfer org ownership") are split into distinct Permission
members: a route gating "delete this org" is a genuinely different check
than one gating "view billing," even though today only OrgOwner can do
either.
"""

from enum import StrEnum

from relay_domain.enums.role import OrgRole, Role


class Permission(StrEnum):
    # --- org-level (docs/auth/plan.md's org-level action table) ---
    ORG_MANAGE_BILLING = "org:manage_billing"
    ORG_DELETE = "org:delete"
    ORG_TRANSFER_OWNERSHIP = "org:transfer_ownership"
    ORG_CREATE_PROJECT = "org:create_project"
    ORG_DELETE_PROJECT = "org:delete_project"
    ORG_INVITE_MEMBER = "org:invite_member"
    ORG_REMOVE_MEMBER = "org:remove_member"
    ORG_SELF_GRANT_PROJECT_MEMBERSHIP = "org:self_grant_project_membership"

    # --- project-level (docs/auth/plan.md's project-level action table) ---
    PROJECT_READ = "project:read"
    JOB_ENQUEUE = "project:job_enqueue"
    JOB_CANCEL = "project:job_cancel"
    JOB_REPLAY = "project:job_replay"
    QUEUE_PAUSE = "project:queue_pause"
    QUEUE_PURGE = "project:queue_purge"
    QUEUE_EDIT_DEFAULTS = "project:queue_edit_defaults"
    API_KEY_CREATE = "project:api_key_create"
    API_KEY_REVOKE = "project:api_key_revoke"
    PROJECT_INVITE_MEMBER = "project:invite_member"
    PROJECT_CHANGE_MEMBER_ROLE = "project:change_member_role"
    PROJECT_DELETE = "project:delete"
    PROJECT_TRANSFER_OWNERSHIP = "project:transfer_ownership"


_ORG_OWNER_ONLY = frozenset(
    {Permission.ORG_MANAGE_BILLING, Permission.ORG_DELETE, Permission.ORG_TRANSFER_OWNERSHIP}
)
_ORG_ADMIN_AND_ABOVE = frozenset(
    {
        Permission.ORG_CREATE_PROJECT,
        Permission.ORG_DELETE_PROJECT,
        Permission.ORG_INVITE_MEMBER,
        Permission.ORG_REMOVE_MEMBER,
        Permission.ORG_SELF_GRANT_PROJECT_MEMBERSHIP,
    }
)

# Deliberately explicit dicts, not computed from rank: a matrix you can
# read top to bottom against the spec's own tables is easier to audit
# than one derived by set arithmetic, and test_permissions.py's
# monotonicity check catches drift between the two.
ORG_ROLE_PERMISSIONS: dict[OrgRole, frozenset[Permission]] = {
    OrgRole.OWNER: _ORG_OWNER_ONLY | _ORG_ADMIN_AND_ABOVE,
    OrgRole.ADMIN: _ORG_ADMIN_AND_ABOVE,
    OrgRole.MEMBER: frozenset(),
}

_PROJECT_OWNER_ONLY = frozenset({Permission.PROJECT_DELETE, Permission.PROJECT_TRANSFER_OWNERSHIP})
_PROJECT_ADMIN_AND_ABOVE = frozenset(
    {
        Permission.QUEUE_PAUSE,
        Permission.QUEUE_PURGE,
        Permission.QUEUE_EDIT_DEFAULTS,
        Permission.API_KEY_CREATE,
        Permission.API_KEY_REVOKE,
        Permission.PROJECT_INVITE_MEMBER,
        Permission.PROJECT_CHANGE_MEMBER_ROLE,
    }
)
_PROJECT_MEMBER_AND_ABOVE = frozenset(
    {Permission.JOB_ENQUEUE, Permission.JOB_CANCEL, Permission.JOB_REPLAY}
)
_PROJECT_VIEWER_AND_ABOVE = frozenset({Permission.PROJECT_READ})

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.OWNER: (
        _PROJECT_OWNER_ONLY
        | _PROJECT_ADMIN_AND_ABOVE
        | _PROJECT_MEMBER_AND_ABOVE
        | _PROJECT_VIEWER_AND_ABOVE
    ),
    Role.ADMIN: _PROJECT_ADMIN_AND_ABOVE | _PROJECT_MEMBER_AND_ABOVE | _PROJECT_VIEWER_AND_ABOVE,
    Role.MEMBER: _PROJECT_MEMBER_AND_ABOVE | _PROJECT_VIEWER_AND_ABOVE,
    Role.VIEWER: _PROJECT_VIEWER_AND_ABOVE,
}
