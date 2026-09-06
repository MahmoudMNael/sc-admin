from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from app.modules.assets.models import Asset
from app.modules.fixtures.dto import CreateFixtureRequest, CreateVariantRequest
from app.modules.fixtures.models import FixtureApplication
from app.modules.fixtures.service import FixtureService
from app.tests.modules.assets.fakes import FakeAssetRepository
from app.tests.modules.fixtures.fakes import (
    FakeFixtureRepository,
    FakeFixtureStore,
    FakeFixtureVariantImageRepository,
    FakeFixtureVariantRepository,
)


def seed_asset(assets: FakeAssetRepository, filename: str = "file.ies") -> Asset:
    asset = Asset(
        id=uuid4(),
        relative_path=f"assets/{uuid4().hex}.bin",
        original_filename=filename,
        mime_type="application/octet-stream",
        size_bytes=8,
        created_at=datetime.now(timezone.utc),
    )
    assets.store[asset.id] = asset
    return asset


def make_service() -> tuple[
    FixtureService,
    FakeAssetRepository,
    FakeFixtureRepository,
    FakeFixtureVariantRepository,
    FakeFixtureVariantImageRepository,
]:
    assets = FakeAssetRepository()
    store = FakeFixtureStore()
    fixtures = FakeFixtureRepository(store, assets)
    variants = FakeFixtureVariantRepository(store, assets)
    images = FakeFixtureVariantImageRepository(store, assets)
    return FixtureService(fixtures, variants, images, assets), assets, fixtures, variants, images


def fixture_payload(ies_file_id, **overrides) -> CreateFixtureRequest:
    data = {
        "manufacturer_name": "Acme",
        "name": "High Bay",
        "ies_file_id": ies_file_id,
        "is_main_solution": False,
        "applications": [FixtureApplication.INTERIOR],
    }
    data.update(overrides)
    return CreateFixtureRequest.model_validate(data)


def variant_payload(**overrides) -> CreateVariantRequest:
    data = {
        "name": "36W",
        "power": 36,
        "chip": "2835",
        "driver": "Meanwell",
        "power_factor": Decimal("0.95"),
        "cri": Decimal(80),
        "efficacy": 140,
        "mechanical_protections": ["IP65"],
        "electrical_protections": ["OV"],
    }
    data.update(overrides)
    return CreateVariantRequest.model_validate(data)
