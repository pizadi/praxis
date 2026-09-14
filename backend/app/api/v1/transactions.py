from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_at_least
from app.api.pagination import Page, clamp_limit_offset, paginate
from app.core.enums import UserRole
from app.core.tokens import utc_now
from app.db.session import get_db
from app.models import Appointment, Patient, Transaction, User
from app.schemas import TransactionCreateIn, TransactionOut, TransactionUpdateIn
from app.services import audit

router = APIRouter(prefix="/appointments", tags=["transactions"])


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


async def _get_txn_or_404(db: AsyncSession, txn_id: int) -> Transaction:
    stmt = (
        select(Transaction)
        .join(Appointment, Transaction.appointment_id == Appointment.id)
        .join(Patient, Appointment.patient_id == Patient.id)
        .where(
            Transaction.id == txn_id,
            Transaction.deleted_at.is_(None),
            Appointment.deleted_at.is_(None),
            Patient.deleted_at.is_(None),
        )
    )
    txn = await db.scalar(stmt)
    if txn is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return txn


@router.get("/{appointment_id}/transactions", response_model=Page[TransactionOut])
async def list_transactions(
    appointment_id: int,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_at_least(UserRole.RECEPTIONIST)),
):
    await _get_appt_or_404(db, appointment_id)
    stmt = (
        select(Transaction)
        .where(
            Transaction.appointment_id == appointment_id,
            Transaction.deleted_at.is_(None),
        )
        .order_by(Transaction.id)
    )
    limit, offset = clamp_limit_offset(limit, offset)
    items, total = await paginate(db, stmt, limit=limit, offset=offset)
    return Page(
        items=[TransactionOut.model_validate(t) for t in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/{appointment_id}/transactions",
    response_model=TransactionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_transaction(
    appointment_id: int,
    body: TransactionCreateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_at_least(UserRole.RECEPTIONIST)),
):
    await _get_appt_or_404(db, appointment_id)
    txn = Transaction(
        appointment_id=appointment_id,
        description=body.description,
        amount=body.amount,
        pos=body.pos,
    )
    db.add(txn)
    await db.commit()
    await db.refresh(txn)
    await audit.log_action(
        db,
        user=user,
        request=request,
        action=audit.CREATE,
        entity_type="transaction",
        entity_id=txn.id,
        summary=f"{txn.description} — {txn.amount}",
        details={"appointment_id": appointment_id, "pos": txn.pos},
    )
    return txn


@router.patch("/transactions/{txn_id}", response_model=TransactionOut)
async def update_transaction(
    txn_id: int,
    body: TransactionUpdateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_at_least(UserRole.RECEPTIONIST)),
):
    txn = await _get_txn_or_404(db, txn_id)
    data = body.model_dump(exclude_unset=True)
    before: dict[str, Any] = {
        f: getattr(txn, f) for f in ("description", "amount", "pos") if f in data
    }
    for field in ("description", "amount", "pos"):
        if field in data:
            setattr(txn, field, data[field])
    await db.commit()
    await db.refresh(txn)
    changed = audit.diff_details(before, {f: getattr(txn, f) for f in before}, list(before))
    await audit.log_action(
        db,
        user=user,
        request=request,
        action=audit.UPDATE,
        entity_type="transaction",
        entity_id=txn.id,
        summary=f"{txn.description} — {txn.amount}",
        details=changed or None,
    )
    return txn


@router.delete("/transactions/{txn_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(
    txn_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_at_least(UserRole.RECEPTIONIST)),
):
    txn = await _get_txn_or_404(db, txn_id)
    txn.deleted_at = utc_now()
    await db.commit()
    await audit.log_action(
        db,
        user=user,
        request=request,
        action=audit.DELETE,
        entity_type="transaction",
        entity_id=txn.id,
        summary=f"{txn.description} — {txn.amount}",
    )
    return None
