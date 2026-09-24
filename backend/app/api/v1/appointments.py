import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_perm
from app.api.pagination import Page, clamp_limit_offset, paginate, paginate_rows
from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.tokens import utc_now
from app.db.session import day_bounds, get_db
from app.models import Appointment, Patient, Transaction, User
from app.models.domain import STAGE_LABELS_FA, AppointmentStage
from app.schemas import (
    AppointmentBrief,
    AppointmentCreateIn,
    AppointmentOut,
    AppointmentStageChangeIn,
    AppointmentUpdateIn,
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
        raise NotFoundError("Appointment not found", code="appointment_not_found")
    return appt


def _out(appt: Appointment, user: User) -> AppointmentOut:
    data = {
        "id": appt.id,
        "patient_id": appt.patient_id,
        "scheduled_at": appt.scheduled_at,
        "stage": int(appt.stage),
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


def _brief(appt: Appointment) -> AppointmentBrief:
    return AppointmentBrief.model_validate(
        {
            "id": appt.id,
            "patient_id": appt.patient_id,
            "scheduled_at": appt.scheduled_at,
            "stage": int(appt.stage),
            "patient_first_name": appt.patient.first_name,
            "patient_last_name": appt.patient.last_name,
            "patient_national_id": appt.patient.national_id,
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
        lo = (
            day_bounds(date_from)[0]
            if date_from
            else dt.datetime(1, 1, 1, tzinfo=dt.UTC)
        )
        hi = (
            day_bounds(date_to)[1]
            if date_to
            else dt.datetime(9999, 12, 31, tzinfo=dt.UTC)
        )
        if date_from and date_to and lo > hi:
            raise BusinessRuleError(
                "date_from must be <= date_to", code="invalid_date_range"
            )
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

    return Page(
        items=[_brief(a) for a in appts],
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
        raise NotFoundError("Patient not found", code="patient_not_found")
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


@router.patch("/appointments/{appointment_id}/stage", response_model=AppointmentOut)
async def change_appointment_stage(
    appointment_id: int,
    body: AppointmentStageChangeIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_perm("appointments.stage")),
):
    """Advance/regress the visit pipeline by ONE step.

    Boundaries (below reserved / beyond finished) are a 409 conflict, not
    validation errors — the direction is valid, the current stage just
    can't move that way.
    """
    appt = await _get_or_404(db, appointment_id)
    current = AppointmentStage(int(appt.stage))
    step = 1 if body.direction == "advance" else -1
    target_value = current.value + step
    if not 0 <= target_value <= max(s.value for s in AppointmentStage):
        raise ConflictError(
            "مرحله نوبت در مرز مجاز است", code="stage_limit"
        )
    target = AppointmentStage(target_value)
    appt.stage = target
    await db.commit()
    appt = await _get_or_404(db, appointment_id)
    await audit.log_action(
        db,
        user=user,
        request=request,
        action=audit.UPDATE,
        entity_type="appointment",
        entity_id=appt.id,
        summary=(
            f"{appt.patient.first_name} {appt.patient.last_name} — مرحله:"
            f" از {STAGE_LABELS_FA[current]} به {STAGE_LABELS_FA[target]}"
        ),
        details={"stage": {"old": current.name, "new": target.name}},
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
