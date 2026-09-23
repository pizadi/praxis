"""Structured prescriptions (v1.3) — replacement for the legacy free-text rx.

A prescription belongs to a PATIENT (like questionnaire responses).
`prescription_items` is a tag-like dictionary powering the autocomplete;
unknown names typed by the physician are auto-registered by the create/
update endpoints (no separate taxonomy perm — prescribing doctors grow the
dictionary). Links carry an optional quantity (NULL = unspecified).

Legacy data: the Alembic migration (and scripts/migrate_sqlite.py for fresh
installs) converts the old `appointments.rx` free text into prescriptions;
below-threshold item text lands in the prescription `notes`, and the raw
text also stays in the deprecated rx column.
"""

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_perm
from app.api.pagination import Page, clamp_limit_offset, paginate
from app.core.errors import ConflictError
from app.core.tokens import utc_now
from app.db.session import get_db
from app.models import (
    Patient,
    Prescription,
    PrescriptionItem,
    PrescriptionItemLink,
    User,
)
from app.schemas import (
    NamedCreateIn,
    NamedRef,
    NamedRenameIn,
    PrescriptionCreateIn,
    PrescriptionItemLinkIn,
    PrescriptionItemLinkOut,
    PrescriptionOut,
    PrescriptionUpdateIn,
)
from app.services import audit

router = APIRouter(tags=["prescriptions"])

ITEM_MAX_PAGE_SIZE = 200


# --- helpers --------------------------------------------------------------------


async def _get_prescription_or_404(db: AsyncSession, prescription_id: int) -> Prescription:
    """Live prescription whose parent patient is alive (subtree-hide)."""
    stmt = (
        select(Prescription)
        .join(Patient, Prescription.patient_id == Patient.id)
        .where(
            Prescription.id == prescription_id,
            Prescription.deleted_at.is_(None),
            Patient.deleted_at.is_(None),
        )
        .options(
            selectinload(Prescription.links).selectinload(PrescriptionItemLink.item)
        )
    )
    rx = await db.scalar(stmt)
    if rx is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Prescription not found")
    return rx


def _out(rx: Prescription, created_by: str | None) -> PrescriptionOut:
    data: dict[str, Any] = {
        "id": rx.id,
        "patient_id": rx.patient_id,
        "prescribed_at": rx.prescribed_at,
        "notes": rx.notes,
        "created_by_username": created_by,
        "source_appointment_id": rx.source_appointment_id,
        "items": [
            PrescriptionItemLinkOut(
                id=link.id,
                item_id=link.item_id,
                item_name=link.item.name,
                quantity=link.quantity,
            )
            for link in rx.links
        ],
        "created_at": rx.created_at,
        "updated_at": rx.updated_at,
    }
    return PrescriptionOut.model_validate(data)


async def _created_by_username(db: AsyncSession, rx: Prescription) -> str | None:
    if rx.created_by_id is None:
        return None
    row = await db.execute(
        select(User.username).where(User.id == rx.created_by_id)
    )
    username = row.scalar()
    return username


async def _resolve_items(
    db: AsyncSession,
    specs: list[PrescriptionItemLinkIn],
) -> list[tuple[int, int | None]]:
    """Map the request's item specs to (item_id, quantity) pairs.

    Unknown names are registered as new dictionary items. Duplicates
    (same id, or names colliding case-insensitively within the request)
    are rejected — the DB enforces a unique (prescription, item) pair.
    """
    resolved: list[tuple[int, int | None]] = []
    by_id: dict[int, int] = {}
    by_name: dict[str, int] = {}

    async def item_id_for(spec: PrescriptionItemLinkIn) -> int:
        if spec.item_id is not None:
            existing = await db.get(PrescriptionItem, spec.item_id)
            if existing is None or existing.deleted_at is not None:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Prescription item {spec.item_id} not found",
                )
            by_id[spec.item_id] = existing.id
            by_name.setdefault(existing.name.casefold(), existing.id)
            return existing.id
        name = (spec.name or "").strip()
        found = by_name.get(name.casefold())
        if found is not None:
            return found
        row = await db.execute(
            select(PrescriptionItem).where(
                func.lower(PrescriptionItem.name) == name.casefold(),
                PrescriptionItem.deleted_at.is_(None),
            )
        )
        item = row.scalar()
        if item is None:
            item = PrescriptionItem(name=name[:128])
            db.add(item)
            await db.flush()
        by_name[name.casefold()] = item.id
        return item.id

    for spec in specs:
        if spec.item_id is None and (spec.name is None or not spec.name.strip()):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Each item needs item_id or name",
            )
        item_id = await item_id_for(spec)
        if item_id in {i for i, _ in resolved}:
            raise ConflictError(
                "Duplicate item in one prescription", code="duplicate_item"
            )
        resolved.append((item_id, spec.quantity))

    # names typed twice with different ids → same casefolded dictionary row
    if len({i for i, _ in resolved}) != len(resolved):
        raise ConflictError(
            "Duplicate item in one prescription", code="duplicate_item"
        )
    return resolved


