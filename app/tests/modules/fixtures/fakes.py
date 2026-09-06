from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy.orm.attributes import set_committed_value

from app.modules.fixtures.models import Fixture, FixtureVariant, FixtureVariantImage
from app.shared.specification.base import AndSpecification, Specification
from app.shared.specification.fields import ArrayContains, FieldEquals
from app.shared.specification.keyword import KeywordSpecification
from app.shared.specification.match_all import MatchAllSpecification
from app.tests.modules.assets.fakes import FakeAssetRepository


class FakeFixtureStore:
    def __init__(self) -> None:
        self.fixtures: dict[UUID, Fixture] = {}
        self.variants: dict[UUID, FixtureVariant] = {}
        self.images: dict[UUID, FixtureVariantImage] = {}


def _matches(spec: Specification, entity) -> bool:
    if isinstance(spec, MatchAllSpecification):
        return True
    if isinstance(spec, AndSpecification):
        return all(_matches(s, entity) for s in spec.specs)
    if isinstance(spec, FieldEquals):
        return getattr(entity, spec.field) == spec.value
    if isinstance(spec, ArrayContains):
        return spec.value in (getattr(entity, spec.field) or [])
    if isinstance(spec, KeywordSpecification):
        if not spec.keywords:
            return True
        haystacks = [str(getattr(entity, field)).lower() for field in spec.fields]
        hits = [any(kw.lower() in hay for hay in haystacks) for kw in spec.keywords]
        return all(hits) if spec.match_mode == "all" else any(hits)
    return True


def _stamp(entity) -> None:
    now = datetime.now(timezone.utc)
    if entity.id is None:
        entity.id = uuid4()
    if getattr(entity, "created_at", None) is None and hasattr(entity, "created_at"):
        entity.created_at = now
    if getattr(entity, "updated_at", None) is None and hasattr(entity, "updated_at"):
        entity.updated_at = now


class FakeFixtureRepository:
    def __init__(self, store: FakeFixtureStore, assets: FakeAssetRepository):
        self.store = store
        self.assets = assets

    def _attach(self, fixture: Fixture) -> Fixture:
        set_committed_value(fixture, "ies_file", self.assets.store.get(fixture.ies_file_id))
        return fixture

    async def create(self, entity: Fixture) -> Fixture:
        _stamp(entity)
        self.store.fixtures[entity.id] = entity
        return self._attach(entity)

    async def get_by_id(self, id: UUID) -> Fixture | None:
        fixture = self.store.fixtures.get(id)
        return self._attach(fixture) if fixture else None

    async def get_with_variants(self, id: UUID) -> Fixture | None:
        fixture = self.store.fixtures.get(id)
        if fixture is None:
            return None
        self._attach(fixture)
        variants = [v for v in self.store.variants.values() if v.fixture_id == id]
        attached = [FakeFixtureVariantRepository(self.store, self.assets)._attach(v) for v in variants]
        set_committed_value(fixture, "variants", attached)
        return fixture

    async def find(self, spec: Specification, skip: int = 0, limit: int = 100) -> Sequence[Fixture]:
        items = [self._attach(f) for f in self.store.fixtures.values() if _matches(spec, f)]
        return items[skip : skip + limit]

    async def count(self, spec: Specification) -> int:
        return sum(1 for f in self.store.fixtures.values() if _matches(spec, f))

    async def update(self, id: UUID, data: dict) -> Fixture | None:
        entity = self.store.fixtures.get(id)
        if entity is None:
            return None
        for key, value in data.items():
            setattr(entity, key, value)
        return self._attach(entity)

    async def delete(self, id: UUID) -> bool:
        if id not in self.store.fixtures:
            return False
        variant_ids = [v.id for v in self.store.variants.values() if v.fixture_id == id]
        for variant_id in variant_ids:
            await FakeFixtureVariantRepository(self.store, self.assets).delete(variant_id)
        del self.store.fixtures[id]
        return True


class FakeFixtureVariantRepository:
    def __init__(self, store: FakeFixtureStore, assets: FakeAssetRepository):
        self.store = store
        self.assets = assets

    def _attach(self, variant: FixtureVariant) -> FixtureVariant:
        model = self.assets.store.get(variant.model_3d_file_id) if variant.model_3d_file_id else None
        set_committed_value(variant, "model_3d_file", model)
        images = [
            FakeFixtureVariantImageRepository(self.store, self.assets)._attach(img)
            for img in self.store.images.values()
            if img.variant_id == variant.id
        ]
        set_committed_value(variant, "images", images)
        return variant

    async def create(self, entity: FixtureVariant) -> FixtureVariant:
        _stamp(entity)
        self.store.variants[entity.id] = entity
        return self._attach(entity)

    async def get_by_id(self, id: UUID) -> FixtureVariant | None:
        variant = self.store.variants.get(id)
        return self._attach(variant) if variant else None

    async def get_with_fixture(self, id: UUID) -> FixtureVariant | None:
        variant = self.store.variants.get(id)
        if variant is None:
            return None
        self._attach(variant)
        fixture = self.store.fixtures.get(variant.fixture_id)
        if fixture is not None:
            set_committed_value(fixture, "ies_file", self.assets.store.get(fixture.ies_file_id))
            set_committed_value(variant, "fixture", fixture)
        return variant

    async def get_one(self, spec: Specification) -> FixtureVariant | None:
        rows = await self.find(spec, skip=0, limit=1)
        return rows[0] if rows else None

    async def find(self, spec: Specification, skip: int = 0, limit: int = 100) -> Sequence[FixtureVariant]:
        items = [self._attach(v) for v in self.store.variants.values() if _matches(spec, v)]
        return items[skip : skip + limit]

    async def update(self, id: UUID, data: dict) -> FixtureVariant | None:
        entity = self.store.variants.get(id)
        if entity is None:
            return None
        for key, value in data.items():
            setattr(entity, key, value)
        return self._attach(entity)

    async def delete(self, id: UUID) -> bool:
        if id not in self.store.variants:
            return False
        for image_id in [i.id for i in self.store.images.values() if i.variant_id == id]:
            del self.store.images[image_id]
        del self.store.variants[id]
        return True


class FakeFixtureVariantImageRepository:
    def __init__(self, store: FakeFixtureStore, assets: FakeAssetRepository):
        self.store = store
        self.assets = assets

    def _attach(self, image: FixtureVariantImage) -> FixtureVariantImage:
        set_committed_value(image, "image_file", self.assets.store.get(image.image_file_id))
        return image

    async def create(self, entity: FixtureVariantImage) -> FixtureVariantImage:
        _stamp(entity)
        self.store.images[entity.id] = entity
        return self._attach(entity)

    async def get_by_id(self, id: UUID) -> FixtureVariantImage | None:
        image = self.store.images.get(id)
        return self._attach(image) if image else None

    async def get_one(self, spec: Specification) -> FixtureVariantImage | None:
        rows = [img for img in self.store.images.values() if _matches(spec, img)]
        return self._attach(rows[0]) if rows else None

    async def delete(self, id: UUID) -> bool:
        if id not in self.store.images:
            return False
        del self.store.images[id]
        return True
