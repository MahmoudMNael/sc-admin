from datetime import datetime, timezone

from app.modules.standards.dto import CreateStandardRequest
from app.modules.standards.models import Standard
from app.modules.standards.service import StandardService, compute_content_hash
from app.shared.utils import generate_qdrant_point_id

from .fakes import FakeStandardRepository


def sample_hierarchy(**overrides) -> dict:
    data = {
        "category_table_number": "6.1",
        "category_title": "Indoor workplaces",
        "ref_number": "6.1.1",
        "page": 42,
    }
    data.update(overrides)
    return data


def sample_payload(**overrides) -> CreateStandardRequest:
    data = {
        "id": "en12464_1_v2019_6_1_1",
        "standard_metadata": {
            "standard_code": "EN 12464-1",
            "version_year": "2019",
            "is_latest": True,
        },
        "hierarchy": sample_hierarchy(),
        "activity": "Parking areas",
        "parameters": {"em_r_lx": 50.0},
        "specific_requirements": None,
        "searchable_text": "parking areas indoor lighting",
    }
    data.update(overrides)
    return CreateStandardRequest.model_validate(data)


def sample_json(**overrides) -> dict:
    return sample_payload(**overrides).model_dump(by_alias=True)


class FakeStandardService(StandardService):
    """Real service + in-memory repo. Never touches Mongo or disk."""

    def __init__(self) -> None:
        super().__init__(FakeStandardRepository())


def seed_standard(repo: FakeStandardRepository, payload: CreateStandardRequest | None = None) -> Standard:
    payload = payload or sample_payload()
    data = payload.model_dump()
    now = datetime.now(timezone.utc)
    entity = Standard(
        **data,
        qdrant_point_id=generate_qdrant_point_id(data),
        content_hash=compute_content_hash(data),
        created_at=now,
        updated_at=now,
    )
    repo.store[entity.id] = entity
    return entity
