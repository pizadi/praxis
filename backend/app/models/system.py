import datetime as dt
import json

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.domain import Base, partial_unique_where, soft_delete_column


class Role(Base):
    """Admin-definable role holding a set of permission keys (JSON array).

    System roles (admin/doctor/receptionist) are seeded at startup; `admin`
    is locked so the instance can never lock itself out of role management.
    """

    __tablename__ = "roles"
    __table_args__ = (
        Index("uq_roles_name_live", "name", unique=True, **partial_unique_where()),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    permissions_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    deleted_at: Mapped[dt.datetime | None] = soft_delete_column()
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    users: Mapped[list["User"]] = relationship(back_populates="role")

    @property
    def permissions(self) -> list[str]:
        try:
            parsed = json.loads(self.permissions_json)
        except (TypeError, ValueError):
            return []
        return parsed if isinstance(parsed, list) else []


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("uq_users_username_live", "username", unique=True, **partial_unique_where()),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    full_name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    deleted_at: Mapped[dt.datetime | None] = soft_delete_column()
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    role: Mapped[Role] = relationship(back_populates="users", lazy="selectin")
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def role_name(self) -> str:
        return self.role.name if self.role is not None else ""

    @property
    def permissions(self) -> list[str]:
        return self.role.permissions if self.role is not None else []

    def has_perm(self, *perms: str) -> bool:
        """True if the user holds ANY of the given permission keys."""
        held = set(self.permissions)
        return any(p in held for p in perms)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        UniqueConstraint("jti", name="uq_refresh_tokens_jti"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    jti: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="refresh_tokens")


class LoginAudit(Base):
    __tablename__ = "login_audit"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ip_address: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AuditLog(Base):
    """Every mutating action: who did what, to which entity, when.

    `details` holds a small JSON payload (e.g. changed fields for updates,
    amounts for payments); `ip` is the client address. Login attempts are
    kept in login_audit; this table is for CRUD actions.
    """

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_created_at", "created_at"),
        Index("ix_audit_log_entity", "entity_type", "entity_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    # action: create | update | delete | restore | purge
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    # entity_type: patient | appointment | file | transaction | tag | diagnosis | user
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    summary: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    details: Mapped[str | None] = mapped_column(Text())  # JSON string
    ip_address: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
