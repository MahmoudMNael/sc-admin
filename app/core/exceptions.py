from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.shared.dto.error import ErrorResponse


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(detail=detail).model_dump(),
            headers=exc.headers,
        )
