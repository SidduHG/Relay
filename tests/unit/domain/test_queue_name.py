import pytest
from relay_domain.value_objects.queue_name import InvalidQueueNameError, QueueName


@pytest.mark.parametrize("name", ["a", "emails", "priority_1", "web-hooks", "a" * 63])
def test_queue_name_accepts_canonical_names(name: str) -> None:
    assert str(QueueName.parse(name)) == name


@pytest.mark.parametrize("name", ["", "Emails", "-emails", "with space", "a" * 64])
def test_queue_name_rejects_noncanonical_names(name: str) -> None:
    with pytest.raises(InvalidQueueNameError):
        QueueName.parse(name)
