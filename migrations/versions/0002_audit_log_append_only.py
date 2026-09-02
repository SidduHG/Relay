"""audit_log append-only

RELAY-SPEC.md F1: "Audit log. Append-only record of every privileged
action." Nothing in the app layer issues an UPDATE or DELETE against
audit_log (AuditRepo is write-only), but that's discipline, not a
guarantee — the same tenant-isolation section of the spec insists on
enforcement "below the middleware... by the database itself," and the
same standard applies here: a future bug or a raw query must not be
able to rewrite history.

relay_app gets SELECT, INSERT, UPDATE, DELETE on every table by
default (infra/postgres/init/01-app-role.sql's ALTER DEFAULT
PRIVILEGES), since most tables legitimately need UPDATE/DELETE.
audit_log is the one table where that's wrong, so this migration
narrows it back down, table-specific — relay_app keeps INSERT and
SELECT, loses UPDATE and DELETE.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("REVOKE UPDATE, DELETE ON audit_log FROM relay_app")


def downgrade() -> None:
    op.execute("GRANT UPDATE, DELETE ON audit_log TO relay_app")
