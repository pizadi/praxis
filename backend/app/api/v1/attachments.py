from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    require_perm,
    resolve_stored_path,
    save_upload_stream,
)
from app.core.tokens import utc_now
from app.db.session import get_db
from app.models import Attachment, Patient, User
from app.schemas import AttachmentCreateIn, AttachmentOut, AttachmentUpdateIn
from app.services import audit

router = APIRouter(tags=["attachments"])

# Since 1.3 files belong to the PATIENT (they survive appointment deletion
# and are managed from the patient page). Row-level routes (/files/…) stay
# id-based and unchanged.


async def _get_attachment_or_404(db: AsyncSession, attachment_id: int) -> Attachment:
    # visible only if the attachment AND its parent patient are alive
    stmt = (
        select(Attachment)
        .join(Patient, Attachment.patient_id == Patient.id)
        .where(
            Attachment.id == attachment_id,
            Attachment.deleted_at.is_(None),
            Patient.deleted_at.is_(None),
        )
    )
    att = await db.scalar(stmt)
    if att is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    return att


@router.get("/patients/{patient_id}/files", response_model=list[AttachmentOut])
async def list_files(
    patient_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_perm("files.read")),
):
    from app.api.v1.patients import _get_or_404 as _patient_or_404

    await _patient_or_404(db, patient_id)
    rows = (
        await db.scalars(
            select(Attachment)
            .where(
                Attachment.patient_id == patient_id,
                Attachment.deleted_at.is_(None),
            )
            .order_by(Attachment.created_at.desc())
        )
    ).all()
    return list(rows)


@router.post(
    "/patients/{patient_id}/files",
    response_model=AttachmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_file(
    patient_id: int,
    file: UploadFile,
    request: Request,
    description: str = Form(""),
    notes: str = Form(""),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_perm("files.write")),
):
    from app.api.v1.patients import _get_or_404 as _patient_or_404

    await _patient_or_404(db, patient_id)
    meta = await save_upload_stream(file, file.filename or "upload.bin")
    att = Attachment(
        patient_id=patient_id,
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
        details={"patient_id": patient_id, "size": meta["size_bytes"]},
    )
    return att


@router.post(
    "/patients/{patient_id}/files/note",
    response_model=AttachmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_note_file(
    patient_id: int,
    body: AttachmentCreateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_perm("files.write")),
):
    """Create a note-only attachment (description + notes, no physical file)."""
    from app.api.v1.patients import _get_or_404 as _patient_or_404

    await _patient_or_404(db, patient_id)
    att = Attachment(
        patient_id=patient_id,
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
        details={"patient_id": patient_id, "note_only": True},
    )
    return att


@router.patch("/files/{attachment_id}", response_model=AttachmentOut)
async def update_file(
    attachment_id: int,
    body: AttachmentUpdateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_perm("files.write")),
):
    """Update description/notes. (Legacy bug: old system silently dropped these edits.)"""
    att = await _get_attachment_or_404(db, attachment_id)
    data = body.model_dump(exclude_unset=True)
    before: dict[str, object] = {
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


@router.post("/files/{attachment_id}/content", response_model=AttachmentOut)
async def set_attachment_content(
    attachment_id: int,
    file: UploadFile,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_perm("files.write")),
):
    """Attach a physical file to an existing attachment row, or replace the
    one it holds (note-only rows get a file; missing_file rows are repaired).
    description/notes are preserved. The superseded physical file stays on
    disk — trash purge remains the only path that unlinks stored files."""
    att = await _get_attachment_or_404(db, attachment_id)
    meta = await save_upload_stream(file, file.filename or "upload.bin")
    had_file = bool(att.stored_filename) and not att.missing_file
    old_stored = att.stored_filename
    att.stored_filename = meta["stored_filename"]
    att.original_filename = meta["original_filename"]
    att.mime_type = meta["mime_type"]
    att.size_bytes = meta["size_bytes"]
    att.missing_file = False
    await db.commit()
    await db.refresh(att)
    await audit.log_action(
        db,
        user=user,
        request=request,
        action=audit.UPDATE,
        entity_type="file",
        entity_id=att.id,
        summary=meta["original_filename"],
        details={
            "patient_id": att.patient_id,
            "replaced": had_file,
            "old_stored_filename": old_stored,
            "new_stored_filename": meta["stored_filename"],
            "size": meta["size_bytes"],
        },
    )
    return att


@router.delete("/files/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    attachment_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_perm("files.delete")),
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
    _: User = Depends(require_perm("files.read")),
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
