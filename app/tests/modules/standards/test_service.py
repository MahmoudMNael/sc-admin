import pytest
from fastapi import HTTPException

from app.modules.standards.dto import CreateManyStandardsRequest, UpdateStandardRequest
from app.modules.standards.service import StandardService, compute_content_hash
from app.tests.modules.standards.fakes import FakeStandardRepository
from app.tests.modules.standards.helpers import sample_payload, seed_standard


def _service() -> tuple[StandardService, FakeStandardRepository]:
    repo = FakeStandardRepository()
    return StandardService(repo), repo


async def test_create_computes_hash_and_timestamps():
    service, repo = _service()
    payload = sample_payload()
    dumped = payload.model_dump()
    assert "content_hash" not in dumped

    result = await service.create_standard(payload)

    assert len(repo.create_calls) == 1
    created = repo.create_calls[0]
    assert created.content_hash == compute_content_hash(payload.model_dump())
    assert created.content_hash == result.content_hash
    assert created.created_at is not None
    assert created.updated_at == created.created_at
    assert created.qdrant_point_id == payload.qdrant_point_id
    assert created.id == payload.id


async def test_create_identical_content_is_idempotent():
    service, repo = _service()
    payload = sample_payload()
    first = await service.create_standard(payload)
    second = await service.create_standard(payload)

    assert first.id == second.id
    assert first.content_hash == second.content_hash
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
        await service.create_standard(sample_payload(id="other_standard", qdrant_point_id=1))
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


async def test_reject_duplicate_ids_in_batch():
    service, _repo = _service()
    payload = CreateManyStandardsRequest(
        items=[sample_payload(), sample_payload(qdrant_point_id=2)],
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
    taken_point = seed_standard(
        repo,
        sample_payload(id="already_here", qdrant_point_id=99, activity="other"),
    )

    payload = CreateManyStandardsRequest(
        items=[
            sample_payload(),  # same id as existing — skip
            sample_payload(id="brand_new", qdrant_point_id=99),  # point taken — skip
            sample_payload(id="genuinely_new", qdrant_point_id=7),
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
