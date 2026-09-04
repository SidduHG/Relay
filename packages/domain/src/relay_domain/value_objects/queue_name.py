"""Validated queue names used in URLs, database rows, and Redis keys."""

import re
from dataclasses import dataclass

_QUEUE_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")


class InvalidQueueNameError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class QueueName:
    value: str

    @classmethod
    def parse(cls, value: str) -> "QueueName":
        if not _QUEUE_NAME.fullmatch(value):
            raise InvalidQueueNameError(
                "queue name must be 1-63 lowercase characters, start with a letter or "
                "number, and contain only letters, numbers, '-' or '_'"
            )
        return cls(value)

    def __str__(self) -> str:
        return self.value
