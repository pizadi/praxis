import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_perm
from app.api.pagination import Page, clamp_limit_offset, paginate, paginate_rows
from app.core.tokens import utc_now
from app.db.session import get_db
from app.models import Appointment, Attachment, Patient, Transaction, User
from app.schemas import (
    AppointmentBrief,
    AppointmentCreateIn,
    AppointmentOut,
    AppointmentUpdateIn,
    AttachmentOut,
    PatientTransactionOut,
)
from app.services import audit

router = APIRouter(tags=["appointments"])


def _live_join() -> list:
    """Both the appointment and its patient must be alive (subtree-hide)."""
    return [
        Appointment.deleted_at.is_(None),
        Patient.deleted_at.is_(None),
    ]


async def _get_or_404(db: AsyncSession, appointment_id: int) -> Appointment:
    stmt = (
        select(Appointment)
        .join(Patient, Appointment.patient_id == Patient.id)
        .where(Appointment.id == appointment_id, *_live_join())
        .options(selectinload(Appointment.patient))
    )
    appt = await db.scalar(stmt)
    if appt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    return appt


def _out(appt: Appointment, user: User) -> AppointmentOut:
    data = {
        "id": appt.id,
        "patient_id": appt.patient_id,
        "scheduled_at": appt.scheduled_at,
        "notes": appt.notes,
        "cm": appt.cm,
        "hx": appt.hx,
        "px": appt.px,
        "rx": appt.rx,
        "patient_first_name": appt.patient.first_name,
        "patient_last_name": appt.patient.last_name,
        "patient_national_id": appt.patient.national_id,
        "created_at": appt.created_at,
        "updated_at": appt.updated_at,
    }
    if not user.has_perm("medical_notes.view"):
        for k in ("cm", "hx", "px", "rx"):
            data[k] = ""
    return AppointmentOut.model_validate(data)


def _brief(appt: Appointment, attachment_count: int = 0) -> AppointmentBrief:
    return AppointmentBrief.model_validate(
        {
            "id": appt.id,
            "patient_id": appt.patient_id,
            "scheduled_at": appt.scheduled_at,
            "patient_first_name": appt.patient.first_name,
            "patient_last_name": appt.patient.last_name,
            "patient_national_id": appt.patient.national_id,
            "attachment_count": attachment_count,
        }
    )


@router.get("/appointments", response_model=Page[AppointmentBrief])
async def list_appointments(
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    patient_id: int | None = None,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_perm("appointments.read")),
):
    """Date filters are interpreted in APP_TIMEZONE (day boundaries)."""
    filters: list = [Appointment.patient_id == patient_id] if patient_id else []
    if date_from or date_to:
        from app.db.session import APP_TZ

        lo = (
            dt.datetime.combine(date_from, dt.time.min, APP_TZ)
            if date_from
            else dt.datetime(1, 1, 1, tzinfo=APP_TZ)
        )
        hi = (
            dt.datetime.combine(date_to, dt.time.max, APP_TZ)
            if date_to
            else dt.datetime(9999, 12, 31, tzinfo=APP_TZ)
        )
        if date_from and date_to and lo > hi:
            raise HTTPException(422, detail="date_from must be <= date_to")
        filters.append(Appointment.scheduled_at >= lo)
        filters.append(Appointment.scheduled_at <= hi)

    stmt = (
        select(Appointment)
        .join(Patient, Appointment.patient_id == Patient.id)
        .where(*_live_join(), *filters)
        .options(selectinload(Appointment.patient))
        .order_by(Appointment.scheduled_at.desc())
    )
    limit, offset = clamp_limit_offset(limit, offset)
    appts, total = await paginate(db, stmt, limit=limit, offset=offset)

    # attachment counts for the page: one grouped query, no N+1
    counts: dict[int, int] = {}
    if appts:
        count_rows = (
            await db.execute(
                select(Attachment.appointment_id, func.count(Attachment.id))
                .where(
                    Attachment.appointment_id.in_([a.id for a in appts]),
                    Attachment.deleted_at.is_(None),
                )
                .group_by(Attachment.appointment_id)
            )
        ).all()
        counts = {aid: int(n) for aid, n in count_rows}

    return Page(
        items=[_brief(a, counts.get(a.id, 0)) for a in appts],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/patients/{patient_id}/appointments", response_model=AppointmentOut, status_code=201)
async def create_appointment(
    patient_id: int,
    body: AppointmentCreateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_perm("appointments.create")),
):
    patient = await db.scalar(
        select(Patient).where(
            Patient.id == patient_id, Patient.deleted_at.is_(None)
        )
    )
    if patient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Patient not found")
    appt = Appointment(
        patient_id=patient_id,
        scheduled_at=body.scheduled_at,
        notes=body.notes,
        cm=body.cm,
        hx=body.hx,
        px=body.px,
        rx=body.rx,
    )
    db.add(appt)
    await db.commit()
    appt = await _get_or_404(db, appt.id)
    await audit.log_action(
        db,
        user=user,
        request=request,
        action=audit.CREATE,
        entity_type="appointment",
        entity_id=appt.id,
        summary=(
            f"{patient.first_name} {patient.last_name} —"
            f" {appt.scheduled_at.isoformat()}"
        ),
    )
    return _out(appt, user)


