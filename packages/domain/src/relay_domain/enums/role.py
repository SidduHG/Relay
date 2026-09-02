"""Role enums for the two permission scopes.

RELAY has two independent role scopes, and conflating them is the mistake
this module exists to prevent:

* :class:`OrgRole` governs the *organization* — billing, creating projects,
  inviting people. It grants **no access to job data whatsoever**.
* :class:`Role` governs a *project* — queues, jobs, API keys. This is the
  only thing that can authorise reading a job payload.

An OrgAdmin who wants to read a project's jobs must first grant themselves
a project membership, and that self-grant is an audited event.
"""

from enum import StrEnum


class OrgRole(StrEnum):
    """A user's role within an organization."""

    OWNER = "org_owner"
    """Billing, deleting the org, transferring ownership."""

    ADMIN = "org_admin"
    """Creating and deleting projects, inviting and removing org members."""

    MEMBER = "org_member"
    """Belongs to the org and can be added to its projects. No org powers."""


class Role(StrEnum):
    """A user's role within a single project."""

    OWNER = "owner"
    """Deleting the project and transferring project ownership."""

    ADMIN = "admin"
    """API keys, queue pause/purge/defaults, project membership."""

    MEMBER = "member"
    """Enqueue, cancel and replay jobs. Mistakes here affect one job."""

    VIEWER = "viewer"
    """Read-only. Sees job state and failures, mutates nothing."""


# Privilege ordering. Higher number outranks lower.
#
# These are deliberately explicit dicts rather than comparisons on the enum
# members themselves: StrEnum inherits ``<`` from ``str``, so ``Role.ADMIN <
# Role.MEMBER`` silently does an *alphabetical* comparison and returns True.
# Always rank through these maps, never with a bare ``<`` on a role.
ORG_RANK: dict[OrgRole, int] = {
    OrgRole.MEMBER: 0,
    OrgRole.ADMIN: 1,
    OrgRole.OWNER: 2,
}

RANK: dict[Role, int] = {
    Role.VIEWER: 0,
    Role.MEMBER: 1,
    Role.ADMIN: 2,
    Role.OWNER: 3,
}
