"""A distinct type for externally visible job identifiers."""

from typing import NewType
from uuid import UUID

JobId = NewType("JobId", UUID)
