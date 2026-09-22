import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.shared.specification.base import Specification
from app.shared.specification.fields import FieldEquals
from app.shared.specification.keyword import KeywordSpecification
from app.shared.specification.match_all import MatchAllSpecification
from app.shared.utils import generate_qdrant_point_id

from .dto import (
    CreateManyStandardsRequest,
    CreateStandardRequest,
    StandardCategoryResponse,
    StandardMetadataDTO,
    StandardResponse,
    UpdateStandardRequest,
)
from .models import Standard
from .repository import StandardRepository

SEARCHABLE_FIELDS = ["searchable_text", "activity", "specific_requirements"]
HASH_FIELDS = (
    "standard_metadata",
    "hierarchy",
    "activity",
    "parameters",
    "specific_requirements",
    "searchable_text",
)


def compute_content_hash(data: dict[str, Any]) -> str:
    canonical = {k: data[k] for k in HASH_FIELDS}
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()


def point_id_for(payload: CreateStandardRequest) -> str:
    return generate_qdrant_point_id(payload.model_dump())


class StandardService:
    def __init__(self, repository: StandardRepository):
        self.repository = repository

    def reject_duplicate_keys(self, payload: CreateManyStandardsRequest) -> None:
        ids = [item.id for item in payload.items]
        if len(ids) != len(set(ids)):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Duplicate ids within the same request batch")
        point_ids = [point_id_for(item) for item in payload.items]
        if len(point_ids) != len(set(point_ids)):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Duplicate qdrant_point_id values within the same request batch",
            )

    async def _ensure_point_id_free(self, qdrant_point_id: str, owner_id: str) -> None:
        occupant = await self.repository.get_by_qdrant_point_id(qdrant_point_id)
        if occupant is not None and occupant.id != owner_id:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"qdrant_point_id {qdrant_point_id} is already used by '{occupant.id}'",
            )

    def _entity_from_create(self, payload: CreateStandardRequest, now: datetime) -> Standard:
        data = payload.model_dump()
        return Standard(
            **data,
            qdrant_point_id=generate_qdrant_point_id(data),
            content_hash=compute_content_hash(data),
            created_at=now,
            updated_at=now,
        )

    async def create_standard(self, payload: CreateStandardRequest) -> StandardResponse:
        content_hash = compute_content_hash(payload.model_dump())
        existing = await self.repository.get_by_id(payload.id)

        if existing is not None:
            if existing.content_hash == content_hash:
                return StandardResponse.model_validate(existing)  # idempotent no-op
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Standard '{payload.id}' already exists with different content. "
                f"Use PATCH /standards/{payload.id} to update it explicitly.",
            )

        qdrant_point_id = point_id_for(payload)
        await self._ensure_point_id_free(qdrant_point_id, payload.id)

        now = datetime.now(timezone.utc)
        standard = self._entity_from_create(payload, now)
        try:
            created = await self.repository.create(standard)
        except DuplicateKeyError:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"qdrant_point_id {qdrant_point_id} is already used",
            )
        return StandardResponse.model_validate(created)

    async def create_many_standards(self, payload: CreateManyStandardsRequest) -> None:
        """Runs after POST /bulk returns 202. Duplicate keys in the payload were already rejected."""
        ids = [item.id for item in payload.items]
        point_ids = [point_id_for(item) for item in payload.items]
        existing_by_id = {s.id: s for s in await self.repository.get_many_by_ids(ids)}
        existing_by_point = {
            s.qdrant_point_id: s for s in await self.repository.get_many_by_qdrant_point_ids(point_ids)
        }

        now = datetime.now(timezone.utc)
        to_insert: list[Standard] = []
        for item in payload.items:
            current = existing_by_id.get(item.id)
            if current is not None:
                continue  # same-hash retry or content conflict — neither is inserted
            occupant = existing_by_point.get(point_id_for(item))
            if occupant is not None:
                continue  # point_id taken by another document — skip (HTTP already returned)
            to_insert.append(self._entity_from_create(item, now))

        if not to_insert:
            return
        try:
            await self.repository.create_many(to_insert)
        except DuplicateKeyError:
            # ponytail: unique-index race; in-process background job has no caller to 409. Upgrade: persist per-item results.
            pass

    async def get_standard(self, standard_id: str) -> StandardResponse:
        standard = await self.repository.get_by_id(standard_id)
        if standard is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Standard not found")
        return StandardResponse.model_validate(standard)

    async def list_standards(
        self,
        standard_code: str | None,
        version_year: str | None,
        is_latest: bool | None,
        category_table_number: str | None,
        activity: str | None,
        keywords: list[str],
        match_mode: Literal["any", "all"],
        skip: int,
        limit: int,
    ) -> tuple[list[StandardResponse], int]:
        spec = self._list_spec(
            standard_code,
            version_year,
            is_latest,
            category_table_number,
            activity,
            keywords,
            match_mode,
        )
        total = await self.repository.count(spec)
        standards = await self.repository.find(spec, skip=skip, limit=limit)
        return [StandardResponse.model_validate(s) for s in standards], total

    async def list_categories(
        self,
        standard_code: str | None,
        version_year: str | None,
        is_latest: bool | None,
    ) -> list[StandardCategoryResponse]:
        spec = self._list_spec(standard_code, version_year, is_latest, None, None, [], "any")
        rows = await self.repository.distinct_categories(spec)
        items = [
            StandardCategoryResponse(
                standard_metadata=StandardMetadataDTO.model_validate(meta),
                category_table_number=table_number,
                category_title=title,
            )
            for meta, table_number, title in rows
        ]

        def _key(item: StandardCategoryResponse) -> tuple:
            parts = tuple(int(p) if p.isdigit() else p for p in item.category_table_number.split("."))
            return (item.standard_metadata.standard_code, item.standard_metadata.version_year, parts)

        items.sort(key=_key)
        return items

    def _list_spec(
        self,
        standard_code: str | None,
        version_year: str | None,
        is_latest: bool | None,
        category_table_number: str | None,
        activity: str | None,
        keywords: list[str],
        match_mode: Literal["any", "all"],
    ) -> Specification:
        filters: list[Specification] = []
        if standard_code:
            filters.append(FieldEquals("standard_metadata.standard_code", standard_code))
        if version_year:
            filters.append(FieldEquals("standard_metadata.version_year", version_year))
        if is_latest is not None:
            filters.append(FieldEquals("standard_metadata.is_latest", is_latest))
        if category_table_number:
            filters.append(FieldEquals("hierarchy.category_table_number", category_table_number))
        if activity:
            filters.append(FieldEquals("activity", activity))
        if keywords:
            filters.append(KeywordSpecification(fields=SEARCHABLE_FIELDS, keywords=keywords, match_mode=match_mode))

        spec: Specification = MatchAllSpecification()
        for f in filters:
            spec = spec & f
        return spec

    async def update_standard(self, standard_id: str, payload: UpdateStandardRequest) -> StandardResponse:
        existing = await self.repository.get_by_id(standard_id)
        if existing is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Standard not found")

        data = payload.model_dump(exclude_unset=True)
        if not data:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields provided to update")

        existing_dump = existing.model_dump()
        if "standard_metadata" in data:
            data["standard_metadata"] = {**existing_dump["standard_metadata"], **data["standard_metadata"]}
        if "hierarchy" in data:
            data["hierarchy"] = {**existing_dump["hierarchy"], **data["hierarchy"]}

        merged = {**existing_dump, **data}
        data["content_hash"] = compute_content_hash(merged)
        data["updated_at"] = datetime.now(timezone.utc)
        # identity fields and qdrant_point_id are never in `data`

        updated = await self.repository.update(standard_id, data)
        return StandardResponse.model_validate(updated)

    async def delete_standard(self, standard_id: str) -> None:
        if not await self.repository.delete(standard_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Standard not found")