# --- dictionary (autocomplete) ----------------------------------------------------


@router.get("/prescription-items", response_model=Page[NamedRef])
async def list_items(
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_perm("prescriptions.read")),
):
    stmt = select(PrescriptionItem).where(PrescriptionItem.deleted_at.is_(None))
    if q:
        stmt = stmt.where(PrescriptionItem.name.ilike(f"%{q.strip()}%"))
    stmt = stmt.order_by(PrescriptionItem.name)
    limit, offset = clamp_limit_offset(limit, offset, ITEM_MAX_PAGE_SIZE)
    rows, total = await paginate(db, stmt, limit=limit, offset=offset)
    return Page(items=rows, total=total, limit=limit, offset=offset)


@router.post("/prescription-items", response_model=NamedRef, status_code=status.HTTP_201_CREATED)
async def create_item(
    body: NamedCreateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_perm("prescriptions.write")),
):
    """Directly register a dictionary item (normally items self-register
    from prescriptions). Case-insensitive duplicate check first — a live
    item differing only by case is a 409 name_taken, same as rename."""
    name = body.name.strip()
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Name required")
    dup = await db.scalar(
        select(PrescriptionItem).where(
            func.lower(PrescriptionItem.name) == name.casefold(),
            PrescriptionItem.deleted_at.is_(None),
        )
    )
    if dup:
        raise ConflictError("Name already taken", code="name_taken")
    item = PrescriptionItem(name=name[:128])
    db.add(item)
    await db.commit()
    await db.refresh(item)
    await audit.log_action(
        db,
        user=user,
        request=request,
        action=audit.CREATE,
        entity_type="prescription_item",
        entity_id=item.id,
        summary=item.name,
    )
    return item


@router.patch("/prescription-items/{item_id}", response_model=NamedRef)
async def rename_item(
    item_id: int,
    body: NamedRenameIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_perm("prescriptions.write")),
):
    """Rename a dictionary item (fix typos — links follow automatically)."""
    item = await db.scalar(
        select(PrescriptionItem).where(
            PrescriptionItem.id == item_id, PrescriptionItem.deleted_at.is_(None)
        )
    )
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not found")
    name = body.name.strip()
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Name required")
    dup = await db.scalar(
        select(PrescriptionItem).where(
            func.lower(PrescriptionItem.name) == name.casefold(),
            PrescriptionItem.id != item_id,
            PrescriptionItem.deleted_at.is_(None),
        )
    )
    if dup:
        raise ConflictError("Name already taken", code="name_taken")
    old_name = item.name
    item.name = name[:128]
    await db.commit()
    await audit.log_action(
        db,
        user=user,
        request=request,
        action=audit.UPDATE,
        entity_type="prescription_item",
        entity_id=item.id,
        summary=f"{old_name} → {item.name}",
    )
    return item


@router.delete("/prescription-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_perm("prescriptions.write")),
):
    """Soft delete: hidden from autocomplete; existing links are kept so a
    restore is lossless (same semantics as tags/diagnoses)."""
    item = await db.scalar(
        select(PrescriptionItem).where(
            PrescriptionItem.id == item_id, PrescriptionItem.deleted_at.is_(None)
        )
    )
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not found")
    item.deleted_at = utc_now()
    await db.commit()
    await audit.log_action(
        db,
        user=user,
        request=request,
        action=audit.DELETE,
        entity_type="prescription_item",
        entity_id=item.id,
        summary=item.name,
    )
    return None


# --- prescriptions ------------------------------------------------------------------