@router.get("/appointments/{appointment_id}", response_model=AppointmentOut)
async def get_appointment(
    appointment_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_perm("appointments.read")),
):
    appt = await _get_or_404(db, appointment_id)
    return _out(appt, user)


@router.patch("/appointments/{appointment_id}", response_model=AppointmentOut)
async def update_appointment(
    appointment_id: int,
    body: AppointmentUpdateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_perm("appointments.update")),
):
    appt = await _get_or_404(db, appointment_id)
    data = body.model_dump(exclude_unset=True)
    before: dict[str, Any] = {
        f: getattr(appt, f)
        for f in ("scheduled_at", "notes", "cm", "hx", "px", "rx")
        if f in data
    }
    for field in ("scheduled_at", "notes", "cm", "hx", "px", "rx"):
        if field in data:
            setattr(appt, field, data[field])
    await db.commit()
    appt = await _get_or_404(db, appointment_id)
    changed = audit.diff_details(before, {f: getattr(appt, f) for f in before}, list(before))
    await audit.log_action(
        db,
        user=user,
        request=request,
        action=audit.UPDATE,
        entity_type="appointment",
        entity_id=appt.id,
        summary=f"{appt.patient.first_name} {appt.patient.last_name} —"
        f" {appt.scheduled_at.isoformat()}",
        details=changed or None,
    )
    return _out(appt, user)


@router.delete("/appointments/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_appointment(
    appointment_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_perm("appointments.delete")),
):
    """Soft delete; the appointment's files/transactions become invisible via
    join filtering and return on restore. Physical files untouched."""
    appt = await _get_or_404(db, appointment_id)
    appt.deleted_at = utc_now()
    await db.commit()
    await audit.log_action(
        db,
        user=user,
        request=request,
        action=audit.DELETE,
        entity_type="appointment",
        entity_id=appt.id,
        summary=f"{appt.patient.first_name} {appt.patient.last_name} —"
        f" {appt.scheduled_at.isoformat()}",
    )
    return None


# --- patient-level aggregate views (patient page sidebar tabs) -----------------


@router.get(
    "/patients/{patient_id}/all-files",
    response_model=Page[AttachmentOut],
)
async def list_patient_files(
    patient_id: int,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_perm("files.read")),
):
    """Every live file across all live appointments of one patient, newest first."""
    from app.api.v1.patients import _get_or_404 as _patient_or_404

    await _patient_or_404(db, patient_id)
    stmt = (
        select(Attachment)
        .join(Appointment, Attachment.appointment_id == Appointment.id)
        .where(
            Appointment.patient_id == patient_id,
            Appointment.deleted_at.is_(None),
            Attachment.deleted_at.is_(None),
        )
        .order_by(Attachment.created_at.desc())
    )
    limit, offset = clamp_limit_offset(limit, offset)
    items, total = await paginate(db, stmt, limit=limit, offset=offset)
    return Page(
        items=[AttachmentOut.model_validate(a) for a in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/patients/{patient_id}/all-transactions",
    response_model=Page[PatientTransactionOut],
)
async def list_patient_transactions(
    patient_id: int,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_perm("transactions.read")),
):
    """Every live payment across all live appointments of one patient."""
    from app.api.v1.patients import _get_or_404 as _patient_or_404

    await _patient_or_404(db, patient_id)
    stmt = (
        select(Transaction, Appointment.scheduled_at)
        .join(Appointment, Transaction.appointment_id == Appointment.id)
        .where(
            Appointment.patient_id == patient_id,
            Appointment.deleted_at.is_(None),
            Transaction.deleted_at.is_(None),
        )
        .order_by(Appointment.scheduled_at.desc())
    )
    limit, offset = clamp_limit_offset(limit, offset)
    rows, total = await paginate_rows(db, stmt, limit=limit, offset=offset)
    items = [
        PatientTransactionOut(
            id=t.id,
            appointment_id=t.appointment_id,
            appointment_scheduled_at=scheduled,
            description=t.description,
            amount=t.amount,
            pos=t.pos,
        )
        for t, scheduled in rows
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)
