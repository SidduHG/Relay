"""Safe local-filesystem blob storage for a single-node deployment."""

import asyncio
from pathlib import Path


class LocalBlobStore:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def _path(self, value: str) -> Path:
        relative = value.removeprefix("file://").lstrip("/\\")
        candidate = (self._root / relative).resolve()
        if candidate != self._root and self._root not in candidate.parents:
            raise ValueError("blob path escapes the configured storage root")
        return candidate

    async def put(self, key: str, data: bytes) -> str:
        path = self._path(key)

        def write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        await asyncio.to_thread(write)
        return f"file://{key.replace('\\', '/')}"

    async def get(self, uri: str) -> bytes:
        return await asyncio.to_thread(self._path(uri).read_bytes)

    async def delete(self, uri: str) -> None:
        path = self._path(uri)
        try:
            await asyncio.to_thread(path.unlink)
        except FileNotFoundError:
            return
