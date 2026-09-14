from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from app.api.v1 import api_router
from app.core.config import settings
from app.core.enums import UserRole
from app.core.errors import register_error_handlers
from app.db.session import SessionLocal
from app.models import User


async def bootstrap_admin() -> None:
    """Create the initial admin account if the users table is empty.

    Tolerates an unmigrated database (fresh start before `alembic upgrade head`)
    so the API can still boot and /health reports degradation.
    """
    from sqlalchemy import func, select
    from sqlalchemy.exc import SQLAlchemyError

    from app.core.security import hash_password

    try:
        async with SessionLocal() as session:
            count = await session.scalar(select(func.count()).select_from(User))
            if count:
                return
            session.add(
                User(
                    username=settings.bootstrap_admin_username,
                    full_name="System Administrator",
                    password_hash=hash_password(settings.bootstrap_admin_password),
                    role=UserRole.ADMIN,
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
    await bootstrap_admin()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Clinic API",
        version="1.0.0",
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
