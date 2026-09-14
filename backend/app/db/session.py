import datetime as dt
import zoneinfo
from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

APP_TZ: dt.timezone | zoneinfo.ZoneInfo
try:
    APP_TZ = zoneinfo.ZoneInfo(settings.app_timezone)
except zoneinfo.ZoneInfoNotFoundError:
    APP_TZ = dt.UTC


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def db_is_ready() -> bool:
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
