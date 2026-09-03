from typing import Generic, Literal, TypeVar

from pydantic import BaseModel

from app.shared.dto.pagination import PaginationMeta

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    success: Literal[True] = True
    data: T
    pagination: PaginationMeta | None = None
