"""Canonical JSON measurement and compressed payload offload."""

import gzip
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from relay_storage.interface import BlobStore

INLINE_MAX_BYTES = 262_144
PAYLOAD_MAX_BYTES = 10_485_760


class PayloadTooLargeError(ValueError):
    def __init__(self, size: int, limit: int) -> None:
        super().__init__(f"payload is {size} bytes; the limit is {limit}")
        self.size = size
        self.limit = limit


class StorageUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PreparedPayload:
    value: Any
    encoded: bytes
    size: int


def prepare_payload(payload: Any, *, max_bytes: int = PAYLOAD_MAX_BYTES) -> PreparedPayload:
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False, sort_keys=True).encode(
        "utf-8"
    )
    size = len(encoded)
    if size > max_bytes:
        raise PayloadTooLargeError(size, max_bytes)
    return PreparedPayload(value=payload, encoded=encoded, size=size)


def payload_key(project_id: UUID, job_id: UUID, created_at: datetime) -> str:
    return f"{project_id}/{created_at:%Y-%m}/{job_id}.json.gz"


async def offload_payload(
    store: BlobStore,
    prepared: PreparedPayload,
    *,
    project_id: UUID,
    job_id: UUID,
    created_at: datetime,
) -> str:
    key = payload_key(project_id, job_id, created_at)
    try:
        return await store.put(key, gzip.compress(prepared.encoded))
    except Exception as exc:
        raise StorageUnavailableError("payload storage is unavailable") from exc


async def rehydrate_payload(store: BlobStore, uri: str) -> Any:
    try:
        raw = gzip.decompress(await store.get(uri))
        return json.loads(raw)
    except Exception as exc:
        raise StorageUnavailableError("payload storage is unavailable") from exc
