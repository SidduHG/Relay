from datetime import UTC, datetime
from uuid import UUID

import pytest
from relay_storage.payloads import PayloadTooLargeError, payload_key, prepare_payload


def test_canonical_measurement_ignores_key_order() -> None:
    assert prepare_payload({"b": 2, "a": 1}).encoded == prepare_payload({"a": 1, "b": 2}).encoded


def test_reject_boundary_is_exact() -> None:
    prepare_payload("x", max_bytes=3)
    with pytest.raises(PayloadTooLargeError):
        prepare_payload("xx", max_bytes=3)


def test_payload_key_is_deterministic() -> None:
    project_id = UUID("00000000-0000-0000-0000-000000000001")
    job_id = UUID("00000000-0000-0000-0000-000000000002")
    created = datetime(2026, 9, 4, tzinfo=UTC)
    assert payload_key(project_id, job_id, created) == (
        "00000000-0000-0000-0000-000000000001/2026-09/00000000-0000-0000-0000-000000000002.json.gz"
    )
