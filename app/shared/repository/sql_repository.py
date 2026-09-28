from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.repository.base import AbstractRepository
from app.shared.specification.base import Specification

ModelT = TypeVar("ModelT")
IdT = TypeVar("IdT")


class SQLRepository(AbstractRepository[ModelT, IdT], Generic[ModelT, IdT]):
    model: type[ModelT]

    def __init__(self, session: AsyncSession):
        self.session = session

    def _options(self) -> Sequence[Any]:
        return ()

    def _select(self):
        return select(self.model).options(*self._options())

    async def create(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        await self.session.commit()
        loaded = await self.get_by_id(entity.id)  # type: ignore[attr-defined]
        return loaded if loaded is not None else entity

    async def create_many(self, entities: Sequence[ModelT]) -> Sequence[ModelT]:
        if not entities:
            return []
        self.session.add_all(entities)
        await self.session.commit()
        ids = [entity.id for entity in entities]  # type: ignore[attr-defined]
        return await self.get_many_by_ids(ids)

    async def get_by_id(self, id: IdT) -> ModelT | None:
        return await self.session.get(
            self.model,
            id,
            options=self._options(),
            populate_existing=True,
        )

    async def get_many_by_ids(self, ids: Sequence[IdT]) -> Sequence[ModelT]:
        if not ids:
            return []
        result = await self.session.execute(self._select().where(self.model.id.in_(ids)))
        rows = result.scalars().all()
        by_id = {row.id: row for row in rows}
        return [by_id[i] for i in ids if i in by_id]

    async def list(self, skip: int = 0, limit: int = 100) -> Sequence[ModelT]:
        result = await self.session.execute(self._select().offset(skip).limit(limit))
        return result.scalars().all()

    async def find(self, spec: Specification, skip: int = 0, limit: int = 100) -> Sequence[ModelT]:
        stmt = self._select().where(spec.to_sql(self.model)).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_one(self, spec: Specification) -> ModelT | None:
        rows = await self.find(spec, skip=0, limit=1)
        return rows[0] if rows else None

    async def count(self, spec: Specification) -> int:
        stmt = select(func.count()).select_from(self.model).where(spec.to_sql(self.model))
        return await self.session.scalar(stmt) or 0

    async def update(self, id: IdT, data: dict) -> ModelT | None:
        entity = await self.session.get(self.model, id)
        if entity is None:
            return None
        for key, value in data.items():
            setattr(entity, key, value)
        await self.session.commit()
        return await self.get_by_id(id)

    async def delete(self, id: IdT) -> bool:
        entity = await self.session.get(self.model, id)
        if entity is None:
            return False
        await self.session.delete(entity)
        await self.session.commit()
        return True
