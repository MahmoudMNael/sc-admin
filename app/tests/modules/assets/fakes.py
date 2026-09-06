from collections.abc import AsyncIterator, Sequence
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import UploadFile

from app.modules.assets.models import Asset
from app.shared.repository.base import AbstractRepository
from app.shared.specification.base import AndSpecification, Specification
from app.shared.specification.keyword import KeywordSpecification
from app.shared.specification.match_all import MatchAllSpecification
from app.storage.base import AbstractFileStorage


class FakeFileStorage(AbstractFileStorage):
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.delete_calls: list[str] = []

    async def save(self, file: UploadFile, subfolder: str = "") -> tuple[str, int]:
        data = await file.read()
        name = f"{uuid4().hex}{Path(file.filename or '').suffix}"
        relative_path = f"{subfolder}/{name}" if subfolder else name
        self.files[relative_path] = data
        return relative_path, len(data)

    async def delete(self, relative_path: str) -> bool:
        self.delete_calls.append(relative_path)
        return self.files.pop(relative_path, None) is not None

    def get_absolute_path(self, relative_path: str) -> Path:
        raise NotImplementedError("tests use iter_bytes")

    async def iter_bytes(self, relative_path: str) -> AsyncIterator[bytes]:
        if relative_path not in self.files:
            raise FileNotFoundError(relative_path)
        yield self.files[relative_path]


def _matches(spec: Specification, asset: Asset) -> bool:
    if isinstance(spec, MatchAllSpecification):
        return True
    if isinstance(spec, AndSpecification):
        return all(_matches(s, asset) for s in spec.specs)
    if isinstance(spec, KeywordSpecification):
        if not spec.keywords:
            return True
        haystacks = [getattr(asset, field).lower() for field in spec.fields]
        hits = [any(kw.lower() in hay for hay in haystacks) for kw in spec.keywords]
        return all(hits) if spec.match_mode == "all" else any(hits)
    return True


class FakeAssetRepository(AbstractRepository[Asset, UUID]):
    def __init__(self) -> None:
        self.store: dict[UUID, Asset] = {}

    async def create(self, entity: Asset) -> Asset:
        if entity.id is None:
            entity.id = uuid4()
        if entity.created_at is None:
            entity.created_at = datetime.now(timezone.utc)
        self.store[entity.id] = entity
        return entity

    async def create_many(self, entities: Sequence[Asset]) -> Sequence[Asset]:
        for entity in entities:
            await self.create(entity)
        return entities

    async def get_by_id(self, id: UUID) -> Asset | None:
        return self.store.get(id)

    async def get_many_by_ids(self, ids: Sequence[UUID]) -> Sequence[Asset]:
        return [self.store[i] for i in ids if i in self.store]

    async def list(self, skip: int = 0, limit: int = 100) -> Sequence[Asset]:
        items = list(self.store.values())
        return items[skip : skip + limit]

    def _filtered(self, spec: Specification) -> list[Asset]:
        return [asset for asset in self.store.values() if _matches(spec, asset)]

    async def find(self, spec: Specification, skip: int = 0, limit: int = 100) -> Sequence[Asset]:
        return self._filtered(spec)[skip : skip + limit]

    async def count(self, spec: Specification) -> int:
        return len(self._filtered(spec))

    async def update(self, id: UUID, data: dict) -> Asset | None:
        entity = self.store.get(id)
        if entity is None:
            return None
        for key, value in data.items():
            setattr(entity, key, value)
        return entity

    async def delete(self, id: UUID) -> bool:
        if id not in self.store:
            return False
        del self.store[id]
        return True
