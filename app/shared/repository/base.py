from abc import ABC, abstractmethod
from typing import Generic, Optional, Sequence, TypeVar

from app.shared.specification.base import Specification

EntityT = TypeVar("EntityT")
IdT = TypeVar("IdT")


class AbstractRepository(ABC, Generic[EntityT, IdT]):
    @abstractmethod
    async def create(self, entity: EntityT) -> EntityT: ...

    @abstractmethod
    async def create_many(self, entities: Sequence[EntityT]) -> Sequence[EntityT]: ...

    @abstractmethod
    async def get_by_id(self, id: IdT) -> Optional[EntityT]: ...

    @abstractmethod
    async def get_many_by_ids(self, ids: Sequence[IdT]) -> Sequence[EntityT]: ...

    @abstractmethod
    async def list(self, skip: int = 0, limit: int = 100) -> Sequence[EntityT]: ...

    @abstractmethod
    async def find(self, spec: Specification, skip: int = 0, limit: int = 100) -> Sequence[EntityT]:
        """Return entities matching an arbitrary Specification. See Section 6."""

    @abstractmethod
    async def update(self, id: IdT, data: dict) -> Optional[EntityT]: ...

    @abstractmethod
    async def delete(self, id: IdT) -> bool: ...
