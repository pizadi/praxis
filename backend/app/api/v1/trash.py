"""Admin/doctor trash panel: list, restore, and purge soft-deleted items.

Access: list/restore → doctor or admin; purge (permanent delete, the only
action that unlinks physical files) → admin only.

Subtree semantics: deleting a patient (or appointment) hides its children
without stamping them. The trash therefore lists only *directly* deleted
rows; children reappear when their parent is restored. Restoring a child
whose parent is still deleted is refused with 409 (restore the parent first).
"""

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import delete_stored_file, require_admin, require_at_least
from app.api.pagination import Page, clamp_limit_offset, paginate
from app.core.enums import UserRole
from app.core.errors import ConflictError
from app.db.session import get_db
from app.models import (
    Appointment,
    Attachment,
    Diagnosis,
    Patient,
    Tag,
    Transaction,
    User,
)
from app.schemas import TrashItemOut
from app.services import audit

router = APIRouter(prefix="/admin/trash", tags=["trash"])

TYPES = ("patients", "appointments", "transactions", "attachments", "tags", "diagnoses", "users")


def _get_model(type_name: str):
    mapping = {
        "patients": Patient,
        "appointments": Appointment,
        "transactions": Transaction,
        "attachments": Attachment,
        "tags": Tag,
        "diagnoses": Diagnosis,
        "users": User,
    }
    if type_name not in mapping:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"type must be one of {TYPES}",
        )
    return mapping[type_name]


def _as_utc(value: dt.datetime | None) -> dt.datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.UTC)
    return value


@router.get("/{type}", response_model=Page[TrashItemOut])
async def list_trash(
    type: str,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_at_least(UserRole.DOCTOR)),
):
    model = _get_model(type)

    stmt = (
        select(model)
        .where(model.deleted_at.is_not(None))
        .order_by(model.deleted_at.desc())
    )
    limit, offset = clamp_limit_offset(limit, offset)
    rows, total = await paginate(db, stmt, limit=limit, offset=offset)

    items: list[TrashItemOut] = []
    for row in rows:
        deleted_at = _as_utc(row.deleted_at)
        title = ""
        subtitle = ""
        parent_deleted = False

        if isinstance(row, Patient):
            title = f"{row.first_name} {row.last_name}"
            subtitle = row.national_id
        elif isinstance(row, Appointment):
            pat = await db.get(Patient, row.patient_id)
            if pat is not None:
                title = f"{pat.first_name} {pat.last_name}"
                subtitle = f"appointment at {row.scheduled_at.isoformat()}"
                parent_deleted = pat.deleted_at is not None
            else:
                title = f"appointment {row.id}"
        elif isinstance(row, Transaction):
            appt = await db.get(Appointment, row.appointment_id)
            title = f"{row.description} — {row.amount}"
            subtitle = f"appointment {row.appointment_id}"
            if appt is not None:
                parent_deleted = appt.deleted_at is not None
        elif isinstance(row, Attachment):
            appt = await db.get(Appointment, row.appointment_id)
            title = row.description or (row.original_filename or f"attachment {row.id}")
            subtitle = row.original_filename or ""
            if appt is not None:
                parent_deleted = appt.deleted_at is not None
        elif isinstance(row, (Tag, Diagnosis)):
            title = row.name
        elif isinstance(row, User):
            title = row.username
            subtitle = row.full_name

        items.append(
            TrashItemOut(
                id=row.id,
                type=type,
                deleted_at=deleted_at
                or _as_utc(getattr(row, "created_at", None))
                or dt.datetime.now(dt.UTC),
                title=title,
                subtitle=subtitle,
                parent_deleted=parent_deleted,
            )
        )

    return Page(items=items, total=total, limit=limit, offset=offset)


async def _unique_conflict_exists(db: AsyncSession, model, row) -> bool:
    """Check whether restoring this row would violate live uniqueness."""
    if isinstance(row, Patient):
        dup = await db.scalar(
            select(func.count())
            .select_from(Patient)
            .where(
                Patient.national_id == row.national_id,
                Patient.deleted_at.is_(None),
                Patient.id != row.id,
            )
        )
        return bool(dup)
    if isinstance(row, (Tag, Diagnosis)):
        dup = await db.scalar(
            select(func.count())
            .select_from(type(row))
            .where(
                type(row).name == row.name,
                type(row).deleted_at.is_(None),
                type(row).id != row.id,
            )
        )
        return bool(dup)
    if isinstance(row, User):
        dup = await db.scalar(
            select(func.count())
            .select_from(User)
            .where(
                User.username == row.username,
                User.deleted_at.is_(None),
                User.id != row.id,
            )
        )
        return bool(dup)
    return False


