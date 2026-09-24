from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

ERROR_ENVELOPE_EXEMPT_STATUS = {204}


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=body, headers=headers)


class ApiError(Exception):
    """Base class for application errors using the public error envelope."""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_code = "api_error"

    def __init__(
        self,
        message: str,
        code: str | None = None,
        details: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.default_code
        self.details = details
        self.headers = headers


class ConflictError(ApiError):
    """409 — duplicate name / national ID, etc."""

    status_code = status.HTTP_409_CONFLICT
    default_code = "conflict"


class BusinessRuleError(ApiError):
    """422 — semantically invalid operation (bad date range, etc.)."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_code = "business_rule"


class NotFoundError(ApiError):
    """404 with a machine-readable code."""

    status_code = status.HTTP_404_NOT_FOUND
    default_code = "not_found"


class AuthenticationError(ApiError):
    """401 — missing, expired, or invalid authentication."""

    status_code = status.HTTP_401_UNAUTHORIZED
    default_code = "unauthorized"

    def __init__(
        self,
        message: str,
        code: str | None = None,
        details: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            message,
            code,
            details,
            headers or {"WWW-Authenticate": "Bearer"},
        )


class AuthorizationError(ApiError):
    """403 — authenticated but lacking the required permission."""

    status_code = status.HTTP_403_FORBIDDEN
    default_code = "forbidden"


class PayloadTooLargeError(ApiError):
    """413 — streamed upload exceeded the configured limit."""

    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_code = "payload_too_large"


class RateLimitedError(ApiError):
    """429 — too many attempts (login lockout, etc.)."""

    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_code = "rate_limited"


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return error_response(
            exc.status_code,
            code=f"http_{exc.status_code}",
            message=str(exc.detail),
            headers=dict(exc.headers) if exc.headers is not None else None,
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

    @app.exception_handler(ApiError)
    async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
        return error_response(
            exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
            headers=exc.headers,
        )
