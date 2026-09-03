from typing import Generic, Optional, Sequence, Type, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.repository.base import AbstractRepository
from app.shared.specification.base import Specification

ModelT = TypeVar("ModelT")


class SQLRepository(AbstractRepository[ModelT, int], Generic[ModelT]):
    model: Type[ModelT]

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        await self.session.commit()
        await self.session.refresh(entity)
        return entity

    async def create_many(self, entities: Sequence[ModelT]) -> Sequence[ModelT]:
        if not entities:
            return []
        self.session.add_all(entities)
        await self.session.commit()
        for entity in entities:
            await self.session.refresh(entity)
        return entities

    async def get_by_id(self, id: int) -> Optional[ModelT]:
        return await self.session.get(self.model, id)

    async def get_many_by_ids(self, ids: Sequence[int]) -> Sequence[ModelT]:
        if not ids:
            return []
        result = await self.session.execute(select(self.model).where(self.model.id.in_(ids)))
        return result.scalars().all()

    async def list(self, skip: int = 0, limit: int = 100) -> Sequence[ModelT]:
        result = await self.session.execute(select(self.model).offset(skip).limit(limit))
        return result.scalars().all()

    async def find(self, spec: Specification, skip: int = 0, limit: int = 100) -> Sequence[ModelT]:
        stmt = select(self.model).where(spec.to_sql(self.model)).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count(self, spec: Specification) -> int:
        stmt = select(func.count()).select_from(self.model).where(spec.to_sql(self.model))
        return await self.session.scalar(stmt) or 0

    async def update(self, id: int, data: dict) -> Optional[ModelT]:
        entity = await self.get_by_id(id)
        if entity is None:
            return None
        for key, value in data.items():
            setattr(entity, key, value)
        await self.session.commit()
        await self.session.refresh(entity)
        return entity

    async def delete(self, id: int) -> bool:
        entity = await self.get_by_id(id)
        if entity is None:
            return False
        await self.session.delete(entity)
        await self.session.commit()
        return True
