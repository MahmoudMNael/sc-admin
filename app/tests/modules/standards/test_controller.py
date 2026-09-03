import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.modules.standards.controller import router
from app.modules.standards.dependencies import get_standard_service
from app.tests.modules.standards.helpers import FakeStandardService, sample_json


def _app(service: FakeStandardService | None = None) -> tuple[FastAPI, FakeStandardService]:
    service = service or FakeStandardService()
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_standard_service] = lambda: service
    return app, service


@pytest.fixture
def service() -> FakeStandardService:
    return FakeStandardService()


@pytest.fixture
async def client(service: FakeStandardService):
    app, _ = _app(service)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def test_create_returns_201(client: AsyncClient):
    response = await client.post("/api/v1/standards/", json=sample_json())
    assert response.status_code == 201
    body = response.json()
    assert body["id"] == "en12464_1_v2019_6_1_1"
    assert body["qdrant_point_id"] == 1
    assert "content_hash" in body
    assert body["content_hash"]
    assert "created_at" in body
    assert "updated_at" in body


async def test_create_unknown_field_422(client: AsyncClient):
    payload = sample_json()
    payload["not_a_field"] = "nope"
    response = await client.post("/api/v1/standards/", json=payload)
    assert response.status_code == 422


async def test_bulk_returns_202_without_blocking(client: AsyncClient):
    payload = {"items": [sample_json(), sample_json(id="second", qdrant_point_id=2)]}
    response = await client.post("/api/v1/standards/bulk", json=payload)
    assert response.status_code == 202
    assert response.json() == {"status": "accepted", "item_count": 2}


async def test_bulk_duplicate_ids_400(client: AsyncClient):
    payload = {"items": [sample_json(), sample_json(qdrant_point_id=2)]}
    response = await client.post("/api/v1/standards/bulk", json=payload)
    assert response.status_code == 400


async def test_patch_rejects_qdrant_point_id(client: AsyncClient):
    await client.post("/api/v1/standards/", json=sample_json())
    response = await client.patch(
        "/api/v1/standards/en12464_1_v2019_6_1_1",
        json={"qdrant_point_id": 99},
    )
    assert response.status_code == 422


async def test_patch_rejects_content_hash(client: AsyncClient):
    await client.post("/api/v1/standards/", json=sample_json())
    response = await client.patch(
        "/api/v1/standards/en12464_1_v2019_6_1_1",
        json={"content_hash": "abc"},
    )
    assert response.status_code == 422


async def test_get_missing_404(client: AsyncClient):
    response = await client.get("/api/v1/standards/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {"detail": "Standard not found"}


async def test_delete_204(client: AsyncClient):
    await client.post("/api/v1/standards/", json=sample_json())
    response = await client.delete("/api/v1/standards/en12464_1_v2019_6_1_1")
    assert response.status_code == 204
    missing = await client.get("/api/v1/standards/en12464_1_v2019_6_1_1")
    assert missing.status_code == 404


async def test_openapi_update_omits_immutable_fields(client: AsyncClient):
    spec = (await client.get("/openapi.json")).json()
    update = spec["components"]["schemas"]["UpdateStandardRequest"]
    props = update.get("properties", {})
    assert "qdrant_point_id" not in props
    assert "content_hash" not in props
    assert update.get("additionalProperties") is False
    create = spec["components"]["schemas"]["CreateStandardRequest"]
    assert "_id" in create["properties"] or "id" in create["properties"]
    assert "content_hash" not in create.get("properties", {})
