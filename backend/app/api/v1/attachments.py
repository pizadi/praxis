from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    require_at_least,
    resolve_stored_path,
    save_upload,
)
from app.core.enums import UserRole
from app.core.tokens import utc_now
from app.db.session import get_db
from app.models import Appointment, Attachment, Patient, User
from app.schemas import AttachmentCreateIn, AttachmentOut, AttachmentUpdateIn
from app.services import audit

router = APIRouter(prefix="/appointments", tags=["attachments"])


async def _get_appt_or_404(db: AsyncSession, appointment_id: int) -> Appointment:
    stmt = (
        select(Appointment)
        .join(Patient, Appointment.patient_id == Patient.id)
        .where(
            Appointment.id == appointment_id,
            Appointment.deleted_at.is_(None),
            Patient.deleted_at.is_(None),
        )
    )
    appt = await db.scalar(stmt)
    if appt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    return appt


async def _get_attachment_or_404(db: AsyncSession, attachment_id: int) -> Attachment:
    # visible only if the attachment AND its parent chain are alive
    stmt = (
        select(Attachment)
        .join(Appointment, Attachment.appointment_id == Appointment.id)
        .join(Patient, Appointment.patient_id == Patient.id)
        .where(
            Attachment.id == attachment_id,
            Attachment.deleted_at.is_(None),
            Appointment.deleted_at.is_(None),
            Patient.deleted_at.is_(None),
        )
    )
    att = await db.scalar(stmt)
    if att is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    return att


@router.get("/{appointment_id}/files", response_model=list[AttachmentOut])
async def list_files(
    appointment_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_at_least(UserRole.RECEPTIONIST)),
):
    await _get_appt_or_404(db, appointment_id)
    rows = (
        await db.scalars(
            select(Attachment)
            .where(
                Attachment.appointment_id == appointment_id,
                Attachment.deleted_at.is_(None),
            )
            .order_by(Attachment.created_at.desc())
        )
    ).all()
    return list(rows)


@router.post(
    "/{appointment_id}/files",
    response_model=AttachmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_file(
    appointment_id: int,
    file: UploadFile,
    request: Request,
    description: str = Form(""),
    notes: str = Form(""),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_at_least(UserRole.DOCTOR)),
):
    await _get_appt_or_404(db, appointment_id)
    data = await file.read()
    meta = save_upload(data, file.filename or "upload.bin")
    att = Attachment(
        appointment_id=appointment_id,
        description=description[:128],
        notes=notes[:10000],
        stored_filename=meta["stored_filename"],
        original_filename=meta["original_filename"],
        mime_type=meta["mime_type"],
        size_bytes=meta["size_bytes"],
    )
    db.add(att)
    await db.commit()
    await db.refresh(att)
    await audit.log_action(
        db,
        user=user,
        request=request,
        action=audit.CREATE,
        entity_type="file",
        entity_id=att.id,
        summary=f"{meta['original_filename']} ({meta['stored_filename']})",
        details={"appointment_id": appointment_id, "size": meta["size_bytes"]},
    )
    return att


@router.post(
    "/{appointment_id}/files/note",
    response_model=AttachmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_note_file(
    appointment_id: int,
    body: AttachmentCreateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_at_least(UserRole.DOCTOR)),
):
    """Create a note-only attachment (description + notes, no physical file)."""
    await _get_appt_or_404(db, appointment_id)
    att = Attachment(
        appointment_id=appointment_id,
        description=body.description[:128],
        notes=body.notes[:10000],
        stored_filename=None,
        original_filename=None,
        mime_type=None,
        size_bytes=None,
        missing_file=False,
    )
    db.add(att)
    await db.commit()
    await db.refresh(att)
    await audit.log_action(
        db,
        user=user,
        request=request,
        action=audit.CREATE,
        entity_type="file",
        entity_id=att.id,
        summary=f"note-only: {att.description or '(بدون شرح)'}",
        details={"appointment_id": appointment_id, "note_only": True},
    )
    return att


@router.patch("/files/{attachment_id}", response_model=AttachmentOut)
async def update_file(
    attachment_id: int,
    body: AttachmentUpdateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_at_least(UserRole.DOCTOR)),
):
    """Update description/notes. (Legacy bug: old system silently dropped these edits.)"""
    att = await _get_attachment_or_404(db, attachment_id)
    data = body.model_dump(exclude_unset=True)
    before: dict[str, Any] = {
        f: getattr(att, f) for f in ("description", "notes") if f in data
    }
    if "description" in data:
        att.description = data["description"][:128]
    if "notes" in data:
        att.notes = data["notes"][:10000]
    await db.commit()
    await db.refresh(att)
    changed = audit.diff_details(before, {f: getattr(att, f) for f in before}, list(before))
    await audit.log_action(
        db,
        user=user,
        request=request,
        action=audit.UPDATE,
        entity_type="file",
        entity_id=att.id,
        summary=att.original_filename or f"attachment {att.id}",
        details=changed or None,
    )
    return att


@router.delete("/files/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    attachment_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_at_least(UserRole.DOCTOR)),
):
    """Soft delete; physical file stays until a trash purge removes it."""
    att = await _get_attachment_or_404(db, attachment_id)
    att.deleted_at = utc_now()
    await db.commit()
    await audit.log_action(
        db,
        user=user,
        request=request,
        action=audit.DELETE,
        entity_type="file",
        entity_id=att.id,
        summary=att.original_filename or f"attachment {att.id}",
    )
    return None


@router.get("/files/{attachment_id}/download")
async def download_file(
    attachment_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_at_least(UserRole.RECEPTIONIST)),
):
    """Streamed download; path resolution is containment-checked (no traversal)."""
    att = await _get_attachment_or_404(db, attachment_id)
    if not att.stored_filename or att.missing_file:
        # Row is note-only, or the file was already absent at migration time.
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=(
                "Attachment record has no file (note-only or missing since migration)"
            ),
        )
    path = resolve_stored_path(att.stored_filename)
    if not path.is_file():
        # DB says a file exists but it is not in UPLOAD_DIR — almost always
        # an upload-volume/path mismatch after a migration, not a bad request.
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=(
                f"File metadata exists but the physical file is absent from"
                f" UPLOAD_DIR (expected: {att.stored_filename}). If this happens"
                " for all downloads, the files were migrated to a different"
                " directory than the one mounted in the api container."
            ),
        )
    return FileResponse(
        path,
        media_type=att.mime_type or "application/octet-stream",
        filename=att.original_filename or att.stored_filename,
    )
