import csv
import datetime as dt
import io

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_perm
from app.core.errors import BusinessRuleError
from app.db.session import APP_TZ, get_db
from app.models import Appointment, Patient, Transaction, User
from app.schemas import DescriptionStat, StatsSummary

router = APIRouter(prefix="/stats", tags=["stats"])


def _day_bounds(date_from: dt.date, date_to: dt.date) -> tuple[dt.datetime, dt.datetime]:
    if date_from > date_to:
        raise BusinessRuleError(
            "date_from must be <= date_to", code="invalid_date_range"
        )
    lo = dt.datetime.combine(date_from, dt.time.min, APP_TZ)
    hi = dt.datetime.combine(date_to, dt.time.max, APP_TZ)
    return lo, hi


async def _summary_data(
    db: AsyncSession, date_from: dt.date, date_to: dt.date
) -> StatsSummary:
    lo, hi = _day_bounds(date_from, date_to)

    alive = (
        Appointment.deleted_at.is_(None),
        Patient.deleted_at.is_(None),
        Transaction.deleted_at.is_(None),
    )
    num_appointments = await db.scalar(
        select(func.count())
        .select_from(Appointment)
        .join(Patient, Appointment.patient_id == Patient.id)
        .where(
            Appointment.scheduled_at >= lo,
            Appointment.scheduled_at <= hi,
            Appointment.deleted_at.is_(None),
            Patient.deleted_at.is_(None),
        )
    )

    txn_amount = func.coalesce(func.sum(Transaction.amount), 0)
    in_range = (
        Appointment.scheduled_at >= lo,
        Appointment.scheduled_at <= hi,
        *alive,
    )

    total_amount = await db.scalar(
        select(txn_amount)
        .select_from(Transaction)
        .join(Appointment, Transaction.appointment_id == Appointment.id)
        .join(Patient, Appointment.patient_id == Patient.id)
        .where(*in_range)
    )
    pos_amount = await db.scalar(
        select(txn_amount)
        .select_from(Transaction)
        .join(Appointment, Transaction.appointment_id == Appointment.id)
        .join(Patient, Appointment.patient_id == Patient.id)
        .where(*in_range, Transaction.pos.is_(True))
    )
    cash_amount = await db.scalar(
        select(txn_amount)
        .select_from(Transaction)
        .join(Appointment, Transaction.appointment_id == Appointment.id)
        .join(Patient, Appointment.patient_id == Patient.id)
        .where(*in_range, Transaction.pos.is_(False))
    )
    num_transactions = await db.scalar(
        select(func.count())
        .select_from(Transaction)
        .join(Appointment, Transaction.appointment_id == Appointment.id)
        .join(Patient, Appointment.patient_id == Patient.id)
        .where(*in_range)
    )
    by_desc_rows = (
        (
            await db.execute(
                select(
                    Transaction.description,
                    func.count(func.distinct(Transaction.id)),
                    txn_amount,
                )
                .select_from(Transaction)
                .join(Appointment, Transaction.appointment_id == Appointment.id)
                .join(Patient, Appointment.patient_id == Patient.id)
                .where(*in_range)
                .group_by(Transaction.description)
            )
        )
        .all()
    )
    return StatsSummary(
        start=date_from,
        end=date_to,
        num_appointments=int(num_appointments or 0),
        total_amount=int(total_amount or 0),
        pos_amount=int(pos_amount or 0),
        cash_amount=int(cash_amount or 0),
        num_transactions=int(num_transactions or 0),
        by_description=[
            DescriptionStat(description=d, count=int(c), total_amount=int(s))
            for d, c, s in by_desc_rows
        ],
    )


@router.get("/summary", response_model=StatsSummary)
async def stats_summary(
    date_from: dt.date,
    date_to: dt.date,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_perm("stats.view")),
):
    """Aggregates over appointments and transactions by appointment date, in APP_TIMEZONE."""
    return await _summary_data(db, date_from, date_to)


@router.get("/summary.csv")
async def stats_summary_csv(
    date_from: dt.date,
    date_to: dt.date,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_perm("stats.view")),
) -> StreamingResponse:
    summary = await _summary_data(db, date_from, date_to)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["description", "count", "total_amount"])
    for row in summary.by_description:
        writer.writerow([row.description, row.count, row.total_amount])
    fname = f"stats-{date_from.isoformat()}-{date_to.isoformat()}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
