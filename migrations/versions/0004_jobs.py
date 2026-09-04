"""partitioned jobs

Revision ID: 0004
Revises: 0003
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PARTITIONS = (
    ("jobs_2026_09", "2026-09-01", "2026-10-01"),
    ("jobs_2026_10", "2026-10-01", "2026-11-01"),
    ("jobs_2026_11", "2026-11-01", "2026-12-01"),
)


def _secure(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY tenant_isolation ON {table} USING (project_id = NULLIF(current_setting('app.project_id', true), '')::uuid)")


def upgrade() -> None:
    op.execute("CREATE TYPE job_state AS ENUM ('blocked','scheduled','queued','running','succeeded','failed','cancelled','parked')")
    op.execute("""
        CREATE TABLE jobs (
            id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            queue_id uuid NOT NULL REFERENCES queues(id) ON DELETE RESTRICT,
            queue_name varchar(63) NOT NULL,
            handler varchar(255) NOT NULL,
            handler_version varchar(100),
            payload jsonb,
            payload_ref text,
            payload_bytes integer NOT NULL CHECK (payload_bytes >= 0),
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            state job_state NOT NULL,
            priority smallint NOT NULL CHECK (priority BETWEEN 0 AND 3),
            priority_effective smallint NOT NULL CHECK (priority_effective BETWEEN 0 AND 3),
            attempt smallint NOT NULL DEFAULT 0 CHECK (attempt >= 0),
            max_attempts smallint NOT NULL,
            timeout_seconds integer NOT NULL,
            lease_seconds integer NOT NULL,
            reclaim_count smallint NOT NULL DEFAULT 0,
            run_at timestamptz,
            lease_expires_at timestamptz,
            lease_owner varchar(255),
            started_at timestamptz,
            finished_at timestamptz,
            result jsonb,
            result_ref text,
            dependency_count smallint NOT NULL DEFAULT 0,
            replayed_from uuid,
            cancel_requested_at timestamptz,
            cancel_reason varchar(50),
            trace_id char(32),
            span_id char(16),
            trace_flags smallint,
            enqueued_by_type varchar(20) NOT NULL,
            enqueued_by_id uuid NOT NULL,
            idempotency_key_hash char(64),
            redis_indexed_at timestamptz,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (id, created_at),
            CONSTRAINT ck_jobs_payload_location_valid CHECK ((payload IS NULL) <> (payload_ref IS NULL))
        ) PARTITION BY RANGE (created_at)
    """)
    for table, start, end in PARTITIONS:
        op.execute(f"CREATE TABLE {table} PARTITION OF jobs FOR VALUES FROM ('{start}') TO ('{end}')")
    op.execute("CREATE TABLE jobs_default PARTITION OF jobs DEFAULT")
    _secure("jobs")
    for table, _, _ in PARTITIONS:
        _secure(table)
    _secure("jobs_default")


def downgrade() -> None:
    op.execute("DROP TABLE jobs CASCADE")
    op.execute("DROP TYPE job_state")
