"""Lifecycle states shared by the API, workers, and database."""

from enum import StrEnum


class JobState(StrEnum):
    BLOCKED = "blocked"
    SCHEDULED = "scheduled"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PARKED = "parked"
