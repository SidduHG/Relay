"""handler schemas

Revision ID: 0007
Revises: 0006
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "handler_schemas",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("handler", sa.String(255), nullable=False),
        sa.Column("schema", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "handler"),
    )
    op.execute("ALTER TABLE handler_schemas ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE handler_schemas FORCE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY tenant_isolation ON handler_schemas USING (project_id = NULLIF(current_setting('app.project_id', true), '')::uuid)")


def downgrade() -> None:
    op.drop_table("handler_schemas")
