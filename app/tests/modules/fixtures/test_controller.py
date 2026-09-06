from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.modules.fixtures.controller import router
from app.modules.fixtures.dependencies import get_fixture_service
from app.modules.fixtures.service import FixtureService
from app.tests.modules.assets.fakes import FakeAssetRepository
from app.tests.modules.fixtures.fakes import (
    FakeFixtureRepository,
    FakeFixtureStore,
    FakeFixtureVariantImageRepository,
    FakeFixtureVariantRepository,
)
from app.tests.modules.fixtures.helpers import seed_asset


class FakeFixtureService(FixtureService):
    def __init__(self) -> None:
        assets = FakeAssetRepository()
        store = FakeFixtureStore()
        super().__init__(
            FakeFixtureRepository(store, assets),
            FakeFixtureVariantRepository(store, assets),
            FakeFixtureVariantImageRepository(store, assets),
            assets,
        )
        self.assets = assets


def _app(service: FakeFixtureService | None = None) -> tuple[FastAPI, FakeFixtureService]:
    service = service or FakeFixtureService()
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_fixture_service] = lambda: service
    return app, service


@pytest.fixture
def service() -> FakeFixtureService:
    return FakeFixtureService()


@pytest.fixture
async def client(service: FakeFixtureService):
    app, _ = _app(service)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def test_create_list_get_delete(client: AsyncClient, service: FakeFixtureService):
    ies = seed_asset(service.assets)
    created = await client.post(
        "/api/v1/fixtures/",
        json={
            "manufacturer_name": "Acme",
            "name": "High Bay",
            "ies_file_id": str(ies.id),
            "applications": ["interior"],
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["success"] is True
    assert body["pagination"] is None
    assert "variants" not in body["data"]
    fixture_id = body["data"]["id"]

    listed = await client.get("/api/v1/fixtures/", params={"q": "high", "application": "interior"})
    assert listed.status_code == 200
    assert listed.json()["pagination"]["total_count"] == 1
    assert "variants" not in listed.json()["data"][0]

    variant = await client.post(
        f"/api/v1/fixtures/{fixture_id}/variants/",
        json={
            "name": "36W",
            "power": 36,
            "chip": "2835",
            "driver": "MW",
            "power_factor": 0.95,
            "cri": 80,
            "efficacy": 140,
        },
    )
    assert variant.status_code == 201
    variant_id = variant.json()["data"]["id"]
    assert variant.json()["data"]["images"] == []

    pic = seed_asset(service.assets, "pic.png")
    image = await client.post(
        f"/api/v1/fixtures/{fixture_id}/variants/{variant_id}/images/",
        json={"image_file_id": str(pic.id)},
    )
    assert image.status_code == 201

    got_variant = await client.get(f"/api/v1/fixtures/{fixture_id}/variants/{variant_id}")
    assert got_variant.status_code == 200
    nested = got_variant.json()["data"]["fixture"]
    assert nested["id"] == fixture_id
    assert nested["name"] == "High Bay"
    assert "variants" not in nested
    assert nested["ies_file"]["original_filename"] == "file.ies"

    detail = await client.get(f"/api/v1/fixtures/{fixture_id}")
    assert detail.status_code == 200
    data = detail.json()["data"]
    assert len(data["variants"]) == 1
    assert len(data["variants"][0]["images"]) == 1
    assert "fixture" not in data["variants"][0]

    deleted = await client.delete(f"/api/v1/fixtures/{fixture_id}")
    assert deleted.status_code == 204
    assert deleted.content == b""


async def test_missing_asset_404(client: AsyncClient):
    response = await client.post(
        "/api/v1/fixtures/",
        json={
            "manufacturer_name": "Acme",
            "name": "X",
            "ies_file_id": str(uuid4()),
            "applications": ["interior"],
        },
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Asset not found"}


async def test_duplicate_variant_409(client: AsyncClient, service: FakeFixtureService):
    ies = seed_asset(service.assets)
    created = await client.post(
        "/api/v1/fixtures/",
        json={
            "manufacturer_name": "Acme",
            "name": "High Bay",
            "ies_file_id": str(ies.id),
            "applications": ["interior"],
        },
    )
    fixture_id = created.json()["data"]["id"]
    payload = {
        "name": "36W",
        "power": 36,
        "chip": "2835",
        "driver": "MW",
        "power_factor": 0.95,
        "cri": 80,
        "efficacy": 140,
    }
    assert (await client.post(f"/api/v1/fixtures/{fixture_id}/variants/", json=payload)).status_code == 201
    dup = await client.post(f"/api/v1/fixtures/{fixture_id}/variants/", json=payload)
    assert dup.status_code == 409
    assert dup.json() == {"detail": "Variant name already exists on this fixture"}


async def test_create_rejects_duplicate_applications(client: AsyncClient, service: FakeFixtureService):
    ies = seed_asset(service.assets)
    response = await client.post(
        "/api/v1/fixtures/",
        json={
            "manufacturer_name": "Acme",
            "name": "X",
            "ies_file_id": str(ies.id),
            "applications": ["interior", "interior"],
        },
    )
    assert response.status_code == 422
