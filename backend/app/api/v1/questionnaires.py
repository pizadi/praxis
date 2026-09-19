"""Questionnaire templates (admin-defined) and responses (per patient).

Templates: full CRUD for holders of questionnaires.templates; the format
document is validated on every write path (API body or uploaded JSON —
the upload UI posts the same body, so validation is identical).

Responses: belong to a PATIENT. Answers are validated against the
template's current format at write time and stored as raw nullable JSON;
template edits later are reconciled at render time (client-side), with a
clear-invalid-fields flow that goes through PATCH (re-validated).
"""

import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_perm
from app.api.pagination import Page, clamp_limit_offset, paginate, paginate_rows
from app.core.errors import BusinessRuleError
from app.core.tokens import utc_now
from app.db.session import get_db
from app.models import Patient, QuestionnaireResponse, QuestionnaireTemplate, User
from app.schemas import (
    QuestionnaireResponseCreateIn,
    QuestionnaireResponseOut,
    QuestionnaireResponseReportOut,
    QuestionnaireResponseUpdateIn,
    QuestionnaireTemplateCreateIn,
    QuestionnaireTemplateOut,
    QuestionnaireTemplateUpdateIn,
)
from app.services import audit
from app.services.questionnaires import parse_format

router = APIRouter(tags=["questionnaires"])


def _template_out(t: QuestionnaireTemplate) -> QuestionnaireTemplateOut:
    return QuestionnaireTemplateOut.model_validate(
        {
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "format": json.loads(t.format_json),
            "created_at": t.created_at,
            "updated_at": t.updated_at,
        }
    )


def _response_out(
    r: QuestionnaireResponse, template_name: str = "", created_by: str | None = None
) -> QuestionnaireResponseOut:
    return QuestionnaireResponseOut.model_validate(
        {
            "id": r.id,
            "patient_id": r.patient_id,
            "template_id": r.template_id,
            "template_name": template_name,
            "answers": json.loads(r.answers_json),
            "created_by_username": created_by,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
        }
    )


async def _get_live_template(db: AsyncSession, template_id: int) -> QuestionnaireTemplate:
    t = await db.get(QuestionnaireTemplate, template_id)
    if t is None or t.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Template not found")
    return t


async def _get_live_response(
    db: AsyncSession, response_id: int
) -> QuestionnaireResponse:
    stmt = (
        select(QuestionnaireResponse)
        .join(Patient, QuestionnaireResponse.patient_id == Patient.id)
        .where(
            QuestionnaireResponse.id == response_id,
            QuestionnaireResponse.deleted_at.is_(None),
            Patient.deleted_at.is_(None),
        )
    )
    r = await db.scalar(stmt)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Response not found")
    return r


# --- templates ------------------------------------------------------------------


@router.get("/questionnaires/templates", response_model=Page[QuestionnaireTemplateOut])
async def list_templates(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_perm("questionnaires.read")),
):
    stmt = (
        select(QuestionnaireTemplate)
        .where(QuestionnaireTemplate.deleted_at.is_(None))
        .order_by(QuestionnaireTemplate.name)
    )
    limit, offset = clamp_limit_offset(limit, offset)
    rows, total = await paginate(db, stmt, limit=limit, offset=offset)
    return Page(
        items=[_template_out(t) for t in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/questionnaires/templates/validate",
    response_model=QuestionnaireTemplateOut,
)
async def validate_template_format(
    body: QuestionnaireTemplateCreateIn,
    _: User = Depends(require_perm("questionnaires.templates")),
):
    """Validate a format document (e.g. before upload) without saving it."""
    try:
        fmt = parse_format(body.format)
    except Exception as exc:  # json or pydantic — both are client errors
        raise BusinessRuleError(
            f"Invalid questionnaire format: {exc}", code="invalid_format"
        ) from None
    return QuestionnaireTemplateOut.model_validate(
        {
            "id": 0,
            "name": body.name,
            "description": body.description,
            "format": json.loads(fmt.dumps()),
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }
    )


@router.post(
    "/questionnaires/templates",
    response_model=QuestionnaireTemplateOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_template(
    body: QuestionnaireTemplateCreateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_perm("questionnaires.templates")),
):
    dup = await db.scalar(
        select(QuestionnaireTemplate).where(
            QuestionnaireTemplate.name == body.name,
            QuestionnaireTemplate.deleted_at.is_(None),
        )
    )
    if dup:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Template name already taken"
        )
    try:
        fmt = parse_format(body.format)
    except Exception as exc:
        raise BusinessRuleError(
            f"Invalid questionnaire format: {exc}", code="invalid_format"
        ) from None
    t = QuestionnaireTemplate(
        name=body.name,
        description=body.description,
        format_json=fmt.dumps(),
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    await audit.log_action(
        db,
        user=actor,
        request=request,
        action=audit.CREATE,
        entity_type="questionnaire_template",
        entity_id=t.id,
        summary=t.name,
        details={"questions": len(fmt.questions)},
    )
    return _template_out(t)


@router.get("/questionnaires/templates/{template_id}", response_model=QuestionnaireTemplateOut)
async def get_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_perm("questionnaires.read")),
):
    t = await _get_live_template(db, template_id)
    return _template_out(t)


