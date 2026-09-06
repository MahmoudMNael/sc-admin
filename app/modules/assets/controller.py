from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from app.shared.dto.error import ErrorResponse
from app.shared.dto.pagination import PaginationMeta, PaginationQuery
from app.shared.dto.response import ApiResponse

from .dependencies import AssetServiceDep
from .dto import AssetResponse

router = APIRouter(prefix="/assets", tags=["Assets"])

RESP_404 = {status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}}


@router.post(
    "/",
    response_model=ApiResponse[AssetResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_asset(
    service: AssetServiceDep,
    file: Annotated[UploadFile, File()],
):
    return ApiResponse(data=await service.create_asset(file))


@router.get("/", response_model=ApiResponse[list[AssetResponse]])
async def list_assets(
    service: AssetServiceDep,
    pagination: Annotated[PaginationQuery, Depends()],
    name: str | None = Query(default=None),
):
    items, total = await service.list_assets(name, pagination.skip, pagination.limit)
    return ApiResponse(
        data=items,
        pagination=PaginationMeta.from_query(total, pagination.page, pagination.limit),
    )


@router.get("/{asset_id}", responses={**RESP_404})
async def get_asset_file(asset_id: UUID, service: AssetServiceDep):
    stream = await service.stream_asset(asset_id)
    filename = quote(stream.asset.original_filename)
    return StreamingResponse(
        stream.chunks,
        media_type=stream.asset.mime_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
            "Content-Length": str(stream.asset.size_bytes),
        },
    )
