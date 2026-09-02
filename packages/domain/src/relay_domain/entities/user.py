"""The global user entity.

Users are global, not scoped to an organization — one account can belong
to many organizations. This mirrors GitHub's model rather than Slack's:
a contractor working for two customers has one login, not two. See
docs/auth/plan.md for the reasoning.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class User:
    id: UUID
    email: str
    password_hash: str
    created_at: datetime
