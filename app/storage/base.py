from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import UploadFile


class AbstractFileStorage(ABC):
    @abstractmethod
    async def save(self, file: UploadFile, subfolder: str = "") -> tuple[str, int]:
        """Persist the file. Return (relative path/key, size in bytes)."""

    @abstractmethod
    async def delete(self, relative_path: str) -> bool: ...

    @abstractmethod
    def get_absolute_path(self, relative_path: str) -> Path: ...

    @abstractmethod
    def iter_bytes(self, relative_path: str) -> AsyncIterator[bytes]:
        """Yield file bytes. Raise FileNotFoundError if missing."""
