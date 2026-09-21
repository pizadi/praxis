import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from app import __version__
from app.api.v1 import api_router
from app.core.config import settings
from app.core.errors import register_error_handlers
from app.db.migrations import run_migrations
from app.db.session import SessionLocal
from app.models import Role, User
from app.services.uploads_purge import purge_loop


async def ensure_system_roles(session) -> None:
    """Seed the three system roles if missing (idempotent; also used by tests)."""
    import json

    from sqlalchemy import select

    from app.core.permissions import SYSTEM_ROLES

    for name, perms in SYSTEM_ROLES.items():
        exists = await session.scalar(
            select(Role).where(Role.name == name, Role.deleted_at.is_(None))
        )
        if exists is None:
            session.add(
                Role(
                    name=name,
                    is_system=True,
                    permissions_json=json.dumps(perms, ensure_ascii=False),
                )
            )
    await session.commit()


async def bootstrap_admin() -> None:
    """Seed system roles and create the initial admin account if none exist.

    Tolerates an unmigrated database (fresh start before `alembic upgrade head`)
    so the API can still boot and /health reports degradation.
    """
    from sqlalchemy import func, select
    from sqlalchemy.exc import SQLAlchemyError

    from app.core.security import hash_password

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
        import logging

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
    yield
    purge_task.cancel()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Clinic API",
        version=__version__,
        docs_url="/docs",
        openapi_url="/openapi.json",
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    register_error_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
