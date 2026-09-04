"""Structural interface implemented by blob-storage backends."""

from typing import Protocol


class BlobStore(Protocol):
    async def put(self, key: str, data: bytes) -> str: ...

    async def get(self, uri: str) -> bytes: ...

    async def delete(self, uri: str) -> None: ...