@router.post("/{type}/{obj_id}/restore", response_model=TrashItemOut)
async def restore_item(
    type: str,
    obj_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_at_least(UserRole.DOCTOR)),
):
    model = _get_model(type)
    row = await db.get(model, obj_id)
    if row is None or row.deleted_at is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not found in trash")

    # subtree rule: a child can only be restored if its parent is alive
    if isinstance(row, Appointment):
        pat = await db.get(Patient, row.patient_id)
        if pat is not None and pat.deleted_at is not None:
            raise ConflictError(
                "Restore the parent patient first", code="parent_still_deleted"
            )
    elif isinstance(row, (Transaction, Attachment)):
        appt = await db.get(Appointment, row.appointment_id)
        if appt is not None and appt.deleted_at is not None:
            raise ConflictError(
                "Restore the parent appointment first", code="parent_still_deleted"
            )

    if await _unique_conflict_exists(db, model, row):
        kind = type.strip("s").capitalize() if hasattr(type, "strip") else type
        raise ConflictError(
            f"A live record already uses this {kind}'s unique value",
            code="unique_conflict",
        )

    row.deleted_at = None
    if isinstance(row, User):
        row.is_active = True
    await db.commit()
    await audit.log_action(
        db,
        user=user,
        request=request,
        action=audit.RESTORE,
        entity_type=type.rstrip("s"),
        entity_id=row.id,
        summary=f"restored {type.rstrip('s')} {row.id}",
    )

    row = await db.get(model, obj_id)
    if row is None:  # pragma: no cover — just restored, cannot vanish
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not found in trash")
    title = ""
    subtitle = ""
    if isinstance(row, Patient):
        title = f"{row.first_name} {row.last_name}"
        subtitle = row.national_id
    elif isinstance(row, (Tag, Diagnosis)):
        title = row.name
    elif isinstance(row, User):
        title = row.username
        subtitle = row.full_name
    elif isinstance(row, Appointment):
        title = f"appointment {row.id}"
        subtitle = str(row.scheduled_at)
    elif isinstance(row, Transaction):
        title = f"{row.description} — {row.amount}"
        subtitle = f"appointment {row.appointment_id}"
    elif isinstance(row, Attachment):
        title = row.description or (row.original_filename or f"attachment {row.id}")
        subtitle = row.original_filename or ""

    return TrashItemOut(
        id=row.id,
        type=type,
        deleted_at=_as_utc(getattr(row, "created_at", None))
        or dt.datetime.now(dt.UTC),
        title=title,
        subtitle=subtitle,
    )


@router.delete("/{type}/{obj_id}", status_code=status.HTTP_204_NO_CONTENT)
async def purge_item(
    type: str,
    obj_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    """PERMANENTLY delete one trash item (admin only).

    For patients this cascades to appointments → files/txns (hard delete);
    physical files are unlinked from disk. There is no undo.
    """
    model = _get_model(type)
    row = await db.get(model, obj_id)
    if row is None or row.deleted_at is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not found in trash")

    # collect physical file names before hard-deleting the subtree
    stored_names: list[str | None] = []
    if isinstance(row, Patient):
        names = (
            (
                await db.execute(
                    select(Attachment.stored_filename)
                    .join(Appointment, Attachment.appointment_id == Appointment.id)
                    .where(Appointment.patient_id == row.id)
                )
            )
            .scalars()
            .all()
        )
        stored_names = list(names)
    elif isinstance(row, Appointment):
        names = (
            (
                await db.execute(
                    select(Attachment.stored_filename).where(
                        Attachment.appointment_id == row.id
                    )
                )
            )
            .scalars()
            .all()
        )
        stored_names = list(names)
    elif isinstance(row, Attachment):
        stored_names = [row.stored_filename]

    purge_summary = (
        getattr(row, "name", None)
        or getattr(row, "username", None)
        or f"{type} {obj_id}"
    )
    await db.delete(row)
    await db.commit()
    for name in stored_names:
        delete_stored_file(name)
    await audit.log_action(
        db,
        user=user,
        request=request,
        action=audit.PURGE,
        entity_type=type.rstrip("s"),
        entity_id=obj_id,
        summary=f"permanently deleted {type.rstrip('s')} {obj_id} ({purge_summary})",
        details={"files_removed": len(stored_names)},
    )
    return None
