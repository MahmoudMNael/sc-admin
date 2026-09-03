from abc import ABC, abstractmethod
from pathlib import Path

from fastapi import UploadFile


class AbstractFileStorage(ABC):
    @abstractmethod
    async def save(self, file: UploadFile, subfolder: str = "") -> str:
        """Persist the file, return a relative path/key usable to retrieve it later."""

    @abstractmethod
    async def delete(self, relative_path: str) -> bool: ...

    @abstractmethod
    def get_absolute_path(self, relative_path: str) -> Path: ...
