"""The project entity — THE data boundary.

Every queue and job table carries project_id. org_id lives only here;
it is deliberately never duplicated onto job tables (see RELAY-SPEC.md
F1 step 5) so there is exactly one place tenancy resolution can go wrong,
not two.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Project:
    id: UUID
    org_id: UUID
    name: str
    slug: str
    created_at: datetime
