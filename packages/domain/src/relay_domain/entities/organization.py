"""The organization entity — the billing and project-ownership boundary.

This is deliberately not the data-access boundary. An OrgRole grants no
access to job data by itself; see Project and Membership for that.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Organization:
    id: UUID
    name: str
    slug: str
    created_at: datetime