@router.get(
    "/patients/{patient_id}/prescriptions",
    response_model=Page[PrescriptionOut],
)
async def list_patient_prescriptions(
    patient_id: int,
    date: dt.date | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_perm("prescriptions.read")),
):
    """`date` (YYYY-MM-DD) restricts to one APP_TIMEZONE day (prescribed_at)
    — used by the appointment view's «نسخه‌های این روز» tab."""
    from app.api.v1.patients import _get_or_404 as _patient_or_404

    await _patient_or_404(db, patient_id)
    filters = [Prescription.patient_id == patient_id, Prescription.deleted_at.is_(None)]
    if date:
        from app.db.session import day_bounds

        lo, hi = day_bounds(date)
        filters += [Prescription.prescribed_at >= lo, Prescription.prescribed_at <= hi]
    stmt = (
        select(Prescription)
        .where(*filters)
        .options(selectinload(Prescription.links).selectinload(PrescriptionItemLink.item))
        .order_by(Prescription.prescribed_at.desc(), Prescription.id.desc())
    )
    limit, offset = clamp_limit_offset(limit, offset)
    rows, total = await paginate(db, stmt, limit=limit, offset=offset)
    users_map: dict[int, str] = {}
    if rows:
        uids = {r.created_by_id for r in rows if r.created_by_id is not None}
        if uids:
            urows = (
                await db.execute(select(User.id, User.username).where(User.id.in_(uids)))
            ).all()
            users_map = {uid: username for uid, username in urows}
    return Page(
        items=[
            _out(r, users_map.get(r.created_by_id) if r.created_by_id else None)
            for r in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/patients/{patient_id}/prescriptions",
    response_model=PrescriptionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_prescription(
    patient_id: int,
    body: PrescriptionCreateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_perm("prescriptions.write")),
):
    from app.api.v1.patients import _get_or_404 as _patient_or_404

    await _patient_or_404(db, patient_id)
    items = await _resolve_items(db, body.items)
    rx = Prescription(
        patient_id=patient_id,
        notes=body.notes[:10000],
        prescribed_at=body.prescribed_at if body.prescribed_at is not None else utc_now(),
        created_by_id=user.id,
    )
    for item_id, quantity in items:
        rx.links.append(PrescriptionItemLink(item_id=item_id, quantity=quantity))
    db.add(rx)
    await db.commit()
    await db.refresh(rx)
    rx = await _get_prescription_or_404(db, rx.id)
    await audit.log_action(
        db,
        user=user,
        request=request,
        action=audit.CREATE,
        entity_type="prescription",
        entity_id=rx.id,
        summary=", ".join(link.item.name for link in rx.links) or "(بدون قلم)",
        details={
            "patient_id": patient_id,
            "items": [
                {"item_id": link.item_id, "quantity": link.quantity} for link in rx.links
            ],
        },
    )
    return _out(rx, user.username)


@router.get("/prescriptions/{prescription_id}", response_model=PrescriptionOut)
async def get_prescription(
    prescription_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_perm("prescriptions.read")),
):
    rx = await _get_prescription_or_404(db, prescription_id)
    return _out(rx, await _created_by_username(db, rx))


@router.patch("/prescriptions/{prescription_id}", response_model=PrescriptionOut)
async def update_prescription(
    prescription_id: int,
    body: PrescriptionUpdateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_perm("prescriptions.write")),
):
    rx = await _get_prescription_or_404(db, prescription_id)
    before: dict[str, Any] = {}
    if body.notes is not None:
        before["notes"] = rx.notes
        rx.notes = body.notes[:10000]
    if body.prescribed_at is not None:
        before["prescribed_at"] = rx.prescribed_at.isoformat()
        rx.prescribed_at = body.prescribed_at
    if body.items is not None:
        before["items"] = [
            {"item_id": link.item_id, "quantity": link.quantity} for link in rx.links
        ]
        resolved = await _resolve_items(db, body.items)
        # Replacing the collection in one flush re-INSERTs kept
        # (prescription_id, item_id) pairs BEFORE the orphan DELETEs land
        # (unit of work orders inserts first) → uq_prescription_item_links_pair
        # violation. Delete first, flush, then insert the replacement links.
        rx.links = []
        await db.flush()
        rx.links = [
            PrescriptionItemLink(item_id=item_id, quantity=quantity)
            for item_id, quantity in resolved
        ]
    await db.commit()
    rx = await _get_prescription_or_404(db, rx.id)
    changed = audit.diff_details(
        before,
        {
            **({"notes": rx.notes} if "notes" in before else {}),
            **(
                {"prescribed_at": rx.prescribed_at.isoformat()}
                if "prescribed_at" in before
                else {}
            ),
            **(
                {
                    "items": [
                        {"item_id": link.item_id, "quantity": link.quantity}
                        for link in rx.links
                    ]
                }
                if "items" in before
                else {}
            ),
        },
        list(before),
    )
    await audit.log_action(
        db,
        user=user,
        request=request,
        action=audit.UPDATE,
        entity_type="prescription",
        entity_id=rx.id,
        summary=", ".join(link.item.name for link in rx.links) or "(بدون قلم)",
        details=changed or None,
    )
    return _out(rx, await _created_by_username(db, rx))


@router.delete("/prescriptions/{prescription_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prescription(
    prescription_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_perm("prescriptions.write")),
):
    """Soft delete; links are kept so a trash restore is lossless."""
    rx = await _get_prescription_or_404(db, prescription_id)
    rx.deleted_at = utc_now()
    await db.commit()
    await audit.log_action(
        db,
        user=user,
        request=request,
        action=audit.DELETE,
        entity_type="prescription",
        entity_id=rx.id,
        summary=", ".join(link.item.name for link in rx.links) or "(بدون قلم)",
    )
    return None
