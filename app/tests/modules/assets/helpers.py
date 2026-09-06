from io import BytesIO

from starlette.datastructures import Headers, UploadFile

from app.modules.assets.service import AssetService

from .fakes import FakeAssetRepository, FakeFileStorage


def make_upload(filename: str = "Lamp.IES", data: bytes = b"ies-bytes", content_type: str = "application/x-ies") -> UploadFile:
    return UploadFile(
        filename=filename,
        file=BytesIO(data),
        headers=Headers({"content-type": content_type}),
    )


def make_service() -> tuple[AssetService, FakeAssetRepository, FakeFileStorage]:
    repo = FakeAssetRepository()
    storage = FakeFileStorage()
    return AssetService(repo, storage), repo, storage
