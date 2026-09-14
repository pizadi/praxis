from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_at_least
from app.api.pagination import Page, clamp_limit_offset, paginate
from app.core.enums import UserRole
from app.core.errors import ConflictError
from app.core.tokens import utc_now
from app.db.session import get_db
from app.models import Diagnosis, Gender, Patient, Tag, User
from app.schemas import (
    PatientCreateIn,
    PatientOut,
    PatientUpdateIn,
)
from app.services import audit

router = APIRouter(prefix="/patients", tags=["patients"])


async def _get_or_404(db: AsyncSession, patient_id: int) -> Patient:
    stmt = select(Patient).where(
        Patient.id == patient_id, Patient.deleted_at.is_(None)
    )
    patient = await db.scalar(stmt)
    if patient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Patient not found")
    return patient


async def _resolve_m2m(db: AsyncSession, model, ids: list[int]) -> list:
    if not ids:
        return []
    rows = (
        await db.scalars(
            select(model).where(model.id.in_(ids), model.deleted_at.is_(None))
        )
    ).all()
    if len(rows) != len(set(ids)):
        found = {r.id for r in rows}
        missing = [i for i in dict.fromkeys(ids) if i not in found]
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown or deleted ids: {missing}",
        )
    return list(rows)


@router.get("", response_model=Page[PatientOut])
async def list_patients(
    q: str | None = None,
    national_id: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    phone: str | None = None,
    insurance: str | None = None,
    year_of_birth: str | None = None,
    gender: int | None = None,
    tag_ids: str | None = None,
    diagnosis_ids: str | None = None,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_at_least(UserRole.RECEPTIONIST)),
):
    """Search patients. All filtering happens in SQL.

    q: fuzzy across first/last/national id/phone; phone: digits-contains;
    insurance: ilike contains; year_of_birth: digits-contains;
    gender: exact (0=male, 1=female);
    tag_ids/diagnosis_ids: comma lists, patients must have ALL of them.
    Soft-deleted patients are excluded everywhere.
    """
    stmt = select(Patient).where(Patient.deleted_at.is_(None))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                Patient.first_name.ilike(like),
                Patient.last_name.ilike(like),
                Patient.national_id.like(like),
                Patient.phone_number.like(like),
            )
        )
    if national_id:
        stmt = stmt.where(Patient.national_id.like(f"%{national_id}%"))
    if first_name:
        stmt = stmt.where(Patient.first_name.ilike(f"%{first_name}%"))
    if last_name:
        stmt = stmt.where(Patient.last_name.ilike(f"%{last_name}%"))
    if phone:
        stmt = stmt.where(Patient.phone_number.like(f"%{phone}%"))
    if insurance:
        stmt = stmt.where(Patient.insurance.ilike(f"%{insurance}%"))
    if year_of_birth:
        stmt = stmt.where(Patient.year_of_birth.like(f"%{year_of_birth}%"))
    if gender is not None:
        if gender not in (g.value for g in Gender):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, detail="gender must be 0 or 1"
            )
        stmt = stmt.where(Patient.gender == gender)

    def _ids(param: str | None) -> list[int]:
        if not param:
            return []
        try:
            return [int(x) for x in param.split(",") if x.strip()]
        except ValueError:
            raise HTTPException(422, detail="tag_ids/diagnosis_ids must be comma ints") from None

    tags = _ids(tag_ids)
    diags = _ids(diagnosis_ids)
    if tags:
        stmt = stmt.join(Patient.tags).where(
            Tag.id.in_(tags), Tag.deleted_at.is_(None)
        ).group_by(Patient.id).having(
            func.count(func.distinct(Tag.id)) == len(set(tags))
        )
    if diags:
        stmt = stmt.join(Patient.diagnoses).where(
            Diagnosis.id.in_(diags), Diagnosis.deleted_at.is_(None)
        ).group_by(Patient.id).having(
            func.count(func.distinct(Diagnosis.id)) == len(set(diags))
        )
    stmt = stmt.order_by(Patient.last_name, Patient.first_name)
    limit, offset = clamp_limit_offset(limit, offset)
    items, total = await paginate(db, stmt, limit=limit, offset=offset)
    return Page(
        items=[PatientOut.model_validate(p) for p in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=PatientOut, status_code=status.HTTP_201_CREATED)
async def create_patient(
    body: PatientCreateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_at_least(UserRole.RECEPTIONIST)),
):
    dup = await db.scalar(
        select(Patient).where(
            Patient.national_id == body.national_id, Patient.deleted_at.is_(None)
        )
    )
    if dup:
        raise ConflictError("National ID already registered", code="national_id_taken")
    patient = Patient(
        national_id=body.national_id,
        first_name=body.first_name,
        last_name=body.last_name,
        insurance=body.insurance,
        year_of_birth=body.year_of_birth,
        phone_number=body.phone_number,
        gender=body.gender,
    )
    patient.tags = await _resolve_m2m(db, Tag, body.tag_ids)
    patient.diagnoses = await _resolve_m2m(db, Diagnosis, body.diagnosis_ids)
    db.add(patient)
    await db.commit()
    await db.refresh(patient)
    await audit.log_action(
        db,
        user=user,
        request=request,
        action=audit.CREATE,
        entity_type="patient",
        entity_id=patient.id,
        summary=f"{patient.first_name} {patient.last_name} ({patient.national_id})",
        details={"national_id": patient.national_id, "phone": patient.phone_number},
    )
    return patient


