"""Generic CRUD for tag-like and diagnosis-like entities (name + id)."""

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_perm
from app.api.pagination import Page, clamp_limit_offset, paginate
from app.core.errors import BusinessRuleError, ConflictError, NotFoundError
from app.core.search import LIKE_ESCAPE, like_contains
from app.core.tokens import utc_now
from app.db.session import get_db
from app.models import Diagnosis, Tag, User, patient_diagnoses, patient_tags
from app.schemas import NamedCreateIn, NamedRef, NamedRenameIn
from app.services import audit

router = APIRouter(tags=["taxonomies"])

# selects in the patient filter/create UIs need the full list in one page
TAXONOMY_MAX_PAGE_SIZE = 1000


async def _merge_links(db: AsyncSession, link_table, link_fk, *, src_id: int, dst_id: int) -> int:
    """Move M2M links from the merged entry to the survivor in one
    transaction (callers commit). Patients already holding the survivor
    drop the source link instead of colliding with the composite PK."""
    from sqlalchemy import delete, select, update

    await db.execute(
        delete(link_table).where(
            link_fk == src_id,
            link_table.c.patient_id.in_(
                select(link_table.c.patient_id).where(link_fk == dst_id)
            ),
        )
    )
    result = await db.execute(
        update(link_table).where(link_fk == src_id).values(**{link_fk.key: dst_id})
    )
    return int(getattr(result, "rowcount", 0) or 0)


def _make_router(prefix: str, model, link_table, link_fk) -> APIRouter:
    r = APIRouter(prefix=prefix, tags=["taxonomies"])

    @r.get("", response_model=Page[NamedRef])
    async def list_all(
        q: str | None = None,
        limit: int = 100,
        offset: int = 0,
        db: AsyncSession = Depends(get_db),
        _: User = Depends(get_current_user),
    ):
        stmt = select(model).where(model.deleted_at.is_(None))
        if q:
            stmt = stmt.where(
                model.name.ilike(like_contains(q), escape=LIKE_ESCAPE)
            )
        stmt = stmt.order_by(model.name)
        limit, offset = clamp_limit_offset(limit, offset, TAXONOMY_MAX_PAGE_SIZE)
        rows, total = await paginate(
            db, stmt, limit=limit, offset=offset, max_size=TAXONOMY_MAX_PAGE_SIZE
        )
        return Page(items=rows, total=total, limit=limit, offset=offset)

    entity_kind = prefix.strip("/").rstrip("s")

    @r.post("", response_model=NamedRef, status_code=status.HTTP_201_CREATED)
    async def create(
        body: NamedCreateIn,
        request: Request,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_perm("taxonomies.write")),
    ):
        name = body.name.strip()
        if not name:
            raise BusinessRuleError("Name required", code="name_required")
        exists = await db.scalar(
            select(model).where(model.name == name, model.deleted_at.is_(None))
        )
        if exists:
            kind = entity_kind.capitalize()
            raise ConflictError(f"{kind} already exists", code="name_taken")
        obj = model(name=name)
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
        await audit.log_action(
            db,
            user=user,
            request=request,
            action=audit.CREATE,
            entity_type=entity_kind,
            entity_id=obj.id,
            summary=obj.name,
        )
        return obj

    @r.patch("/{obj_id}", response_model=NamedRef)
    async def rename(
        obj_id: int,
        body: NamedRenameIn,
        request: Request,
        merge: bool = False,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_perm("taxonomies.write")),
    ):
        """Rename; when the new name already exists:
        `merge=false` → 409 `name_taken` (UI asks the user), `merge=true` →
        the entries are MERGED (requires this same `taxonomies.write` perm,
        which also gates tag/diag deletion): M2M links move to the survivor
        (patients keeping both lose the duplicate), the source is
        soft-deleted; one transaction, one audit row."""
        obj = await db.scalar(
            select(model).where(model.id == obj_id, model.deleted_at.is_(None))
        )
        if obj is None:
            raise NotFoundError(
                f"{entity_kind.capitalize()} not found", code=f"{entity_kind}_not_found"
            )
        name = body.name.strip()
        if not name:
            raise BusinessRuleError("Name required", code="name_required")
        dup = await db.scalar(
            select(model).where(
                model.name == name,
                model.id != obj_id,
                model.deleted_at.is_(None),
            )
        )
        if dup:
            if not merge:
                raise ConflictError("Name already taken", code="name_taken")
            if dup.id == obj.id:  # unreachable (dup.id != obj_id above); guard for mypy
                raise ConflictError("Name already taken", code="name_taken")
            moved = await _merge_links(db, link_table, link_fk, src_id=obj.id, dst_id=dup.id)
            obj.deleted_at = utc_now()
            await db.commit()
            await db.refresh(dup)
            await audit.log_action(
                db,
                user=user,
                request=request,
                action=audit.MERGE,
                entity_type=entity_kind,
                entity_id=obj.id,
                summary=f"merged «{obj.name}» into «{dup.name}»",
                details={"moved_links": moved, "survivor_id": dup.id},
            )
            return dup
        old_name = obj.name
        obj.name = name
        await db.commit()
        await db.refresh(obj)
        await audit.log_action(
            db,
            user=user,
            request=request,
            action=audit.UPDATE,
            entity_type=entity_kind,
            entity_id=obj.id,
            summary=f"{old_name} → {obj.name}",
        )
        return obj

    @r.delete("/{obj_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete(
        obj_id: int,
        request: Request,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_perm("taxonomies.write")),
    ):
        """Soft delete: hidden from lists/patient filters; M2M links kept so
        restoring is lossless."""
        obj = await db.scalar(
            select(model).where(model.id == obj_id, model.deleted_at.is_(None))
        )
        if obj is None:
            raise NotFoundError(
                f"{entity_kind.capitalize()} not found", code=f"{entity_kind}_not_found"
            )
        obj.deleted_at = utc_now()
        await db.commit()
        await audit.log_action(
            db,
            user=user,
            request=request,
            action=audit.DELETE,
            entity_type=entity_kind,
            entity_id=obj.id,
            summary=obj.name,
        )
        return None

    return r


router.include_router(
    _make_router("/tags", Tag, patient_tags, patient_tags.c.tag_id)
)
router.include_router(
    _make_router("/diagnoses", Diagnosis, patient_diagnoses, patient_diagnoses.c.diagnosis_id)
)
