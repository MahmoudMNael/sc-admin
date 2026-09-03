from typing import Generic, Optional, Sequence, Type, TypeVar

from beanie import Document

from app.shared.repository.base import AbstractRepository
from app.shared.specification.base import Specification

DocT = TypeVar("DocT", bound=Document)
IdT = TypeVar("IdT")


class MongoRepository(AbstractRepository[DocT, IdT], Generic[DocT, IdT]):
    model: Type[DocT]

    async def create(self, entity: DocT) -> DocT:
        return await entity.insert()

    async def create_many(self, entities: Sequence[DocT]) -> Sequence[DocT]:
        if not entities:
            return []
        await self.model.insert_many(entities)
        return entities

    async def get_by_id(self, id: IdT) -> Optional[DocT]:
        return await self.model.get(id)

    async def get_many_by_ids(self, ids: Sequence[IdT]) -> Sequence[DocT]:
        if not ids:
            return []
        return await self.model.find({"_id": {"$in": list(ids)}}).to_list()

    async def list(self, skip: int = 0, limit: int = 100) -> Sequence[DocT]:
        return await self.model.find_all().skip(skip).limit(limit).to_list()

    async def find(self, spec: Specification, skip: int = 0, limit: int = 100) -> Sequence[DocT]:
        query = spec.to_mongo(self.model)
        return await self.model.find(query).skip(skip).limit(limit).to_list()

    async def count(self, spec: Specification) -> int:
        query = spec.to_mongo(self.model)
        return await self.model.find(query).count()

    async def update(self, id: IdT, data: dict) -> Optional[DocT]:
        entity = await self.get_by_id(id)
        if entity is None:
            return None
        await entity.set(data)
        return entity

    async def delete(self, id: IdT) -> bool:
        entity = await self.get_by_id(id)
        if entity is None:
            return False
        await entity.delete()
        return True
