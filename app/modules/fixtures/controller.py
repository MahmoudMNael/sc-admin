from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.modules.fixtures.models import FixtureApplication
from app.shared.dto.error import ErrorResponse
from app.shared.dto.pagination import PaginationMeta, PaginationQuery
from app.shared.dto.response import ApiResponse

from .dependencies import FixtureServiceDep
from .dto import (
    CreateFixtureRequest,
    CreateVariantImageRequest,
    CreateVariantRequest,
    FixtureResponse,
    FixtureSummaryResponse,
    UpdateFixtureRequest,
    UpdateVariantRequest,
    VariantDetailResponse,
    VariantImageResponse,
    VariantResponse,
)

router = APIRouter(prefix="/fixtures", tags=["Fixtures"])

RESP_400 = {status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse}}
RESP_404 = {status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}}
RESP_409 = {status.HTTP_409_CONFLICT: {"model": ErrorResponse}}


@router.post(
    "/",
    response_model=ApiResponse[FixtureSummaryResponse],
    status_code=status.HTTP_201_CREATED,
    responses={**RESP_404},
)
async def create_fixture(payload: CreateFixtureRequest, service: FixtureServiceDep):
    return ApiResponse(data=await service.create_fixture(payload))


@router.get("/", response_model=ApiResponse[list[FixtureSummaryResponse]])
async def list_fixtures(
    service: FixtureServiceDep,
    pagination: Annotated[PaginationQuery, Depends()],
    q: Annotated[str | None, Query()] = None,
    application: Annotated[FixtureApplication | None, Query()] = None,
    is_main_solution: Annotated[bool | None, Query()] = None,
):
    items, total = await service.list_fixtures(
        q,
        application.value if application else None,
        is_main_solution,
        pagination.skip,
        pagination.limit,
    )
    return ApiResponse(
        data=items,
        pagination=PaginationMeta.from_query(total, pagination.page, pagination.limit),
    )


@router.get("/variants/", response_model=ApiResponse[list[VariantDetailResponse]])
async def list_all_variants(
    service: FixtureServiceDep,
    pagination: Annotated[PaginationQuery, Depends()],
    q: Annotated[str | None, Query()] = None,
    application: Annotated[FixtureApplication | None, Query()] = None,
    is_main_solution: Annotated[bool | None, Query()] = None,
    fixture_id: Annotated[UUID | None, Query()] = None,
):
    items, total = await service.list_variants(
        q,
        application.value if application else None,
        is_main_solution,
        fixture_id,
        pagination.skip,
        pagination.limit,
    )
    return ApiResponse(
        data=items,
        pagination=PaginationMeta.from_query(total, pagination.page, pagination.limit),
    )


@router.get(
    "/{fixture_id}",
    response_model=ApiResponse[FixtureResponse],
    responses={**RESP_404},
)
async def get_fixture(fixture_id: UUID, service: FixtureServiceDep):
    return ApiResponse(data=await service.get_fixture(fixture_id))


@router.patch(
    "/{fixture_id}",
    response_model=ApiResponse[FixtureSummaryResponse],
    responses={**RESP_400, **RESP_404},
)
async def update_fixture(fixture_id: UUID, payload: UpdateFixtureRequest, service: FixtureServiceDep):
    return ApiResponse(data=await service.update_fixture(fixture_id, payload))


@router.delete("/{fixture_id}", status_code=status.HTTP_204_NO_CONTENT, responses={**RESP_404})
async def delete_fixture(fixture_id: UUID, service: FixtureServiceDep):
    await service.delete_fixture(fixture_id)


@router.post(
    "/{fixture_id}/variants/",
    response_model=ApiResponse[VariantResponse],
    status_code=status.HTTP_201_CREATED,
    responses={**RESP_404, **RESP_409},
)
async def create_variant(fixture_id: UUID, payload: CreateVariantRequest, service: FixtureServiceDep):
    return ApiResponse(data=await service.create_variant(fixture_id, payload))


@router.get(
    "/{fixture_id}/variants/",
    response_model=ApiResponse[list[VariantDetailResponse]],
    responses={**RESP_404},
)
async def list_fixture_variants(
    fixture_id: UUID,
    service: FixtureServiceDep,
    pagination: Annotated[PaginationQuery, Depends()],
    q: Annotated[str | None, Query()] = None,
    application: Annotated[FixtureApplication | None, Query()] = None,
    is_main_solution: Annotated[bool | None, Query()] = None,
):
    items, total = await service.list_variants(
        q,
        application.value if application else None,
        is_main_solution,
        fixture_id,
        pagination.skip,
        pagination.limit,
    )
    return ApiResponse(
        data=items,
        pagination=PaginationMeta.from_query(total, pagination.page, pagination.limit),
    )


@router.get(
    "/{fixture_id}/variants/{variant_id}",
    response_model=ApiResponse[VariantDetailResponse],
    responses={**RESP_404},
)
async def get_variant(fixture_id: UUID, variant_id: UUID, service: FixtureServiceDep):
    return ApiResponse(data=await service.get_variant(fixture_id, variant_id))


@router.patch(
    "/{fixture_id}/variants/{variant_id}",
    response_model=ApiResponse[VariantResponse],
    responses={**RESP_400, **RESP_404, **RESP_409},
)
async def update_variant(
    fixture_id: UUID, variant_id: UUID, payload: UpdateVariantRequest, service: FixtureServiceDep
):
    return ApiResponse(data=await service.update_variant(fixture_id, variant_id, payload))


@router.delete(
    "/{fixture_id}/variants/{variant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**RESP_404},
)
async def delete_variant(fixture_id: UUID, variant_id: UUID, service: FixtureServiceDep):
    await service.delete_variant(fixture_id, variant_id)


@router.post(
    "/{fixture_id}/variants/{variant_id}/images/",
    response_model=ApiResponse[VariantImageResponse],
    status_code=status.HTTP_201_CREATED,
    responses={**RESP_404, **RESP_409},
)
async def create_variant_image(
    fixture_id: UUID, variant_id: UUID, payload: CreateVariantImageRequest, service: FixtureServiceDep
):
    return ApiResponse(data=await service.create_variant_image(fixture_id, variant_id, payload))


@router.delete(
    "/{fixture_id}/variants/{variant_id}/images/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**RESP_404},
)
async def delete_variant_image(
    fixture_id: UUID, variant_id: UUID, image_id: UUID, service: FixtureServiceDep
):
    await service.delete_variant_image(fixture_id, variant_id, image_id)
