import pytest
from fastapi import HTTPException

from app.modules.standards.dto import (
    CreateManyStandardsRequest,
    UpdateStandardMetadataRequest,
    UpdateStandardRequest,
)
from app.modules.standards.service import StandardService, compute_content_hash, point_id_for
from app.tests.modules.standards.fakes import FakeStandardRepository
from app.tests.modules.standards.helpers import sample_hierarchy, sample_payload, seed_standard


def _service() -> tuple[StandardService, FakeStandardRepository]:
    repo = FakeStandardRepository()
    return StandardService(repo), repo


async def test_create_computes_hash_timestamps_and_point_id():
    service, repo = _service()
    payload = sample_payload()
    dumped = payload.model_dump()
    assert "content_hash" not in dumped
    assert "qdrant_point_id" not in dumped

    result = await service.create_standard(payload)

    assert len(repo.create_calls) == 1
    created = repo.create_calls[0]
    assert created.content_hash == compute_content_hash(payload.model_dump())
    assert created.content_hash == result.content_hash
    assert created.qdrant_point_id == point_id_for(payload)
    assert created.qdrant_point_id == result.qdrant_point_id
    assert created.created_at is not None
    assert created.updated_at == created.created_at
    assert created.id == payload.id


async def test_create_identical_content_is_idempotent():
    service, repo = _service()
    payload = sample_payload()
    first = await service.create_standard(payload)
    second = await service.create_standard(payload)

    assert first.id == second.id
    assert first.content_hash == second.content_hash
    assert first.qdrant_point_id == second.qdrant_point_id
    assert len(repo.create_calls) == 1
    assert len(repo.store) == 1


async def test_create_same_id_different_content_conflicts():
    service, _repo = _service()
    await service.create_standard(sample_payload())
    with pytest.raises(HTTPException) as exc:
        await service.create_standard(sample_payload(activity="Something else"))
    assert exc.value.status_code == 409


async def test_create_taken_qdrant_point_id_conflicts():
    service, _repo = _service()
    await service.create_standard(sample_payload())
    with pytest.raises(HTTPException) as exc:
        await service.create_standard(sample_payload(id="other_standard"))
    assert exc.value.status_code == 409


async def test_patch_recomputes_hash_and_keeps_point_id():
    service, repo = _service()
    original = await service.create_standard(sample_payload())
    updated = await service.update_standard(original.id, UpdateStandardRequest(activity="New activity"))

    assert updated.qdrant_point_id == original.qdrant_point_id
    assert updated.activity == "New activity"
    assert updated.content_hash != original.content_hash
    stored = repo.store[original.id]
    assert stored.qdrant_point_id == original.qdrant_point_id
    assert stored.content_hash == updated.content_hash


async def test_patch_metadata_keeps_identity_fields():
    service, _repo = _service()
    original = await service.create_standard(sample_payload())
    updated = await service.update_standard(
        original.id,
        UpdateStandardRequest(standard_metadata=UpdateStandardMetadataRequest(is_latest=False)),
    )
    assert updated.standard_metadata.standard_code == original.standard_metadata.standard_code
    assert updated.standard_metadata.version_year == original.standard_metadata.version_year
    assert updated.standard_metadata.is_latest is False
    assert updated.qdrant_point_id == original.qdrant_point_id


async def test_reject_duplicate_ids_in_batch():
    service, _repo = _service()
    payload = CreateManyStandardsRequest(
        items=[
            sample_payload(),
            sample_payload(hierarchy=sample_hierarchy(ref_number="6.1.2")),
        ],
    )
    with pytest.raises(HTTPException) as exc:
        service.reject_duplicate_keys(payload)
    assert exc.value.status_code == 400


async def test_reject_duplicate_point_ids_in_batch():
    service, _repo = _service()
    payload = CreateManyStandardsRequest(
        items=[sample_payload(), sample_payload(id="other_standard")],
    )
    with pytest.raises(HTTPException) as exc:
        service.reject_duplicate_keys(payload)
    assert exc.value.status_code == 400


async def test_create_many_inserts_only_new_items():
    service, repo = _service()
    existing = seed_standard(repo, sample_payload())
    taken_hierarchy = sample_hierarchy(category_table_number="6.13", ref_number="6.13.1")
    taken_point = seed_standard(
        repo,
        sample_payload(id="already_here", activity="other", hierarchy=taken_hierarchy),
    )

    payload = CreateManyStandardsRequest(
        items=[
            sample_payload(),  # same id as existing — skip
            sample_payload(id="brand_new", hierarchy=taken_hierarchy),  # same identity as taken_point — skip
            sample_payload(
                id="genuinely_new",
                hierarchy=sample_hierarchy(category_table_number="7.1", ref_number="7.1.1"),
            ),
        ]
    )
    await service.create_many_standards(payload)

    assert existing.id in repo.store
    assert taken_point.id in repo.store
    assert "genuinely_new" in repo.store
    assert "brand_new" not in repo.store
    assert len(repo.create_many_calls) == 1
    assert [e.id for e in repo.create_many_calls[0]] == ["genuinely_new"]


async def test_get_missing_standard_404():
    service, _repo = _service()
    with pytest.raises(HTTPException) as exc:
        await service.get_standard("missing")
    assert exc.value.status_code == 404


async def test_empty_patch_400():
    service, _repo = _service()
    created = await service.create_standard(sample_payload())
    with pytest.raises(HTTPException) as exc:
        await service.update_standard(created.id, UpdateStandardRequest())
    assert exc.value.status_code == 400


async def test_list_returns_items_and_total():
    service, repo = _service()
    await service.create_standard(sample_payload())
    await service.create_standard(
        sample_payload(id="second", hierarchy=sample_hierarchy(ref_number="6.1.2"))
    )
    items, total = await service.list_standards(
        None, None, None, None, None, [], "any", skip=0, limit=1
    )
    assert total == 2
    assert len(items) == 1
    assert len(repo.store) == 2
