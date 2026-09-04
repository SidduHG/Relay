"""Full HTTP proofs for F2. These skip cleanly when the local stack is not running."""

import os
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

import pytest
from relay_db.connection import create_engine, create_session_factory
from relay_db.models.organization import Organization
from relay_db.unit_of_work import TenantUnitOfWork
from relay_domain.enums.role import OrgRole, Role
from sqlalchemy import select

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

REQUIRED_ENV = ["DATABASE_URL", "DATABASE_ADMIN_URL", "REDIS_URL", "API_SECRET_KEY"]


@pytest.fixture
def client() -> Iterator["TestClient"]:
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        pytest.skip(f"missing env for the full app: {', '.join(missing)}")
    from fastapi.testclient import TestClient
    from relay_api.main import app

    try:
        with TestClient(app, client=("f2-tests", 50_000)) as test_client:
            yield test_client
    except OSError as exc:
        pytest.skip(f"local stack not reachable: {exc}")


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _org_id() -> uuid.UUID:
    engine = create_engine(os.environ["DATABASE_ADMIN_URL"])
    sessions = create_session_factory(engine)
    async with sessions() as session:
        org = (await session.scalars(select(Organization).limit(1))).first()
    await engine.dispose()
    assert org is not None
    return org.id


async def _grant_owner(org_id: uuid.UUID, user_id: uuid.UUID) -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    sessions = create_session_factory(engine)
    async with sessions() as session, TenantUnitOfWork(session, org_id=org_id) as uow:
        await uow.org_memberships.create(user_id=user_id, role=OrgRole.OWNER)
    await engine.dispose()


async def _add_project_owner(org_id: uuid.UUID, project_id: uuid.UUID, user_id: uuid.UUID) -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    sessions = create_session_factory(engine)
    async with (
        sessions() as session,
        TenantUnitOfWork(session, org_id=org_id, project_id=project_id) as uow,
    ):
        await uow.memberships.create(user_id=user_id, role=Role.OWNER)
    await engine.dispose()


async def _owner_project(client: "TestClient") -> tuple[str, str, str]:
    email = f"{uuid.uuid4()}@example.com"
    password = "correct-horse-battery"
    client.post("/v1/auth/signup", json={"email": email, "password": password})
    access = client.post("/v1/auth/login", json={"email": email, "password": password}).json()[
        "access_token"
    ]
    user_id = uuid.UUID(client.get("/v1/auth/me", headers=_auth(access)).json()["id"])
    org_id = await _org_id()
    await _grant_owner(org_id, user_id)
    created = client.post(
        f"/v1/orgs/{org_id}/projects",
        json={"name": "F2", "slug": str(uuid.uuid4())},
        headers=_auth(access),
    )
    project_id = uuid.UUID(created.json()["id"])
    await _add_project_owner(org_id, project_id, user_id)
    key = client.post(
        f"/v1/projects/{project_id}/api-keys",
        json={"name": "f2-test"},
        headers=_auth(access),
    ).json()["secret"]
    return access, key, str(project_id)


async def test_enqueue_read_cancel_and_admin_permission_matrix(
    client: "TestClient",
) -> None:
    owner, api_key, project_id = await _owner_project(client)
    path = f"/v1/projects/{project_id}/queues/emails/jobs"
    body = {"handler": "email.send", "payload": {"to": "a@example.com"}}
    headers = {**_auth(api_key), "Idempotency-Key": "same"}

    first = client.post(path, json=body, headers=headers)
    repeat = client.post(path, json=body, headers=headers)
    assert (first.status_code, repeat.status_code) == (201, 200)
    assert first.json()["id"] == repeat.json()["id"]

    assert (
        client.post(
            f"/v1/projects/{project_id}/queues/emails/pause", headers=_auth(api_key)
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/v1/projects/{project_id}/queues/emails/pause", headers=_auth(owner)
        ).status_code
        == 200
    )
    while_paused = client.post(
        path,
        json=body,
        headers={**_auth(api_key), "Idempotency-Key": "while-paused"},
    )
    assert while_paused.status_code == 201

    listed = client.get(f"/v1/projects/{project_id}/jobs", headers=_auth(api_key))
    assert listed.status_code == 200
    job_id = first.json()["id"]
    assert (
        client.get(f"/v1/projects/{project_id}/jobs/{job_id}", headers=_auth(api_key)).status_code
        == 200
    )
    assert (
        client.post(
            f"/v1/projects/{project_id}/jobs/{job_id}/cancel", headers=_auth(api_key)
        ).status_code
        == 200
    )

    token = client.post(
        f"/v1/projects/{project_id}/queues/emails/purge-token", headers=_auth(owner)
    )
    assert token.status_code == 200
    purged = client.delete(
        f"/v1/projects/{project_id}/queues/emails/jobs",
        params={"confirm": token.json()["token"]},
        headers=_auth(owner),
    )
    assert purged.status_code == 200
    assert purged.json()["cancelled"] >= 1


async def test_100_concurrent_http_submissions_return_one_201(
    client: "TestClient",
) -> None:
    _owner, api_key, project_id = await _owner_project(client)
    path = f"/v1/projects/{project_id}/queues/concurrent/jobs"
    headers = {**_auth(api_key), "Idempotency-Key": "one-hundred-same"}
    body = {"handler": "noop", "payload": {"value": 1}}

    def submit() -> tuple[int, str]:
        response = client.post(path, json=body, headers=headers)
        return response.status_code, response.json()["id"]

    with ThreadPoolExecutor(max_workers=25) as pool:
        responses = list(pool.map(lambda _index: submit(), range(100)))
    assert [status for status, _ in responses].count(201) == 1
    assert [status for status, _ in responses].count(200) == 99
    assert len({job_id for _, job_id in responses}) == 1


async def test_payload_above_ten_mib_is_rejected_before_enqueue(
    client: "TestClient",
) -> None:
    _owner, api_key, project_id = await _owner_project(client)
    response = client.post(
        f"/v1/projects/{project_id}/queues/large/jobs",
        json={"handler": "large", "payload": {"body": "x" * 10_485_761}},
        headers={**_auth(api_key), "Idempotency-Key": "too-large"},
    )
    assert response.status_code == 413
