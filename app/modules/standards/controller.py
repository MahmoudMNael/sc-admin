from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Query, status

from app.shared.dto.error import ErrorResponse

from .dependencies import StandardServiceDep
from .dto import (
    CreateManyStandardsAcceptedResponse,
    CreateManyStandardsRequest,
    CreateStandardRequest,
    StandardResponse,
    UpdateStandardRequest,
)

router = APIRouter(prefix="/standards", tags=["Standards"])

RESP_400 = {status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse}}
RESP_404 = {status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}}
RESP_409 = {status.HTTP_409_CONFLICT: {"model": ErrorResponse}}


@router.post(
    "/",
    response_model=StandardResponse,
    status_code=status.HTTP_201_CREATED,
    responses={**RESP_409},
)
async def create_standard(payload: CreateStandardRequest, service: StandardServiceDep):
    return await service.create_standard(payload)


@router.post(
    "/bulk",
    response_model=CreateManyStandardsAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={**RESP_400},
)
async def create_many_standards(
    payload: CreateManyStandardsRequest,
    service: StandardServiceDep,
    background_tasks: BackgroundTasks,
):
    service.reject_duplicate_keys(payload)
    # ponytail: in-process BackgroundTasks; a crash loses the job. Upgrade to a queue / job document if bulk ingest must be durable.
    background_tasks.add_task(service.create_many_standards, payload)
    return CreateManyStandardsAcceptedResponse(item_count=len(payload.items))


@router.get("/", response_model=list[StandardResponse])
async def list_standards(
    service: StandardServiceDep,
    standard_code: str | None = Query(default=None),
    version_year: str | None = Query(default=None),
    is_latest: bool | None = Query(default=None),
    category_table_number: str | None = Query(default=None),
    activity: str | None = Query(default=None),
    keywords: list[str] = Query(default=[]),
    match_mode: Literal["any", "all"] = Query(default="any"),
    skip: int = 0,
    limit: int = 100,
):
    return await service.list_standards(
        standard_code,
        version_year,
        is_latest,
        category_table_number,
        activity,
        keywords,
        match_mode,
        skip,
        limit,
    )


# NOTE: static paths ("/bulk" above) must be declared before "/{standard_id}" —
# otherwise FastAPI matches them as the path parameter instead.
@router.get("/{standard_id}", response_model=StandardResponse, responses={**RESP_404})
async def get_standard(standard_id: str, service: StandardServiceDep):
    return await service.get_standard(standard_id)


@router.patch(
    "/{standard_id}",
    response_model=StandardResponse,
    responses={**RESP_400, **RESP_404},
)
async def update_standard(standard_id: str, payload: UpdateStandardRequest, service: StandardServiceDep):
    return await service.update_standard(standard_id, payload)


@router.delete("/{standard_id}", status_code=status.HTTP_204_NO_CONTENT, responses={**RESP_404})
async def delete_standard(standard_id: str, service: StandardServiceDep):
    await service.delete_standard(standard_id)
