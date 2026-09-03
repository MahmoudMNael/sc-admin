import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.modules.standards.controller import router
from app.modules.standards.dependencies import get_standard_service
from app.modules.standards.service import point_id_for
from app.tests.modules.standards.helpers import FakeStandardService, sample_hierarchy, sample_json, sample_payload


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
    assert body["success"] is True
    assert body["pagination"] is None
    data = body["data"]
    assert data["id"] == "en12464_1_v2019_6_1_1"
    assert data["qdrant_point_id"] == point_id_for(sample_payload())
    assert "content_hash" in data
    assert data["content_hash"]
    assert "created_at" in data
    assert "updated_at" in data


async def test_create_unknown_field_422(client: AsyncClient):
    payload = sample_json()
    payload["not_a_field"] = "nope"
    response = await client.post("/api/v1/standards/", json=payload)
    assert response.status_code == 422


async def test_create_rejects_client_qdrant_point_id(client: AsyncClient):
    payload = sample_json()
    payload["qdrant_point_id"] = "00000000-0000-0000-0000-000000000000"
    response = await client.post("/api/v1/standards/", json=payload)
    assert response.status_code == 422


async def test_bulk_returns_202_without_blocking(client: AsyncClient):
    payload = {
        "items": [
            sample_json(),
            sample_json(id="second", hierarchy=sample_hierarchy(ref_number="6.1.2")),
        ]
    }
    response = await client.post("/api/v1/standards/bulk", json=payload)
    assert response.status_code == 202
    assert response.json() == {
        "success": True,
        "data": {"status": "accepted", "item_count": 2},
        "pagination": None,
    }


async def test_bulk_duplicate_ids_400(client: AsyncClient):
    payload = {
        "items": [
            sample_json(),
            sample_json(hierarchy=sample_hierarchy(ref_number="6.1.2")),
        ]
    }
    response = await client.post("/api/v1/standards/bulk", json=payload)
    assert response.status_code == 400


async def test_patch_rejects_qdrant_point_id(client: AsyncClient):
    await client.post("/api/v1/standards/", json=sample_json())
    response = await client.patch(
        "/api/v1/standards/en12464_1_v2019_6_1_1",
        json={"qdrant_point_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert response.status_code == 422


async def test_patch_rejects_identity_fields(client: AsyncClient):
    await client.post("/api/v1/standards/", json=sample_json())
    response = await client.patch(
        "/api/v1/standards/en12464_1_v2019_6_1_1",
        json={"standard_metadata": {"standard_code": "other", "is_latest": False}},
    )
    assert response.status_code == 422
    response = await client.patch(
        "/api/v1/standards/en12464_1_v2019_6_1_1",
        json={"hierarchy": {"ref_number": "9.9.9", "page": 1}},
    )
    assert response.status_code == 422


async def test_patch_rejects_content_hash(client: AsyncClient):
    await client.post("/api/v1/standards/", json=sample_json())
    response = await client.patch(
        "/api/v1/standards/en12464_1_v2019_6_1_1",
        json={"content_hash": "abc"},
    )
    assert response.status_code == 422


async def test_list_paginates(client: AsyncClient):
    await client.post("/api/v1/standards/", json=sample_json())
    await client.post(
        "/api/v1/standards/",
        json=sample_json(id="second", hierarchy=sample_hierarchy(ref_number="6.1.2")),
    )
    await client.post(
        "/api/v1/standards/",
        json=sample_json(id="third", hierarchy=sample_hierarchy(ref_number="6.1.3")),
    )
    response = await client.get("/api/v1/standards/", params={"page": 1, "limit": 2})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert len(body["data"]) == 2
    assert body["pagination"] == {
        "total_count": 3,
        "page_size": 2,
        "current_page": 1,
        "total_pages": 2,
    }
    page2 = await client.get("/api/v1/standards/", params={"page": 2, "limit": 2})
    assert page2.status_code == 200
    assert len(page2.json()["data"]) == 1
    assert page2.json()["pagination"]["current_page"] == 2


async def test_list_rejects_page_zero(client: AsyncClient):
    response = await client.get("/api/v1/standards/", params={"page": 0})
    assert response.status_code == 422


async def test_get_one_wraps_without_pagination(client: AsyncClient):
    await client.post("/api/v1/standards/", json=sample_json())
    response = await client.get("/api/v1/standards/en12464_1_v2019_6_1_1")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["pagination"] is None
    assert body["data"]["id"] == "en12464_1_v2019_6_1_1"


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


async def test_openapi_omits_computed_and_immutable_fields(client: AsyncClient):
    spec = (await client.get("/openapi.json")).json()
    schemas = spec["components"]["schemas"]
    create = schemas["CreateStandardRequest"]
    assert "qdrant_point_id" not in create.get("properties", {})
    assert "content_hash" not in create.get("properties", {})
    update = schemas["UpdateStandardRequest"]
    props = update.get("properties", {})
    assert "qdrant_point_id" not in props
    assert "content_hash" not in props
    assert update.get("additionalProperties") is False
    meta = schemas["UpdateStandardMetadataRequest"]["properties"]
    assert "standard_code" not in meta
    assert "version_year" not in meta
    hier = schemas["UpdateStandardHierarchyRequest"]["properties"]
    assert "category_table_number" not in hier
    assert "ref_number" not in hier
