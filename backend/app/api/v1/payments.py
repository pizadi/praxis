import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_at_least
from app.api.pagination import Page, clamp_limit_offset, paginate_rows
from app.core.enums import UserRole
from app.db.session import APP_TZ, get_db
from app.models import Appointment, Patient, Transaction, User
from app.schemas import PatientPaymentOut

router = APIRouter(prefix="/payments", tags=["payments"])


@router.get("", response_model=Page[PatientPaymentOut])
async def list_payments(
    date: dt.date | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_at_least(UserRole.RECEPTIONIST)),
):
    """Payments (transactions) whose appointment falls on the given day.

    The day is interpreted in APP_TIMEZONE (Asia/Tehran); omitted = today.
    Only rows with the whole parent chain alive are visible.
    """
    day = date or dt.datetime.now(APP_TZ).date()
    lo = dt.datetime.combine(day, dt.time.min, APP_TZ)
    hi = dt.datetime.combine(day, dt.time.max, APP_TZ)

    stmt = (
        select(
            Transaction,
            Appointment.scheduled_at,
            Patient.id,
            Patient.first_name,
            Patient.last_name,
        )
        .join(Appointment, Transaction.appointment_id == Appointment.id)
        .join(Patient, Appointment.patient_id == Patient.id)
        .where(
            Transaction.deleted_at.is_(None),
            Appointment.deleted_at.is_(None),
            Patient.deleted_at.is_(None),
            Appointment.scheduled_at >= lo,
            Appointment.scheduled_at <= hi,
        )
        .order_by(Appointment.scheduled_at.desc(), Transaction.id.desc())
    )
    limit, offset = clamp_limit_offset(limit, offset)
    rows, total = await paginate_rows(db, stmt, limit=limit, offset=offset)
    items = [
        PatientPaymentOut(
            id=t.id,
            appointment_id=t.appointment_id,
            appointment_scheduled_at=scheduled,
            patient_id=patient_id,
            patient_first_name=first_name,
            patient_last_name=last_name,
            description=t.description,
            amount=t.amount,
            pos=t.pos,
        )
        for t, scheduled, patient_id, first_name, last_name in rows
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)
