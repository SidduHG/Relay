"""Completed attempt outcomes."""

from enum import StrEnum


class AttemptOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    RECLAIMED = "reclaimed"
    CANCELLED = "cancelled"
