import datetime as dt

from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_user
from app.db.session import APP_TZ, db_is_ready
from app.models import User

router = APIRouter(tags=["meta"])


@router.get("/health", status_code=status.HTTP_200_OK)
async def health():
    db_ok = await db_is_ready()
    return {"status": "ok" if db_ok else "degraded", "db": db_ok}


@router.get("/meta/today")
async def today(user: User = Depends(get_current_user)) -> dict:
    """Server 'today' in APP_TIMEZONE — the UI uses this for Jalali defaults."""
    return {"today": dt.datetime.now(APP_TZ).date().isoformat()}
