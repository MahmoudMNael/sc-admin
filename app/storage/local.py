from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import aiofiles
from fastapi import UploadFile

from .base import AbstractFileStorage


class LocalFileStorage(AbstractFileStorage):
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def get_absolute_path(self, relative_path: str) -> Path:
        base = self.base_path.resolve()
        path = (self.base_path / relative_path).resolve()
        if not path.is_relative_to(base):
            raise ValueError("relative_path escapes storage root")
        return path

    async def save(self, file: UploadFile, subfolder: str = "") -> tuple[str, int]:
        target_dir = self.get_absolute_path(subfolder) if subfolder else self.base_path.resolve()
        target_dir.mkdir(parents=True, exist_ok=True)

        ext = Path(file.filename or "").suffix
        filename = f"{uuid4().hex}{ext}"
        relative_path = f"{subfolder}/{filename}" if subfolder else filename

        size = 0
        async with aiofiles.open(target_dir / filename, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                await out.write(chunk)

        return relative_path, size

    async def delete(self, relative_path: str) -> bool:
        path = self.get_absolute_path(relative_path)
        if path.exists():
            path.unlink()
            return True
        return False

    async def iter_bytes(self, relative_path: str) -> AsyncIterator[bytes]:
        path = self.get_absolute_path(relative_path)
        if not path.is_file():
            raise FileNotFoundError(relative_path)
        async with aiofiles.open(path, "rb") as f:
            while chunk := await f.read(1024 * 1024):
                yield chunk
