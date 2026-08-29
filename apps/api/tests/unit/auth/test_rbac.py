import pytest
from relay_api.auth.permissions import Permission
from relay_api.auth.rbac import PermissionDeniedError, require_org, require_project
from relay_domain.enums.role import OrgRole, Role


def test_require_org_returns_the_role_when_permitted() -> None:
    assert require_org(OrgRole.OWNER, Permission.ORG_DELETE) == OrgRole.OWNER


def test_require_org_raises_when_missing_a_permission() -> None:
    with pytest.raises(PermissionDeniedError):
        require_org(OrgRole.ADMIN, Permission.ORG_DELETE)


def test_require_project_returns_the_role_when_permitted() -> None:
    assert require_project(Role.MEMBER, Permission.JOB_ENQUEUE) == Role.MEMBER


def test_require_project_raises_when_missing_a_permission() -> None:
    with pytest.raises(PermissionDeniedError):
        require_project(Role.VIEWER, Permission.JOB_ENQUEUE)


def test_require_project_needs_every_listed_permission_not_just_one() -> None:
    """AND semantics: a role missing even one of several required
    permissions is denied, not partially approved."""
    with pytest.raises(PermissionDeniedError):
        require_project(Role.MEMBER, Permission.JOB_ENQUEUE, Permission.QUEUE_PAUSE)

    # sanity: the same role passes when only the permissions it does hold are required
    require_project(Role.MEMBER, Permission.JOB_ENQUEUE, Permission.JOB_CANCEL)
