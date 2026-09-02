from relay_domain.enums.role import ORG_RANK, RANK, OrgRole, Role


def test_project_ranks_ascend_from_viewer_to_owner() -> None:
    assert RANK[Role.VIEWER] < RANK[Role.MEMBER] < RANK[Role.ADMIN] < RANK[Role.OWNER]


def test_org_ranks_ascend_from_member_to_owner() -> None:
    assert ORG_RANK[OrgRole.MEMBER] < ORG_RANK[OrgRole.ADMIN] < ORG_RANK[OrgRole.OWNER]


def test_every_role_has_a_rank() -> None:
    """A role added without a rank raises KeyError on a live permission check."""
    assert set(RANK) == set(Role)
    assert set(ORG_RANK) == set(OrgRole)


def test_roles_serialise_to_their_wire_values() -> None:
    """These strings land in Postgres and in JSON. Renaming one is a migration."""
    assert Role.ADMIN.value == "admin"
    assert OrgRole.ADMIN.value == "org_admin"


def test_org_and_project_role_values_never_collide() -> None:
    """No shared string between the scopes, so a value used in the wrong scope
    fails loudly instead of silently resolving to a real role."""
    assert not ({r.value for r in Role} & {r.value for r in OrgRole})
