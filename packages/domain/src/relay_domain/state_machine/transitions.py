"""The single domain-level job transition table."""

from types import MappingProxyType

from relay_domain.enums.job_state import JobState
from relay_domain.state_machine.errors import IllegalTransitionError

LEGAL_TRANSITIONS = MappingProxyType(
    {
        JobState.BLOCKED: frozenset({JobState.QUEUED, JobState.CANCELLED}),
        JobState.SCHEDULED: frozenset({JobState.QUEUED, JobState.CANCELLED}),
        JobState.QUEUED: frozenset({JobState.RUNNING, JobState.CANCELLED, JobState.PARKED}),
        JobState.RUNNING: frozenset(
            {
                JobState.SUCCEEDED,
                JobState.FAILED,
                JobState.SCHEDULED,
                JobState.QUEUED,
                JobState.PARKED,
                JobState.CANCELLED,
            }
        ),
        JobState.SUCCEEDED: frozenset(),
        JobState.FAILED: frozenset({JobState.QUEUED}),
        JobState.CANCELLED: frozenset({JobState.QUEUED}),
        JobState.PARKED: frozenset({JobState.QUEUED}),
    }
)


def assert_transition(from_state: JobState, to_state: JobState) -> None:
    if to_state not in LEGAL_TRANSITIONS[from_state]:
        raise IllegalTransitionError(f"illegal job transition: {from_state} -> {to_state}")
