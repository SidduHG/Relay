"""Proves the actual HTTP wiring — routes, deps.py's Depends() chain,
and middleware/error_handler.py's status-code mapping — over a real
FastAPI app and real Postgres. The business rules underneath (escalation
guards, timing normalization, reuse detection, RLS isolation) are
already proven at the service/repository layer in
tests/integration/postgres/; this file exists to prove the wiring on
top of them is correct, not to re-prove the rules themselves.

relay_api.main constructs its Settings() singleton at import time, which
needs REDIS_URL and API_SECRET_KEY that other integration tests don't
require — so the import is deferred into the fixture, after checking
every required env var, to get a clean skip instead of a crash during
test collection when the full app env isn't set.

fastapi.testclient.TestClient is synchronous by design (it drives the
app through httpx's ASGI transport internally) — calling client.get(...)
from inside an `async def test_...` under pytest-asyncio is fine, since
TestClient's own request calls block the current thread rather than
requiring an awaited coroutine.
"""

import os
import uuid
from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest
from relay_db.connection import create_engine, create_session_factory
from relay_db.models.organization import Organization
from relay_db.unit_of_work import TenantUnitOfWork
from relay_domain.enums.role import OrgRole
from sqlalchemy import select

if TYPE_CHECKING:
    # Real import only for type checking. The runtime import stays
    # deferred into the fixture below (after checking required env
    # vars) so an incomplete app env produces a clean pytest.skip
    # instead of a Settings() ValidationError crashing test collection.
    from fastapi.testclient import TestClient

REQUIRED_ENV = ["DATABASE_URL", "DATABASE_ADMIN_URL", "REDIS_URL", "API_SECRET_KEY"]


@pytest.fixture
def client() -> Iterator["TestClient"]:  # noqa: F821 - imported lazily below
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        pytest.skip(f"missing env for the full app: {', '.join(missing)}")

    from fastapi.testclient import TestClient
    from relay_api.main import app

    try:
        with TestClient(app) as test_client:
            yield test_client
    except OSError as exc:
        pytest.skip(f"Postgres not reachable: {exc}")


async def _bootstrapped_org_id() -> uuid.UUID:
    engine = create_engine(os.environ["DATABASE_ADMIN_URL"])
    sessions = create_session_factory(engine)
    async with sessions() as session:
        org = (await session.scalars(select(Organization).limit(1))).first()
    await engine.dispose()
    assert org is not None
    return org.id


async def _grant_org_role(org_id: uuid.UUID, user_id: uuid.UUID, role: OrgRole) -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    sessions = create_session_factory(engine)
    async with sessions() as session, TenantUnitOfWork(session, org_id=org_id) as uow:
        await uow.org_memberships.create(user_id=user_id, role=role)
    await engine.dispose()


def _signup_and_login(client: "TestClient", email: str | None = None) -> tuple[str, str, uuid.UUID, str]:  # noqa: F821, E501
    email = email or f"{uuid.uuid4()}@example.com"
    password = "correct-horse-battery"
    client.post("/v1/auth/signup", json={"email": email, "password": password})
    resp = client.post("/v1/auth/login", json={"email": email, "password": password})
    access = resp.json()["access_token"]
    refresh = resp.json()["refresh_token"]
    user_id = uuid.UUID(client.get("/v1/auth/me", headers=_auth(access)).json()["id"])
    return access, refresh, user_id, email


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_health_check(client: "TestClient") -> None:  # noqa: F821
    resp = client.get("/health")
    assert resp.status_code == 200


async def test_signup_login_me_round_trip(client: "TestClient") -> None:  # noqa: F821
    access, _refresh, user_id, _email = _signup_and_login(client)
    resp = client.get("/v1/auth/me", headers=_auth(access))
    assert resp.status_code == 200
    assert resp.json()["id"] == str(user_id)


async def test_duplicate_signup_is_409(client: "TestClient") -> None:  # noqa: F821
    email = f"{uuid.uuid4()}@example.com"
    body = {"email": email, "password": "correct-horse-battery"}
    client.post("/v1/auth/signup", json=body)
    resp = client.post("/v1/auth/signup", json=body)
    assert resp.status_code == 409


async def test_wrong_password_is_401(client: "TestClient") -> None:  # noqa: F821
    email = f"{uuid.uuid4()}@example.com"
    client.post("/v1/auth/signup", json={"email": email, "password": "correct-horse-battery"})
    resp = client.post("/v1/auth/login", json={"email": email, "password": "wrong"})
    assert resp.status_code == 401


async def test_me_without_a_token_is_401(client: "TestClient") -> None:  # noqa: F821
    resp = client.get("/v1/auth/me")
    assert resp.status_code == 401


async def test_refresh_rotates_and_reuse_is_rejected(client: "TestClient") -> None:  # noqa: F821
    _access, refresh, _user_id, _email = _signup_and_login(client)

    resp = client.post("/v1/auth/refresh", json={"refresh_token": refresh})
    assert resp.status_code == 200

    replay = client.post("/v1/auth/refresh", json={"refresh_token": refresh})
    assert replay.status_code == 401