@router.patch(
    "/questionnaires/templates/{template_id}", response_model=QuestionnaireTemplateOut
)
async def update_template(
    template_id: int,
    body: QuestionnaireTemplateUpdateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_perm("questionnaires.templates")),
):
    t = await _get_live_template(db, template_id)
    before_name = t.name
    before_fmt = t.format_json
    if body.name is not None and body.name != t.name:
        dup = await db.scalar(
            select(QuestionnaireTemplate).where(
                QuestionnaireTemplate.name == body.name,
                QuestionnaireTemplate.deleted_at.is_(None),
                QuestionnaireTemplate.id != t.id,
            )
        )
        if dup:
            raise HTTPException(
                status.HTTP_409_CONFLICT, detail="Template name already taken"
            )
        t.name = body.name
    if body.description is not None:
        t.description = body.description
    if body.format is not None:
        try:
            fmt = parse_format(body.format)
        except Exception as exc:
            raise BusinessRuleError(
                f"Invalid questionnaire format: {exc}", code="invalid_format"
            ) from None
        t.format_json = fmt.dumps()
    await db.commit()
    await db.refresh(t)
    details = {}
    if before_name != t.name:
        details["name"] = {"old": before_name, "new": t.name}
    if before_fmt != t.format_json:
        details["format"] = {"old": "…", "new": "…"}
    await audit.log_action(
        db,
        user=actor,
        request=request,
        action=audit.UPDATE,
        entity_type="questionnaire_template",
        entity_id=t.id,
        summary=t.name,
        details=details or None,
    )
    return _template_out(t)


@router.delete(
    "/questionnaires/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_template(
    template_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_perm("questionnaires.templates")),
):
    t = await _get_live_template(db, template_id)
    t.deleted_at = utc_now()
    await db.commit()
    await audit.log_action(
        db,
        user=actor,
        request=request,
        action=audit.DELETE,
        entity_type="questionnaire_template",
        entity_id=t.id,
        summary=t.name,
    )
    return None


# --- responses --------------------------------------------------------------------


async def _validate_answers_or_422(
    db: AsyncSession, template_id: int, answers: dict
) -> QuestionnaireTemplate:
    t = await db.get(QuestionnaireTemplate, template_id)
    if t is None or t.deleted_at is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Template not found")
    fmt = parse_format(t.format_json)
    errors = fmt.validate_answers(answers)
    if errors:
        raise BusinessRuleError(
            "Invalid answers for this questionnaire",
            code="invalid_answers",
            details={"fields": errors},
        )
    return t


@router.get(
    "/patients/{patient_id}/questionnaires",
    response_model=Page[QuestionnaireResponseOut],
)
async def list_patient_responses(
    patient_id: int,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_perm("questionnaires.read")),
):
    patient = await db.get(Patient, patient_id)
    if patient is None or patient.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Patient not found")
    stmt = (
        select(QuestionnaireResponse)
        .join(QuestionnaireTemplate, QuestionnaireResponse.template_id == QuestionnaireTemplate.id)
        .where(
            QuestionnaireResponse.patient_id == patient_id,
            QuestionnaireResponse.deleted_at.is_(None),
            QuestionnaireTemplate.deleted_at.is_(None),
        )
        .order_by(
            QuestionnaireResponse.created_at.desc(), QuestionnaireResponse.id.desc()
        )
    )
    limit, offset = clamp_limit_offset(limit, offset)
    rows, total = await paginate(db, stmt, limit=limit, offset=offset)
    # template names + creator usernames for the page (no N+1: two IN queries)
    names: dict[int, str] = {}
    if rows:
        tids = {r.template_id for r in rows}
        trows = (
            await db.execute(
                select(QuestionnaireTemplate.id, QuestionnaireTemplate.name).where(
                    QuestionnaireTemplate.id.in_(tids)
                )
            )
        ).all()
        names = {tid: name for tid, name in trows}
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
            _response_out(
                r,
                template_name=names.get(r.template_id, ""),
                created_by=users_map.get(r.created_by_id) if r.created_by_id else None,
            )
            for r in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/patients/{patient_id}/questionnaires",
    response_model=QuestionnaireResponseOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_response(
    patient_id: int,
    body: QuestionnaireResponseCreateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_perm("questionnaires.fill")),
):
    patient = await db.get(Patient, patient_id)
    if patient is None or patient.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Patient not found")
    await _validate_answers_or_422(db, body.template_id, body.answers)
    r = QuestionnaireResponse(
        patient_id=patient_id,
        template_id=body.template_id,
        answers_json=json.dumps(body.answers, ensure_ascii=False, sort_keys=True),
        created_by_id=actor.id,
    )
    db.add(r)
    await db.commit()
    await db.refresh(r)
    t = await db.get(QuestionnaireTemplate, body.template_id)
    await audit.log_action(
        db,
        user=actor,
        request=request,
        action=audit.CREATE,
        entity_type="questionnaire_response",
        entity_id=r.id,
        summary=f"{t.name if t else body.template_id} — {patient.first_name} {patient.last_name}",
    )
    return _response_out(r, template_name=t.name if t else "", created_by=actor.username)


