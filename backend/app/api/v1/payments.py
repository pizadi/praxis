import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_perm
from app.api.pagination import Page, clamp_limit_offset, paginate_rows
from app.db.session import APP_TZ, get_db
from app.models import Appointment, Patient, Transaction, User
from app.schemas import PatientPaymentOut, PaymentTypeStat

router = APIRouter(prefix="/payments", tags=["payments"])


def _day_bounds(date: dt.date | None) -> tuple[dt.date, dt.datetime, dt.datetime]:
    day = date or dt.datetime.now(APP_TZ).date()
    lo = dt.datetime.combine(day, dt.time.min, APP_TZ)
    hi = dt.datetime.combine(day, dt.time.max, APP_TZ)
    return day, lo, hi


@router.get("", response_model=Page[PatientPaymentOut])
async def list_payments(
    date: dt.date | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_perm("payments.view")),
):
    """Payments (transactions) whose appointment falls on the given day.

    The day is interpreted in APP_TIMEZONE (Asia/Tehran); omitted = today.
    Only rows with the whole parent chain alive are visible.
    """
    day, lo, hi = _day_bounds(date)
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


@router.get("/summary", response_model=list[PaymentTypeStat])
async def payments_summary(
    date: dt.date | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_perm("payments.view")),
):
    """Per-description aggregates (count, total, POS/cash split) for one day.

    The day is interpreted in APP_TIMEZONE (Asia/Tehran); omitted = today.
    """
    _day, lo, hi = _day_bounds(date)
    pos_true = func.coalesce(
        func.sum(case((Transaction.pos.is_(True), Transaction.amount), else_=0)), 0
    )
    pos_false = func.coalesce(
        func.sum(case((Transaction.pos.is_(False), Transaction.amount), else_=0)), 0
    )
    total_sum = func.coalesce(func.sum(Transaction.amount), 0)
    stmt = (
        select(
            Transaction.description,
            func.count(Transaction.id),
            total_sum,
            pos_true,
            pos_false,
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
        .group_by(Transaction.description)
        .order_by(total_sum.desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        PaymentTypeStat(
            description=description,
            count=count,
            total_amount=int(total),
            pos_amount=int(pos),
            cash_amount=int(cash),
        )
        for description, count, total, pos, cash in rows
    ]
