import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.modules.assets.controller import router
from app.modules.assets.dependencies import get_asset_service
from app.modules.assets.service import AssetService
from app.tests.modules.assets.fakes import FakeAssetRepository, FakeFileStorage


class FakeAssetService(AssetService):
    def __init__(self) -> None:
        super().__init__(FakeAssetRepository(), FakeFileStorage())


def _app(service: FakeAssetService | None = None) -> tuple[FastAPI, FakeAssetService]:
    service = service or FakeAssetService()
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_asset_service] = lambda: service
    return app, service


@pytest.fixture
def service() -> FakeAssetService:
    return FakeAssetService()


@pytest.fixture
async def client(service: FakeAssetService):
    app, _ = _app(service)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def test_create_returns_201(client: AsyncClient):
    response = await client.post(
        "/api/v1/assets/",
        files={"file": ("Lamp.IES", b"ies-bytes", "application/x-ies")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["pagination"] is None
    data = body["data"]
    assert data["original_filename"] == "Lamp.IES"
    assert data["mime_type"] == "application/x-ies"
    assert data["size_bytes"] == 9
    assert data["relative_path"].startswith("assets/")
    assert data["id"]
    assert data["created_at"]


async def test_list_paginates_and_searches_name(client: AsyncClient):
    await client.post("/api/v1/assets/", files={"file": ("Lamp.IES", b"a", "application/x-ies")})
    await client.post("/api/v1/assets/", files={"file": ("Driver.pdf", b"b", "application/pdf")})
    listed = await client.get("/api/v1/assets/", params={"page": 1, "limit": 100, "name": "lamp"})
    assert listed.status_code == 200
    body = listed.json()
    assert body["success"] is True
    assert body["pagination"]["total_count"] == 1
    assert body["data"][0]["original_filename"] == "Lamp.IES"


async def test_get_file_streams_bytes(client: AsyncClient):
    created = await client.post(
        "/api/v1/assets/",
        files={"file": ("Lamp.IES", b"ies-bytes", "application/x-ies")},
    )
    asset_id = created.json()["data"]["id"]
    response = await client.get(f"/api/v1/assets/{asset_id}")
    assert response.status_code == 200
    assert response.content == b"ies-bytes"
    assert response.headers["content-type"].startswith("application/x-ies")
    assert "Lamp.IES" in response.headers["content-disposition"]
    assert "success" not in response.text


async def test_get_file_404(client: AsyncClient):
    response = await client.get("/api/v1/assets/00000000-0000-4000-8000-000000000000")
    assert response.status_code == 404
    assert response.json() == {"detail": "Asset not found"}
