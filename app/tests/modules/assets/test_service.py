from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.assets.service import AssetService
from app.tests.modules.assets.fakes import FakeAssetRepository, FakeFileStorage
from app.tests.modules.assets.helpers import make_service, make_upload


async def test_create_persists_metadata_and_bytes():
    service, repo, storage = make_service()
    created = await service.create_asset(make_upload())
    assert created.original_filename == "Lamp.IES"
    assert created.mime_type == "application/x-ies"
    assert created.size_bytes == len(b"ies-bytes")
    assert created.relative_path.startswith("assets/")
    assert created.id in repo.store
    assert storage.files[created.relative_path] == b"ies-bytes"


async def test_create_deletes_file_when_db_write_fails():
    storage = FakeFileStorage()
    repo = FakeAssetRepository()

    async def boom(entity):
        raise RuntimeError("db down")

    repo.create = boom  # type: ignore[method-assign]
    service = AssetService(repo, storage)
    with pytest.raises(RuntimeError, match="db down"):
        await service.create_asset(make_upload())
    assert storage.files == {}
    assert storage.delete_calls


async def test_stream_404_when_missing_row():
    service, _, _ = make_service()
    with pytest.raises(HTTPException) as exc:
        await service.stream_asset(uuid4())
    assert exc.value.status_code == 404


async def test_stream_404_when_missing_bytes():
    service, _, storage = make_service()
    created = await service.create_asset(make_upload())
    storage.files.clear()
    with pytest.raises(HTTPException) as exc:
        await service.stream_asset(created.id)
    assert exc.value.status_code == 404


async def test_stream_yields_stored_bytes():
    service, _, _ = make_service()
    created = await service.create_asset(make_upload(data=b"abc"))
    stream = await service.stream_asset(created.id)
    chunks = [chunk async for chunk in stream.chunks]
    assert b"".join(chunks) == b"abc"
    assert stream.asset.original_filename == "Lamp.IES"


async def test_list_filters_name_case_insensitive():
    service, _, _ = make_service()
    await service.create_asset(make_upload(filename="Lamp.IES", data=b"a"))
    await service.create_asset(make_upload(filename="Driver.pdf", data=b"b"))
    items, total = await service.list_assets("lAmP", skip=0, limit=100)
    assert total == 1
    assert items[0].original_filename == "Lamp.IES"


async def test_list_blank_name_returns_all():
    service, _, _ = make_service()
    await service.create_asset(make_upload(filename="a.ies", data=b"a"))
    await service.create_asset(make_upload(filename="b.ies", data=b"b"))
    items, total = await service.list_assets("  ", skip=0, limit=1)
    assert total == 2
    assert len(items) == 1
