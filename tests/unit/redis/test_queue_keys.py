from uuid import UUID

import pytest
from relay_redis.keys import (
    purge_token_key,
    queue_config_key,
    queue_paused_key,
    queue_stream_key,
)

PROJECT = UUID("00000000-0000-0000-0000-000000000001")


def test_queue_keys_include_the_project_boundary() -> None:
    assert queue_stream_key(PROJECT, "emails", 0) == f"q:{PROJECT}:emails:p0"
    assert queue_paused_key(PROJECT, "emails") == f"q:{PROJECT}:emails:paused"
    assert queue_config_key(PROJECT, "emails") == f"queue:cfg:{PROJECT}:emails"
    assert purge_token_key(PROJECT, "emails") == f"purge:token:{PROJECT}:emails"


def test_stream_key_rejects_an_unknown_lane() -> None:
    with pytest.raises(ValueError):
        queue_stream_key(PROJECT, "emails", 4)