@router.get(
    "/questionnaires/responses", response_model=Page[QuestionnaireResponseReportOut]
)
async def list_responses_report(
    template_id: int,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_perm("questionnaires.read")),
):
    """Cross-patient responses of one template (report table + CSV export).

    Subtree rule: only rows whose patient (and template) are live are listed.
    """
    t = await _get_live_template(db, template_id)
    stmt = (
        select(QuestionnaireResponse, Patient.national_id)
        .join(Patient, QuestionnaireResponse.patient_id == Patient.id)
        .where(
            QuestionnaireResponse.template_id == template_id,
            QuestionnaireResponse.deleted_at.is_(None),
            Patient.deleted_at.is_(None),
        )
        .order_by(QuestionnaireResponse.created_at.desc(), QuestionnaireResponse.id.desc())
    )
    limit, offset = clamp_limit_offset(limit, offset)
    rows, total = await paginate_rows(db, stmt, limit=limit, offset=offset)
    users_map: dict[int, str] = {}
    if rows:
        uids = {r.created_by_id for r, _ in rows if r.created_by_id is not None}
        if uids:
            urows = (
                await db.execute(select(User.id, User.username).where(User.id.in_(uids)))
            ).all()
            users_map = {uid: username for uid, username in urows}
    items = []
    for r, national_id in rows:
        base = _response_out(
            r,
            template_name=t.name,
            created_by=users_map.get(r.created_by_id) if r.created_by_id else None,
        )
        items.append(
            QuestionnaireResponseReportOut.model_validate(
                {**base.model_dump(), "patient_national_id": national_id}
            )
        )
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/questionnaires/responses/{response_id}", response_model=QuestionnaireResponseOut)
async def get_response(
    response_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_perm("questionnaires.read")),
):
    r = await _get_live_response(db, response_id)
    t = await db.get(QuestionnaireTemplate, r.template_id)
    created_by = None
    if r.created_by_id is not None:
        u = await db.get(User, r.created_by_id)
        created_by = u.username if u else None
    return _response_out(r, template_name=t.name if t else "", created_by=created_by)


@router.patch(
    "/questionnaires/responses/{response_id}", response_model=QuestionnaireResponseOut
)
async def update_response(
    response_id: int,
    body: QuestionnaireResponseUpdateIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_perm("questionnaires.fill")),
):
    r = await _get_live_response(db, response_id)
    t = await db.get(QuestionnaireTemplate, r.template_id)
    if t is None or t.deleted_at is not None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Template no longer available"
        )
    await _validate_answers_or_422(db, r.template_id, body.answers)
    before = r.answers_json
    r.answers_json = json.dumps(body.answers, ensure_ascii=False, sort_keys=True)
    await db.commit()
    await db.refresh(r)
    await audit.log_action(
        db,
        user=actor,
        request=request,
        action=audit.UPDATE,
        entity_type="questionnaire_response",
        entity_id=r.id,
        summary=t.name,
        details={"changed": before != r.answers_json},
    )
    return _response_out(r, template_name=t.name, created_by=actor.username)


@router.delete(
    "/questionnaires/responses/{response_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_response(
    response_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_perm("questionnaires.fill")),
):
    r = await _get_live_response(db, response_id)
    r.deleted_at = utc_now()
    await db.commit()
    await audit.log_action(
        db,
        user=actor,
        request=request,
        action=audit.DELETE,
        entity_type="questionnaire_response",
        entity_id=r.id,
        summary=f"response {r.id}",
    )
    return None
