from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.modules.assets.models import Asset
from app.modules.assets.repository import AssetRepository
from app.modules.fixtures.models import Fixture, FixtureVariant, FixtureVariantImage
from app.shared.specification.base import Specification
from app.shared.specification.fields import ArrayContains, FieldEquals
from app.shared.specification.keyword import KeywordSpecification
from app.shared.specification.match_all import MatchAllSpecification

from .dto import (
    CreateFixtureRequest,
    CreateVariantImageRequest,
    CreateVariantRequest,
    FixtureResponse,
    FixtureSummaryResponse,
    UpdateFixtureRequest,
    UpdateVariantRequest,
    VariantDetailResponse,
    VariantImageResponse,
    VariantResponse,
)
from .repository import (
    FixtureRepository,
    FixtureVariantImageRepository,
    FixtureVariantRepository,
)

SEARCHABLE_FIELDS = ["manufacturer_name", "name"]
VARIANT_SEARCHABLE_FIELDS = ["name"]


class _VariantFixtureApplicationSpec(Specification):
    """Filter variants by parent fixture application via relationship (no repo change)."""

    def __init__(self, application: str):
        self.application = application

    def to_sql(self, model):
        from app.modules.fixtures.models import Fixture

        return model.fixture.has(Fixture.applications.contains([self.application]))

    def to_mongo(self, model):
        return {"fixture.applications": self.application}


class _VariantFixtureIsMainSolutionSpec(Specification):
    """Filter variants by parent fixture is_main_solution flag via relationship."""

    def __init__(self, is_main_solution: bool):
        self.is_main_solution = is_main_solution

    def to_sql(self, model):
        from app.modules.fixtures.models import Fixture

        return model.fixture.has(Fixture.is_main_solution == self.is_main_solution)

    def to_mongo(self, model):
        return {"fixture.is_main_solution": self.is_main_solution}


