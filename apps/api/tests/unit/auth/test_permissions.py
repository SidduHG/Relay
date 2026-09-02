"""Structural drift guards for the two role->permission matrices,
mirroring tests/unit/domain/test_role.py's "every role has a rank"
pattern: a role added without a matching entry should fail here, at
test time, not as a KeyError on a live request.
"""

from relay_api.auth.permissions import ORG_ROLE_PERMISSIONS, ROLE_PERMISSIONS, Permission
from relay_domain.enums.role import ORG_RANK, RANK, OrgRole, Role


def test_every_org_role_has_a_permission_set() -> None:
    assert set(ORG_ROLE_PERMISSIONS) == set(OrgRole)


def test_every_project_role_has_a_permission_set() -> None:
    assert set(ROLE_PERMISSIONS) == set(Role)


def test_org_matrix_is_monotonic_by_rank() -> None:
    """A higher-ranked role must never lack a permission a lower-ranked
    one has — otherwise "owner can do anything admin can" silently
    breaks, and anything built on that assumption (a UI that hides an
    action based on rank alone, say) gets it wrong."""
    for higher in OrgRole:
        for lower in OrgRole:
            if ORG_RANK[higher] > ORG_RANK[lower]:
                assert ORG_ROLE_PERMISSIONS[lower] <= ORG_ROLE_PERMISSIONS[higher]


def test_project_matrix_is_monotonic_by_rank() -> None:
    for higher in Role:
        for lower in Role:
            if RANK[higher] > RANK[lower]:
                assert ROLE_PERMISSIONS[lower] <= ROLE_PERMISSIONS[higher]


def test_org_member_has_no_permissions() -> None:
    """docs/auth/plan.md's org-level table: every row is Owner/Admin
    only — OrgMember exists to belong, not to act."""
    assert ORG_ROLE_PERMISSIONS[OrgRole.MEMBER] == frozenset()


def test_only_org_owner_can_delete_the_organization() -> None:
    for role in OrgRole:
        has_it = Permission.ORG_DELETE in ORG_ROLE_PERMISSIONS[role]
        assert has_it == (role is OrgRole.OWNER)


def test_viewer_can_read_but_not_enqueue() -> None:
    assert Permission.PROJECT_READ in ROLE_PERMISSIONS[Role.VIEWER]
    assert Permission.JOB_ENQUEUE not in ROLE_PERMISSIONS[Role.VIEWER]


def test_only_owner_and_admin_can_pause_a_queue() -> None:
    for role in Role:
        has_it = Permission.QUEUE_PAUSE in ROLE_PERMISSIONS[role]
        assert has_it == (role in (Role.OWNER, Role.ADMIN))


def test_only_project_owner_can_delete_the_project() -> None:
    for role in Role:
        has_it = Permission.PROJECT_DELETE in ROLE_PERMISSIONS[role]
        assert has_it == (role is Role.OWNER)
