from typing import Optional, Sequence

from app.shared.repository.mongo_repository import MongoRepository
from app.shared.specification.base import Specification

from .models import Standard, StandardMetadata


class StandardRepository(MongoRepository[Standard, str]):
    model = Standard

    async def get_by_qdrant_point_id(self, qdrant_point_id: str) -> Optional[Standard]:
        return await self.model.find_one({"qdrant_point_id": qdrant_point_id})

    async def get_many_by_qdrant_point_ids(self, point_ids: Sequence[str]) -> Sequence[Standard]:
        if not point_ids:
            return []
        return await self.model.find({"qdrant_point_id": {"$in": list(point_ids)}}).to_list()

    async def distinct_categories(
        self, spec: Specification
    ) -> Sequence[tuple[StandardMetadata, str, str]]:
        # ponytail: unbounded $group; lighting standards have tens of tables. Paginate if this becomes a huge cross-standard dump.
        pipeline: list[dict] = []
        match = spec.to_mongo(self.model)
        if match:
            pipeline.append({"$match": match})
        pipeline.append(
            {
                "$group": {
                    "_id": {
                        "standard_code": "$standard_metadata.standard_code",
                        "version_year": "$standard_metadata.version_year",
                        "category_table_number": "$hierarchy.category_table_number",
                    },
                    "category_title": {"$first": "$hierarchy.category_title"},
                    "is_latest": {"$first": "$standard_metadata.is_latest"},
                }
            }
        )
        rows = await self.model.aggregate(pipeline).to_list()
        return [
            (
                StandardMetadata(
                    standard_code=row["_id"]["standard_code"],
                    version_year=row["_id"]["version_year"],
                    is_latest=row["is_latest"],
                ),
                row["_id"]["category_table_number"],
                row["category_title"],
            )
            for row in rows
        ]
