from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException, UploadFile, status

from app.shared.specification.base import Specification
from app.shared.specification.keyword import KeywordSpecification
from app.shared.specification.match_all import MatchAllSpecification
from app.storage.base import AbstractFileStorage

from .dto import AssetResponse
from .models import Asset
from .repository import AssetRepository

SEARCHABLE_FIELDS = ["original_filename"]
SUBFOLDER = "assets"


@dataclass
class AssetStream:
    asset: Asset
    chunks: AsyncIterator[bytes]


class AssetService:
    def __init__(self, repository: AssetRepository, storage: AbstractFileStorage):
        self.repository = repository
        self.storage = storage

    async def create_asset(self, file: UploadFile) -> AssetResponse:
        relative_path, size_bytes = await self.storage.save(file, subfolder=SUBFOLDER)
        entity = Asset(
            original_filename=file.filename or "unnamed",
            mime_type=file.content_type or "application/octet-stream",
            relative_path=relative_path,
            size_bytes=size_bytes,
        )
        try:
            entity = await self.repository.create(entity)
        except Exception:
            await self.storage.delete(relative_path)
            raise
        return AssetResponse.model_validate(entity)

    async def stream_asset(self, asset_id: UUID) -> AssetStream:
        asset = await self.repository.get_by_id(asset_id)
        if asset is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset not found")
        chunks = await self._open_chunks(asset.relative_path)
        return AssetStream(asset=asset, chunks=chunks)

    async def list_assets(self, name: str | None, skip: int, limit: int) -> tuple[list[AssetResponse], int]:
        spec: Specification = MatchAllSpecification()
        if name and name.strip():
            spec = spec & KeywordSpecification(
                fields=SEARCHABLE_FIELDS,
                keywords=[name],
                match_mode="all",
            )
        total = await self.repository.count(spec)
        items = await self.repository.find(spec, skip=skip, limit=limit)
        return [AssetResponse.model_validate(a) for a in items], total

    async def _open_chunks(self, relative_path: str) -> AsyncIterator[bytes]:
        iterator = self.storage.iter_bytes(relative_path)
        try:
            first = await anext(iterator)
        except StopAsyncIteration:

            async def empty() -> AsyncIterator[bytes]:
                return
                yield b""  # pragma: no cover — makes this an async generator

            return empty()
        except FileNotFoundError:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset not found") from None

        async def rest() -> AsyncIterator[bytes]:
            yield first
            async for chunk in iterator:
                yield chunk

        return rest()
