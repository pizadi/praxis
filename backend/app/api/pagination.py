"""Shared pagination primitives (limit/offset with total count)."""

from pydantic import BaseModel, Field
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20


class Page[T](BaseModel):
    items: list[T]
    total: int = Field(description="Total matching rows (before pagination)")
    limit: int
    offset: int


def clamp_limit_offset(limit: int, offset: int, max_size: int = MAX_PAGE_SIZE) -> tuple[int, int]:
    limit = max(1, min(limit, max_size))
    offset = max(0, offset)
    return limit, offset


async def paginate(
    db: AsyncSession, stmt: Select, *, limit: int, offset: int, max_size: int = MAX_PAGE_SIZE
) -> tuple[list, int]:
    limit, offset = clamp_limit_offset(limit, offset, max_size)
    total = await db.scalar(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    )
    rows = (await db.scalars(stmt.limit(limit).offset(offset))).all()
    return list(rows), int(total or 0)


async def paginate_rows(
    db: AsyncSession, stmt: Select, *, limit: int, offset: int, max_size: int = MAX_PAGE_SIZE
) -> tuple[list, int]:
    """Like paginate(), but for multi-column selects: returns full Row tuples."""
    limit, offset = clamp_limit_offset(limit, offset, max_size)
    total = await db.scalar(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    )
    rows = (await db.execute(stmt.limit(limit).offset(offset))).all()
    return list(rows), int(total or 0)
