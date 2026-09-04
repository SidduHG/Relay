"""queues

Revision ID: 0003
Revises: 0002
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "queues",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(63), nullable=False),
        sa.Column("max_attempts", sa.SmallInteger(), server_default="5", nullable=False),
        sa.Column("job_timeout_seconds", sa.Integer(), server_default="300", nullable=False),
        sa.Column("lease_duration_seconds", sa.Integer(), server_default="60", nullable=False),
        sa.Column("default_priority", sa.SmallInteger(), server_default="2", nullable=False),
        sa.Column("rate_limit_per_second", sa.Integer(), nullable=True),
        sa.Column("max_depth", sa.Integer(), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("name ~ '^[a-z0-9][a-z0-9_-]{0,62}$'", name="ck_queues_name_valid"),
        sa.CheckConstraint("max_attempts BETWEEN 1 AND 25", name="ck_queues_max_attempts_valid"),
        sa.CheckConstraint("job_timeout_seconds BETWEEN 1 AND 86400", name="ck_queues_timeout_valid"),
        sa.CheckConstraint("lease_duration_seconds BETWEEN 10 AND 3600", name="ck_queues_lease_valid"),
        sa.CheckConstraint("default_priority BETWEEN 0 AND 3", name="ck_queues_priority_valid"),
        sa.CheckConstraint("rate_limit_per_second IS NULL OR rate_limit_per_second >= 1", name="ck_queues_rate_valid"),
        sa.CheckConstraint("max_depth IS NULL OR max_depth >= 1", name="ck_queues_depth_valid"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "name"),
    )
    op.execute("ALTER TABLE queues ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE queues FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY tenant_isolation ON queues USING (project_id = NULLIF(current_setting('app.project_id', true), '')::uuid)")


def downgrade() -> None:
    op.drop_table("queues")
