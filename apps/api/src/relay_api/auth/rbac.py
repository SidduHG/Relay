"""Permission checks against an already-resolved role.

Deliberately not wired to FastAPI's Depends() yet — that needs a real
role to depend ON, and resolving "which role does this request's actor
hold" is Task 9's job (auth/tenancy.py), not built yet. These are plain
functions a future Depends() chain will call, the same way jwt.py and
api_keys.py raise plain exceptions rather than importing HTTPException:
the auth-logic layer stays decoupled from HTTP, and the route layer
decides what status code a denial becomes.
"""

from relay_domain.enums.role import OrgRole, Role

from relay_api.auth.permissions import ORG_ROLE_PERMISSIONS, ROLE_PERMISSIONS, Permission


class PermissionDeniedError(Exception):
    """The resolved role lacks one or more required permissions."""


def require_org(role: OrgRole, *required: Permission) -> OrgRole:
    granted = ORG_ROLE_PERMISSIONS[role]
    missing = set(required) - granted
    if missing:
        raise PermissionDeniedError(
            f"{role.value} is missing: {sorted(p.value for p in missing)}"
        )
    return role


def require_project(role: Role, *required: Permission) -> Role:
    granted = ROLE_PERMISSIONS[role]
    missing = set(required) - granted
    if missing:
        raise PermissionDeniedError(
            f"{role.value} is missing: {sorted(p.value for p in missing)}"
        )
    return role
