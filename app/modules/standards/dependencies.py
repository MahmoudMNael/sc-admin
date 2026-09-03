from typing import Annotated

from fastapi import Depends

from .repository import StandardRepository
from .service import StandardService


def get_standard_repository() -> StandardRepository:
    return StandardRepository()


def get_standard_service(
    repo: Annotated[StandardRepository, Depends(get_standard_repository)],
) -> StandardService:
    return StandardService(repo)


StandardServiceDep = Annotated[StandardService, Depends(get_standard_service)]
