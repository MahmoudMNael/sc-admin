from math import ceil

from pydantic import BaseModel, Field


class PaginationQuery(BaseModel):
    page: int = Field(1, ge=1)
    limit: int = Field(100, ge=1, le=1000)

    @property
    def skip(self) -> int:
        return (self.page - 1) * self.limit


class PaginationMeta(BaseModel):
    total_count: int = Field(..., ge=0)
    page_size: int = Field(..., ge=1)
    current_page: int = Field(..., ge=1)
    total_pages: int = Field(..., ge=0)

    @classmethod
    def from_query(cls, total_count: int, page: int, limit: int) -> "PaginationMeta":
        total_pages = ceil(total_count / limit) if total_count else 0
        return cls(
            total_count=total_count,
            page_size=limit,
            current_page=page,
            total_pages=total_pages,
        )
