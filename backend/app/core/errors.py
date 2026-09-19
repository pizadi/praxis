from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

ERROR_ENVELOPE_EXEMPT_STATUS = {204}


def error_response(status_code: int, code: str, message: str, details: Any = None) -> JSONResponse:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=body)


class ConflictError(Exception):
    """409 — duplicate name / national ID, etc."""

    def __init__(
        self, message: str, code: str = "conflict", details: Any = None
    ) -> None:
        self.message = message
        self.code = code
        self.details = details


class BusinessRuleError(Exception):
    """422 — semantically invalid operation (bad date range, etc.)."""

    def __init__(
        self, message: str, code: str = "business_rule", details: Any = None
    ) -> None:
        self.message = message
        self.code = code
        self.details = details


class NotFoundError(Exception):
    """404 with machine-readable code."""

    def __init__(self, message: str = "Resource not found", code: str = "not_found") -> None:
        self.message = message
        self.code = code


class RateLimitedError(Exception):
    """429 — too many attempts (login lockout, etc.)."""

    def __init__(self, message: str, code: str = "rate_limited", details: Any = None) -> None:
        self.message = message
        self.code = code
        self.details = details


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return error_response(
            exc.status_code,
            code=f"http_{exc.status_code}",
            message=str(exc.detail),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return error_response(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="validation_error",
            message="Invalid request data.",
            details=exc.errors(),
        )

    @app.exception_handler(ConflictError)
    async def conflict_handler(_: Request, exc: ConflictError) -> JSONResponse:
        return error_response(
            status.HTTP_409_CONFLICT, code=exc.code, message=exc.message, details=exc.details
        )

    @app.exception_handler(BusinessRuleError)
    async def business_rule_handler(_: Request, exc: BusinessRuleError) -> JSONResponse:
        return error_response(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )

    @app.exception_handler(NotFoundError)
    async def not_found_handler(_: Request, exc: NotFoundError) -> JSONResponse:
        return error_response(
            status.HTTP_404_NOT_FOUND, code=exc.code, message=exc.message
        )

    @app.exception_handler(RateLimitedError)
    async def rate_limited_handler(_: Request, exc: RateLimitedError) -> JSONResponse:
        return error_response(
            status.HTTP_429_TOO_MANY_REQUESTS, code=exc.code, message=exc.message,
            details=exc.details,
        )
