import re
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

ERROR_ENVELOPE_EXEMPT_STATUS = {204}

# Uniqueness is enforced by the DATABASE (partial unique indexes — see
# models/domain.py::partial_unique_where), and the endpoints check first so
# they can return a friendly 409. That check is inherently racy: two
# concurrent creates both pass it and the loser trips the index. This table
# turns the database's own verdict into the same envelope instead of a 500.
#
# Keyed by the constraint as each dialect names it: PostgreSQL reports the
# index name, SQLite reports "table.column". Both spellings map to the same
# (code, message) the pre-check raises, so a lost race is indistinguishable
# from a sequential duplicate as far as the client is concerned.
UNIQUE_VIOLATIONS: dict[str, tuple[str, str]] = {
    "uq_patients_national_id_live": (
        "national_id_taken",
        "National ID already registered",
    ),
    "patients.national_id": (
        "national_id_taken",
        "National ID already registered",
    ),
    "uq_tags_name_live": ("name_taken", "A tag with this name already exists"),
    "tags.name": ("name_taken", "A tag with this name already exists"),
    "uq_diagnoses_name_live": (
        "name_taken",
        "A diagnosis with this name already exists",
    ),
    "diagnoses.name": ("name_taken", "A diagnosis with this name already exists"),
    "uq_roles_name_live": ("name_taken", "A role with this name already exists"),
    "roles.name": ("name_taken", "A role with this name already exists"),
    "uq_users_username_live": ("username_taken", "This username is taken"),
    "users.username": ("username_taken", "This username is taken"),
    "uq_questionnaire_templates_name_live": (
        "name_taken",
        "A questionnaire template with this name already exists",
    ),
    "questionnaire_templates.name": (
        "name_taken",
        "A questionnaire template with this name already exists",
    ),
    "uq_prescription_items_name_live": (
        "name_taken",
        "A prescription item with this name already exists",
    ),
    "prescription_items.name": (
        "name_taken",
        "A prescription item with this name already exists",
    ),
    "uq_prescription_item_links_pair": (
        "duplicate_item",
        "This item is already on the prescription",
    ),
    "uq_attachments_stored_filename_live": (
        "file_taken",
        "This file is already attached",
    ),
    "attachments.stored_filename": ("file_taken", "This file is already attached"),
}

# PostgreSQL: duplicate key value violates unique constraint "name"
# SQLite:     UNIQUE constraint failed: patients.national_id
_PG_CONSTRAINT_RE = re.compile(r'unique constraint "([^"]+)"')
_SQLITE_CONSTRAINT_RE = re.compile(r"UNIQUE constraint failed: ([\w.]+)")


def unique_violation(exc: IntegrityError) -> tuple[str, str] | None:
    """Map a database uniqueness violation to (code, message) — or None when
    the IntegrityError is something else (NOT NULL, FK, check), which is a
    server bug and must keep surfacing as a 500."""
    orig = exc.orig
    text = str(orig)
    match = _PG_CONSTRAINT_RE.search(text) or _SQLITE_CONSTRAINT_RE.search(text)
    if match is not None:
        return UNIQUE_VIOLATIONS.get(match.group(1))
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if sqlstate == "23505" or "unique" in text.lower():
        name = getattr(orig, "constraint_name", None) or getattr(orig, "constraint", None)
        if isinstance(name, str):
            return UNIQUE_VIOLATIONS.get(name)
    return None


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

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(_: Request, exc: IntegrityError) -> JSONResponse:
        """A unique-index violation the endpoint's pre-check lost a race to.

        The request's session is already closed (and its transaction rolled
        back) by the time the exception reaches here — the dependency's
        ``async with SessionLocal()`` unwinds first — so there is nothing to
        clean up. A NOT NULL / FK / check violation is NOT a conflict: it
        re-raises and stays a 500, because it means a server bug.
        """
        violation = unique_violation(exc)
        if violation is None:
            raise exc
        code, message = violation
        return error_response(
            status.HTTP_409_CONFLICT, code=code, message=message
        )
