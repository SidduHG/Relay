"""job indexes

Revision ID: 0008
Revises: 0007
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE INDEX ix_jobs_cursor ON jobs (project_id, created_at DESC, id DESC)")
    op.execute("CREATE INDEX ix_jobs_dispatch ON jobs (project_id, queue_id, state) WHERE state IN ('queued','scheduled')")
    op.execute("CREATE INDEX ix_jobs_handler_live ON jobs (project_id, handler, created_at DESC) WHERE state IN ('queued','scheduled','running')")
    op.execute("CREATE INDEX ix_jobs_state_live ON jobs (project_id, state, created_at DESC) WHERE state IN ('queued','scheduled','running','parked')")
    op.execute("CREATE INDEX ix_jobs_redis_drift ON jobs (project_id, created_at) WHERE redis_indexed_at IS NULL AND state = 'queued'")
    op.execute("CREATE INDEX ix_job_attempts_job_number ON job_attempts (job_id, attempt_number)")


def downgrade() -> None:
    op.execute("DROP INDEX ix_job_attempts_job_number")
    op.execute("DROP INDEX ix_jobs_redis_drift")
    op.execute("DROP INDEX ix_jobs_state_live")
    op.execute("DROP INDEX ix_jobs_handler_live")
    op.execute("DROP INDEX ix_jobs_dispatch")
    op.execute("DROP INDEX ix_jobs_cursor")