class FixtureService:
    def __init__(
        self,
        fixtures: FixtureRepository,
        variants: FixtureVariantRepository,
        images: FixtureVariantImageRepository,
        assets: AssetRepository,
    ):
        self.fixtures = fixtures
        self.variants = variants
        self.images = images
        self.assets = assets

    async def create_fixture(self, payload: CreateFixtureRequest) -> FixtureSummaryResponse:
        entity = Fixture(
            manufacturer_name=payload.manufacturer_name,
            name=payload.name,
            is_main_solution=payload.is_main_solution,
            applications=[a.value for a in payload.applications],
        )
        try:
            created = await self.fixtures.create(entity)
        except IntegrityError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid asset reference") from None

        return FixtureSummaryResponse.model_validate(created)

    async def list_fixtures(
        self,
        q: str | None,
        application: str | None,
        is_main_solution: bool | None,
        skip: int,
        limit: int,
    ) -> tuple[list[FixtureSummaryResponse], int]:
        spec: Specification = MatchAllSpecification()
        if q and q.strip():
            spec = spec & KeywordSpecification(fields=SEARCHABLE_FIELDS, keywords=[q], match_mode="all")
        if application:
            spec = spec & ArrayContains("applications", application)
        if is_main_solution is not None:
            spec = spec & FieldEquals("is_main_solution", is_main_solution)
        total = await self.fixtures.count(spec)
        items = await self.fixtures.find(spec, skip=skip, limit=limit)
        return [FixtureSummaryResponse.model_validate(item) for item in items], total

    async def list_variants(
        self,
        q: str | None,
        application: str | None,
        is_main_solution: bool | None,
        fixture_id: UUID | None,
        skip: int,
        limit: int,
    ) -> tuple[list[VariantDetailResponse], int]:
        if fixture_id is not None:
            await self._require_fixture(fixture_id)
        spec: Specification = MatchAllSpecification()
        if q and q.strip():
            spec = spec & KeywordSpecification(
                fields=VARIANT_SEARCHABLE_FIELDS, keywords=[q], match_mode="all"
            )
        if fixture_id is not None:
            spec = spec & FieldEquals("fixture_id", fixture_id)
        if application:
            spec = spec & _VariantFixtureApplicationSpec(application)
        if is_main_solution is not None:
            spec = spec & _VariantFixtureIsMainSolutionSpec(is_main_solution)
        total = await self.variants.count(spec)
        items = await self.variants.find(spec, skip=skip, limit=limit)
        return [VariantDetailResponse.model_validate(item) for item in items], total

    async def get_fixture(self, fixture_id: UUID) -> FixtureResponse:
        fixture = await self.fixtures.get_with_variants(fixture_id)
        if fixture is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Fixture not found")
        return FixtureResponse.model_validate(fixture)

    async def update_fixture(self, fixture_id: UUID, payload: UpdateFixtureRequest) -> FixtureSummaryResponse:
        existing = await self.fixtures.get_by_id(fixture_id)
        if existing is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Fixture not found")
        data = payload.model_dump(exclude_unset=True)
        if not data:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields provided to update")
        if "applications" in data:
            data["applications"] = [a.value if hasattr(a, "value") else a for a in payload.applications or []]
        data["updated_at"] = datetime.now(timezone.utc)
        try:
            updated = await self.fixtures.update(fixture_id, data)
        except IntegrityError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid asset reference") from None
        assert updated is not None
        return FixtureSummaryResponse.model_validate(updated)

    async def delete_fixture(self, fixture_id: UUID) -> None:
        if not await self.fixtures.delete(fixture_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Fixture not found")

    async def create_variant(self, fixture_id: UUID, payload: CreateVariantRequest) -> VariantResponse:
        ies = await self._require_asset(payload.ies_file_id)
        if ies is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "IES file not found")
        await self._require_fixture(fixture_id)
        if payload.model_3d_file_id is not None:
            await self._require_asset(payload.model_3d_file_id)
        await self._reject_duplicate_variant_name(fixture_id, payload.name)
        entity = FixtureVariant(
            fixture_id=fixture_id,
            name=payload.name,
            power=payload.power,
            chip=payload.chip,
            driver=payload.driver,
            power_factor=payload.power_factor,
            cri=payload.cri,
            efficacy=payload.efficacy,
            mechanical_protections=payload.mechanical_protections,
            electrical_protections=[e.value for e in payload.electrical_protections],
            dimension_length=payload.dimension_length,
            dimension_width=payload.dimension_width,
            dimension_depth=payload.dimension_depth,
            dimension_radius=payload.dimension_radius,
            model_3d_file_id=payload.model_3d_file_id,
            ies_file_id=payload.ies_file_id,
        )
        try:
            created = await self.variants.create(entity)
        except IntegrityError:
            raise HTTPException(status.HTTP_409_CONFLICT, "Variant name already exists on this fixture") from None
        loaded = await self.variants.get_by_id(created.id)
        assert loaded is not None
        return VariantResponse.model_validate(loaded)


    async def get_variant(self, fixture_id: UUID, variant_id: UUID) -> VariantDetailResponse:
        await self._require_fixture(fixture_id)
        variant = await self.variants.get_with_fixture(variant_id)
        if variant is None or variant.fixture_id != fixture_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Variant not found")
        return VariantDetailResponse.model_validate(variant)

    async def update_variant(
        self, fixture_id: UUID, variant_id: UUID, payload: UpdateVariantRequest
    ) -> VariantResponse:
        await self._require_variant(fixture_id, variant_id)
        data = payload.model_dump(exclude_unset=True)
        if not data:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields provided to update")
        if "name" in data:
            await self._reject_duplicate_variant_name(fixture_id, data["name"], exclude_id=variant_id)
        if "model_3d_file_id" in data and data["model_3d_file_id"] is not None:
            await self._require_asset(data["model_3d_file_id"])
        if "ies_file_id" in data and data["ies_file_id"] is not None:
            await self._require_asset(data["ies_file_id"])
        if "electrical_protections" in data:
            data["electrical_protections"] = [
                e.value if hasattr(e, "value") else e for e in payload.electrical_protections or []
            ]
        data["updated_at"] = datetime.now(timezone.utc)
        try:
            updated = await self.variants.update(variant_id, data)
        except IntegrityError:
            raise HTTPException(status.HTTP_409_CONFLICT, "Variant name already exists on this fixture") from None
        assert updated is not None
        return VariantResponse.model_validate(updated)

    async def delete_variant(self, fixture_id: UUID, variant_id: UUID) -> None:
        await self._require_variant(fixture_id, variant_id)
        await self.variants.delete(variant_id)

    async def create_variant_image(
        self, fixture_id: UUID, variant_id: UUID, payload: CreateVariantImageRequest
    ) -> VariantImageResponse:
        await self._require_variant(fixture_id, variant_id)
        await self._require_asset(payload.image_file_id)
        existing = await self.images.get_one(
            FieldEquals("variant_id", variant_id) & FieldEquals("image_file_id", payload.image_file_id)
        )
        if existing is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Image already attached to this variant")
        entity = FixtureVariantImage(variant_id=variant_id, image_file_id=payload.image_file_id)
        try:
            created = await self.images.create(entity)
        except IntegrityError:
            raise HTTPException(status.HTTP_409_CONFLICT, "Image already attached to this variant") from None
        loaded = await self.images.get_by_id(created.id)
        assert loaded is not None
        return VariantImageResponse.model_validate(loaded)

    async def delete_variant_image(self, fixture_id: UUID, variant_id: UUID, image_id: UUID) -> None:
        await self._require_variant(fixture_id, variant_id)
        image = await self.images.get_by_id(image_id)
        if image is None or image.variant_id != variant_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found")
        await self.images.delete(image_id)

    async def _require_asset(self, asset_id: UUID) -> Asset:
        asset = await self.assets.get_by_id(asset_id)
        if asset is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset not found")
        return asset

    async def _require_fixture(self, fixture_id: UUID) -> Fixture:
        fixture = await self.fixtures.get_by_id(fixture_id)
        if fixture is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Fixture not found")
        return fixture

    async def _require_variant(self, fixture_id: UUID, variant_id: UUID) -> FixtureVariant:
        await self._require_fixture(fixture_id)
        variant = await self.variants.get_by_id(variant_id)
        if variant is None or variant.fixture_id != fixture_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Variant not found")
        return variant

    async def _reject_duplicate_variant_name(
        self, fixture_id: UUID, name: str, exclude_id: UUID | None = None
    ) -> None:
        occupant = await self.variants.get_one(FieldEquals("fixture_id", fixture_id) & FieldEquals("name", name))
        if occupant is not None and occupant.id != exclude_id:
            raise HTTPException(status.HTTP_409_CONFLICT, "Variant name already exists on this fixture")