@router.get("/{patient_id}", response_model=PatientOut)
async def get_patient(
    patient_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_at_least(UserRole.RECEPTIONIST)),
):
    return await _get_or_404(db, patient_id)


@router.patch("/{patient_id}", response_model=PatientOut)
async def update_patient(
    patient_id: int,
    body: PatientUpdateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_at_least(UserRole.RECEPTIONIST)),
):
    patient = await _get_or_404(db, patient_id)
    data = body.model_dump(exclude_unset=True)
    before = {
        f: getattr(patient, f)
        for f in (
            "national_id",
            "first_name",
            "last_name",
            "insurance",
            "year_of_birth",
            "phone_number",
            "gender",
        )
    }
    if "national_id" in data and data["national_id"] != patient.national_id:
        dup = await db.scalar(
            select(Patient).where(
                Patient.national_id == data["national_id"],
                Patient.id != patient_id,
                Patient.deleted_at.is_(None),
            )
        )
        if dup:
            raise ConflictError("National ID already registered", code="national_id_taken")
    for field in (
        "national_id",
        "first_name",
        "last_name",
        "insurance",
        "year_of_birth",
        "phone_number",
        "gender",
    ):
        if field in data:
            setattr(patient, field, data[field])
    if "tag_ids" in data:
        patient.tags = await _resolve_m2m(db, Tag, data["tag_ids"])
    if "diagnosis_ids" in data:
        patient.diagnoses = await _resolve_m2m(db, Diagnosis, data["diagnosis_ids"])
    await db.commit()
    await db.refresh(patient)
    changed = audit.diff_details(before, {f: getattr(patient, f) for f in before}, list(before))
    await audit.log_action(
        db,
        user=user,
        request=request,
        action=audit.UPDATE,
        entity_type="patient",
        entity_id=patient.id,
        summary=f"{patient.first_name} {patient.last_name} ({patient.national_id})",
        details=changed or None,
    )
    return patient


@router.delete("/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_patient(
    patient_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_at_least(UserRole.ADMIN)),
):
    """Soft delete: stamps deleted_at; appointments/files/txns become invisible
    through join filtering and come back on restore. Physical files untouched.
    """
    patient = await _get_or_404(db, patient_id)
    patient.deleted_at = utc_now()
    await db.commit()
    await audit.log_action(
        db,
        user=user,
        request=request,
        action=audit.DELETE,
        entity_type="patient",
        entity_id=patient.id,
        summary=f"{patient.first_name} {patient.last_name} ({patient.national_id})",
    )
    return None
