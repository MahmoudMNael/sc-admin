from typing import Optional, Sequence

from app.modules.standards.models import Standard
from app.shared.repository.base import AbstractRepository
from app.shared.specification.base import Specification


class FakeStandardRepository(AbstractRepository[Standard, str]):
    def __init__(self) -> None:
        self.store: dict[str, Standard] = {}
        self.create_calls: list[Standard] = []
        self.create_many_calls: list[Sequence[Standard]] = []

    async def create(self, entity: Standard) -> Standard:
        self.create_calls.append(entity)
        self.store[entity.id] = entity
        return entity

    async def create_many(self, entities: Sequence[Standard]) -> Sequence[Standard]:
        self.create_many_calls.append(entities)
        for entity in entities:
            self.store[entity.id] = entity
        return entities

    async def get_by_id(self, id: str) -> Optional[Standard]:
        return self.store.get(id)

    async def get_many_by_ids(self, ids: Sequence[str]) -> Sequence[Standard]:
        return [self.store[i] for i in ids if i in self.store]

    async def list(self, skip: int = 0, limit: int = 100) -> Sequence[Standard]:
        items = list(self.store.values())
        return items[skip : skip + limit]

    async def find(self, spec: Specification, skip: int = 0, limit: int = 100) -> Sequence[Standard]:
        items = list(self.store.values())
        return items[skip : skip + limit]

    async def count(self, spec: Specification) -> int:
        # ponytail: fake ignores spec the same way find does; swap both for in-memory spec eval if list tests need filter totals.
        return len(self.store)

    async def update(self, id: str, data: dict) -> Optional[Standard]:
        entity = self.store.get(id)
        if entity is None:
            return None
        for key, value in data.items():
            setattr(entity, key, value)
        return entity

    async def delete(self, id: str) -> bool:
        if id not in self.store:
            return False
        del self.store[id]
        return True

    async def get_by_qdrant_point_id(self, qdrant_point_id: str) -> Optional[Standard]:
        for entity in self.store.values():
            if entity.qdrant_point_id == qdrant_point_id:
                return entity
        return None

    async def get_many_by_qdrant_point_ids(self, point_ids: Sequence[str]) -> Sequence[Standard]:
        wanted = set(point_ids)
        return [entity for entity in self.store.values() if entity.qdrant_point_id in wanted]
