from typing import Optional, Sequence

from app.shared.repository.mongo_repository import MongoRepository

from .models import Standard


class StandardRepository(MongoRepository[Standard, str]):
    model = Standard

    async def get_by_qdrant_point_id(self, qdrant_point_id: str) -> Optional[Standard]:
        return await self.model.find_one({"qdrant_point_id": qdrant_point_id})

    async def get_many_by_qdrant_point_ids(self, point_ids: Sequence[str]) -> Sequence[Standard]:
        if not point_ids:
            return []
        return await self.model.find({"qdrant_point_id": {"$in": list(point_ids)}}).to_list()