async def test_logout_then_refresh_is_401(client: "TestClient") -> None:  # noqa: F821
    _access, refresh, _user_id, _email = _signup_and_login(client)
    assert client.post("/v1/auth/logout", json={"refresh_token": refresh}).status_code == 204
    resp = client.post("/v1/auth/refresh", json={"refresh_token": refresh})
    assert resp.status_code == 401


async def test_org_member_with_no_membership_gets_404_listing_projects(
    client: "TestClient",  # noqa: F821
) -> None:
    access, _refresh, _user_id, _email = _signup_and_login(client)
    org_id = await _bootstrapped_org_id()
    resp = client.get(f"/v1/orgs/{org_id}/projects", headers=_auth(access))
    assert resp.status_code == 404


async def test_project_create_requires_org_permission(client: "TestClient") -> None:  # noqa: F821
    access, _refresh, user_id, _email = _signup_and_login(client)
    org_id = await _bootstrapped_org_id()
    await _grant_org_role(org_id, user_id, OrgRole.MEMBER)

    resp = client.post(
        f"/v1/orgs/{org_id}/projects",
        json={"name": "X", "slug": str(uuid.uuid4())},
        headers=_auth(access),
    )
    assert resp.status_code == 403


async def test_full_org_and_project_flow(client: "TestClient") -> None:  # noqa: F821
    """Signup -> org owner -> create project -> self-grant (audited) ->
    invite a second user to the org, then the project -> they accept
    both -> a mere project Member is blocked from changing anyone's
    role. This is the entire F1 spec, wired end to end over real HTTP."""
    owner_access, _r, owner_id, _oe = _signup_and_login(client)
    org_id = await _bootstrapped_org_id()
    await _grant_org_role(org_id, owner_id, OrgRole.OWNER)

    created = client.post(
        f"/v1/orgs/{org_id}/projects",
        json={"name": "Payments", "slug": str(uuid.uuid4())},
        headers=_auth(owner_access),
    )
    assert created.status_code == 201
    project_id = created.json()["id"]

    self_grant = client.post(
        f"/v1/orgs/{org_id}/self-grant",
        json={"project_id": project_id, "role": "owner"},
        headers=_auth(owner_access),
    )
    assert self_grant.status_code == 204

    invitee_access, _r2, invitee_id, invitee_email = _signup_and_login(client)

    org_invite = client.post(
        f"/v1/orgs/{org_id}/invitations",
        json={"email": invitee_email, "role": "org_member"},
        headers=_auth(owner_access),
    )
    assert org_invite.status_code == 201
    accept_org = client.post(
        "/v1/invitations/accept",
        json={"token": org_invite.json()["token"]},
        headers=_auth(invitee_access),
    )
    assert accept_org.status_code == 204

    project_invite = client.post(
        f"/v1/projects/{project_id}/invitations",
        json={"email": invitee_email, "role": "member"},
        headers=_auth(owner_access),
    )
    assert project_invite.status_code == 201
    accept_project = client.post(
        "/v1/invitations/accept",
        json={"token": project_invite.json()["token"]},
        headers=_auth(invitee_access),
    )
    assert accept_project.status_code == 204

    # a mere project Member cannot change anyone's role
    denied = client.patch(
        f"/v1/projects/{project_id}/members/{owner_id}",
        json={"role": "admin"},
        headers=_auth(invitee_access),
    )
    assert denied.status_code == 403

    # the owner cannot remove themselves
    self_removal = client.delete(
        f"/v1/projects/{project_id}/members/{owner_id}", headers=_auth(owner_access)
    )
    assert self_removal.status_code == 403


async def test_api_key_create_and_revoke(client: "TestClient") -> None:  # noqa: F821
    owner_access, _r, owner_id, _e = _signup_and_login(client)
    org_id = await _bootstrapped_org_id()
    await _grant_org_role(org_id, owner_id, OrgRole.OWNER)

    created = client.post(
        f"/v1/orgs/{org_id}/projects",
        json={"name": "Payments", "slug": str(uuid.uuid4())},
        headers=_auth(owner_access),
    )
    project_id = created.json()["id"]
    await _add_project_owner(project_id, owner_id, org_id)

    key = client.post(
        f"/v1/projects/{project_id}/api-keys",
        json={"name": "sdk-key"},
        headers=_auth(owner_access),
    )
    assert key.status_code == 201
    assert key.json()["secret"].startswith("rly_live_")

    revoke = client.delete(
        f"/v1/projects/{project_id}/api-keys/{key.json()['id']}", headers=_auth(owner_access)
    )
    assert revoke.status_code == 204


async def _add_project_owner(project_id: uuid.UUID, user_id: uuid.UUID, org_id: uuid.UUID) -> None:
    from relay_domain.enums.role import Role

    engine = create_engine(os.environ["DATABASE_URL"])
    sessions = create_session_factory(engine)
    async with (
        sessions() as session,
        TenantUnitOfWork(session, org_id=org_id, project_id=project_id) as uow,
    ):
        await uow.memberships.create(user_id=user_id, role=Role.OWNER)
    await engine.dispose()
