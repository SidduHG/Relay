"""Priority lanes in dispatch order (lower is more urgent)."""

from enum import IntEnum


class Priority(IntEnum):
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
