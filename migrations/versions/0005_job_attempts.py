"""partitioned job attempts

Revision ID: 0005
Revises: 0004
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PARTITIONS = (
    ("job_attempts_2026_09", "2026-09-01", "2026-10-01"),
    ("job_attempts_2026_10", "2026-10-01", "2026-11-01"),
    ("job_attempts_2026_11", "2026-11-01", "2026-12-01"),
)


def _secure(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY tenant_isolation ON {table} USING (project_id = NULLIF(current_setting('app.project_id', true), '')::uuid)")


def upgrade() -> None:
    op.execute("CREATE TYPE attempt_outcome AS ENUM ('succeeded','failed','timed_out','reclaimed','cancelled')")
    op.execute("""
        CREATE TABLE job_attempts (
            id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            project_id uuid NOT NULL,
            job_id uuid NOT NULL,
            attempt_number smallint NOT NULL,
            worker_id varchar(255),
            started_at timestamptz,
            finished_at timestamptz,
            duration_ms integer,
            outcome attempt_outcome NOT NULL,
            error_class varchar(255),
            error_message text,
            error_stack text,
            error_category varchar(30),
            retry_after_seconds integer,
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at)
    """)
    for table, start, end in PARTITIONS:
        op.execute(f"CREATE TABLE {table} PARTITION OF job_attempts FOR VALUES FROM ('{start}') TO ('{end}')")
    op.execute("CREATE TABLE job_attempts_default PARTITION OF job_attempts DEFAULT")
    _secure("job_attempts")
    for table, _, _ in PARTITIONS:
        _secure(table)
    _secure("job_attempts_default")


def downgrade() -> None:
    op.execute("DROP TABLE job_attempts CASCADE")
    op.execute("DROP TYPE attempt_outcome")
