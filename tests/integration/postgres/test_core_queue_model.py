"""Container-backed proofs for F2's schema, isolation, and enqueue transaction."""

import asyncio
import os
import uuid
from collections.abc import AsyncIterator

import pytest
from relay_db.connection import create_engine, create_session_factory
from relay_db.models.idempotency import IdempotencyKey
from relay_db.models.job import Job
from relay_db.models.organization import Organization
from relay_db.transactions.enqueue import EnqueueValues, enqueue_job
from relay_db.unit_of_work import TenantUnitOfWork
from relay_domain.enums.job_state import JobState
from relay_storage import prepare_payload
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class MemoryStore:
    async def put(self, key: str, data: bytes) -> str:
        return f"memory://{key}"

    async def get(self, uri: str) -> bytes:
        raise NotImplementedError

    async def delete(self, uri: str) -> None:
        return None


class FailingStore(MemoryStore):
    async def put(self, key: str, data: bytes) -> str:
        raise OSError("simulated blob outage")


@pytest.fixture
async def sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    url = os.environ.get("DATABASE_URL")
    if url is None:
        pytest.skip("DATABASE_URL not set — start the stack to run this suite")
    engine = create_engine(url)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        yield create_session_factory(engine)
    except OSError as exc:
        pytest.skip(f"Postgres not reachable: {exc}")
    finally:
        await engine.dispose()


async def _project(
    sessions: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, uuid.UUID]:
    org_id = uuid.uuid4()
    async with sessions() as session, TenantUnitOfWork(session, org_id=org_id) as uow:
        uow.session.add(Organization(id=org_id, name="F2", slug=str(org_id)))
        project = await uow.projects.create(name="F2", slug=str(uuid.uuid4()))
        return org_id, project.id


async def test_queue_autocreate_is_race_safe(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    org_id, project_id = await _project(sessions)

    async def create() -> uuid.UUID:
        async with (
            sessions() as session,
            TenantUnitOfWork(session, org_id=org_id, project_id=project_id) as uow,
        ):
            return (await uow.queues.get_or_create("emails")).id

    ids = await asyncio.gather(*(create() for _ in range(50)))
    assert len(set(ids)) == 1


async def test_100_identical_submissions_create_one_job(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    org_id, project_id = await _project(sessions)
    async with (
        sessions() as session,
        TenantUnitOfWork(session, org_id=org_id, project_id=project_id) as uow,
    ):
        await uow.queues.get_or_create("emails")

    async def submit() -> tuple[uuid.UUID, bool]:
        async with (
            sessions() as session,
            TenantUnitOfWork(session, org_id=org_id, project_id=project_id) as uow,
        ):
            queue = await uow.queues.get("emails")
            assert queue is not None
            result = await enqueue_job(
                uow,
                queue=queue,
                values=EnqueueValues(
                    handler="send_email",
                    payload=prepare_payload({"to": "test@example.com"}),
                    idempotency_key="same-request",
                ),
                blob_store=MemoryStore(),
                actor_type="api_key",
                actor_id=uuid.uuid4(),
            )
            return result.job.id, result.created

    results = await asyncio.gather(*(submit() for _ in range(100)))
    assert len({job_id for job_id, _ in results}) == 1
    assert sum(created for _, created in results) == 1

    async with (
        sessions() as session,
        TenantUnitOfWork(session, org_id=org_id, project_id=project_id) as uow,
    ):
        assert await uow.session.scalar(select(func.count()).select_from(Job)) == 1


async def test_failed_offload_rolls_back_claim_and_job(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    org_id, project_id = await _project(sessions)
    with pytest.raises(Exception, match="storage"):
        async with (
            sessions() as session,
            TenantUnitOfWork(session, org_id=org_id, project_id=project_id) as uow,
        ):
            queue = await uow.queues.get_or_create("large")
            await enqueue_job(
                uow,
                queue=queue,
                values=EnqueueValues(
                    handler="archive",
                    payload=prepare_payload({"body": "large"}),
                    idempotency_key="rollback-key",
                ),
                blob_store=FailingStore(),
                actor_type="user",
                actor_id=uuid.uuid4(),
                inline_max_bytes=1,
            )

    async with (
        sessions() as session,
        TenantUnitOfWork(session, org_id=org_id, project_id=project_id) as uow,
    ):
        claims = await uow.session.scalar(select(func.count()).select_from(IdempotencyKey))
        jobs = await uow.session.scalar(select(func.count()).select_from(Job))
        assert claims == 0
        assert jobs == 0


async def test_job_state_enum_matches_domain() -> None:
    url = os.environ.get("DATABASE_ADMIN_URL")
    if url is None:
        pytest.skip("DATABASE_ADMIN_URL not set — start the stack to run this suite")
    engine = create_engine(url)
    try:
        async with engine.connect() as connection:
            labels = (
                await connection.execute(
                    text(
                        "SELECT enumlabel FROM pg_enum JOIN pg_type "
                        "ON pg_enum.enumtypid = pg_type.oid "
                        "WHERE typname = 'job_state' ORDER BY enumsortorder"
                    )
                )
            ).scalars()
            assert list(labels) == [state.value for state in JobState]
    except OSError as exc:
        pytest.skip(f"Postgres not reachable: {exc}")
    finally:
        await engine.dispose()
