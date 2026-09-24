import asyncio
import json
import logging
import os
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app import __version__
from app.api.v1 import api_router
from app.api.v1.backup import rediscover_backup_artifact
from app.api.v1.meta import health as _health_endpoint
from app.core.config import settings
from app.core.errors import register_error_handlers
from app.core.permissions import ALL_PERMISSIONS, SYSTEM_ROLES
from app.core.security import hash_password
from app.db.migrations import run_migrations
from app.db.session import SessionLocal
from app.models import Role, User
from app.services.uploads_purge import purge_loop


async def ensure_system_roles(session) -> None:
    """Seed the three system roles if missing (idempotent; also used by tests).

    The admin role is UI-locked (no edit/delete — lockout protection), so it
    can never hold user-intended removals: keep it additively at the full
    catalog on every call. This heals databases whose roles were seeded
    before a permission existed (e.g. create_all-built DBs stamped at head —
    data migrations never ran there).
    """
    for name, perms in SYSTEM_ROLES.items():
        role = await session.scalar(
            select(Role).where(Role.name == name, Role.deleted_at.is_(None))
        )
        if role is None:
            session.add(
                Role(
                    name=name,
                    is_system=True,
                    permissions_json=json.dumps(perms, ensure_ascii=False),
                )
            )
        elif name == "admin":
            merged = sorted(set(json.loads(role.permissions_json or "[]")) | ALL_PERMISSIONS)
            if merged != json.loads(role.permissions_json or "[]"):
                role.permissions_json = json.dumps(merged, ensure_ascii=False)
    await session.commit()


async def bootstrap_admin() -> None:
    """Seed system roles and create the initial admin account if none exist.

    Tolerates an unmigrated database (fresh start before `alembic upgrade head`)
    so the API can still boot and /health reports degradation.
    """
    try:
        async with SessionLocal() as session:
            await ensure_system_roles(session)
            count = await session.scalar(select(func.count()).select_from(User))
            if count:
                return
            admin_role = await session.scalar(
                select(Role).where(Role.name == "admin", Role.deleted_at.is_(None))
            )
            if admin_role is None:
                raise SQLAlchemyError("admin role missing")
            session.add(
                User(
                    username=settings.bootstrap_admin_username,
                    full_name="System Administrator",
                    password_hash=hash_password(settings.bootstrap_admin_password),
                    role_id=admin_role.id,
                )
            )
            await session.commit()
    except SQLAlchemyError:
        logging.getLogger("clinic.bootstrap").warning(
            "Database not ready for admin bootstrap; run migrations first.",
        )


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Fail-fast: migrate (or refuse to boot) before anything reads/writes the
    # database. bootstrap_admin tolerates an unmigrated DB only as a fallback.
    await asyncio.to_thread(run_migrations)
    await bootstrap_admin()
    purge_task = asyncio.create_task(purge_loop())  # automatic orphan sweeper
    # backup artifacts persist on the volume — re-find the last one after a
    # restart (background: never blocks boot; status flips to ready when the
    # checksum is computed)
    threading.Thread(
        target=rediscover_backup_artifact, name="clinic-backup-rediscover", daemon=True
    ).start()
    yield
    purge_task.cancel()


def create_app() -> FastAPI:
    production = os.environ.get("CLINIC_ENV") == "production"
    app = FastAPI(
        title="Clinic API",
        version=__version__,
        docs_url=None if production else "/docs",
        redoc_url=None if production else "/redoc",
        openapi_url=None if production else "/openapi.json",
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
    )
    register_error_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    # Root alias for /api/v1/health — the documented liveness URL (uptime
    # monitors / manual curl on the host port hit the bare path; a 404 here
    # looks like the API being down when it is not).
    app.get("/health", status_code=status.HTTP_200_OK, include_in_schema=False)(
        _health_endpoint
    )
    return app


app = create_app()
