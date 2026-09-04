import pytest
from relay_domain.enums.job_state import JobState
from relay_domain.state_machine.errors import IllegalTransitionError
from relay_domain.state_machine.transitions import LEGAL_TRANSITIONS, assert_transition


def test_every_ordered_pair_matches_the_transition_table() -> None:
    for source in JobState:
        for target in JobState:
            if target in LEGAL_TRANSITIONS[source]:
                assert_transition(source, target)
            else:
                with pytest.raises(IllegalTransitionError):
                    assert_transition(source, target)


def test_succeeded_is_terminal() -> None:
    assert LEGAL_TRANSITIONS[JobState.SUCCEEDED] == frozenset()
