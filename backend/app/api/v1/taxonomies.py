"""Generic CRUD for tag-like and diagnosis-like entities (name + id)."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_perm
from app.core.errors import ConflictError
from app.core.tokens import utc_now
from app.db.session import get_db
from app.models import Diagnosis, Tag, User
from app.schemas import NamedCreateIn, NamedRef, NamedRenameIn
from app.services import audit

router = APIRouter(tags=["taxonomies"])


def _make_router(prefix: str, model) -> APIRouter:
    r = APIRouter(prefix=prefix, tags=["taxonomies"])

    @r.get("", response_model=list[NamedRef])
    async def list_all(
        db: AsyncSession = Depends(get_db),
        _: User = Depends(get_current_user),
    ):
        rows = (
            await db.scalars(
                select(model)
                .where(model.deleted_at.is_(None))
                .order_by(model.name)
            )
        ).all()
        return list(rows)

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
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Name required")
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
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_perm("taxonomies.write")),
    ):
        obj = await db.scalar(
            select(model).where(model.id == obj_id, model.deleted_at.is_(None))
        )
        if obj is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not found")
        name = body.name.strip()
        if not name:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Name required")
        dup = await db.scalar(
            select(model).where(
                model.name == name,
                model.id != obj_id,
                model.deleted_at.is_(None),
            )
        )
        if dup:
            raise ConflictError("Name already taken", code="name_taken")
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
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not found")
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


router.include_router(_make_router("/tags", Tag))
router.include_router(_make_router("/diagnoses", Diagnosis))
