import datetime as dt
import enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Domain — 1:1 with the legacy Django model (phase 1; refinements in phase 2)
#
# Soft deletes: every domain table has `deleted_at` (NULL = alive). Uniqueness
# is enforced via PARTIAL unique indexes (WHERE deleted_at IS NULL) so a
# deleted row never blocks reusing its national_id/name/filename, and a
# restored row collides only if a live duplicate was created meanwhile.
# ---------------------------------------------------------------------------


def soft_delete_column() -> Mapped[dt.datetime | None]:
    return mapped_column(DateTime(timezone=True), nullable=True, default=None)


def partial_unique_where():
    """Dialect-portable WHERE clause for partial unique indexes.

    sqlite_where applies under SQLite (tests); postgresql_where under
    PostgreSQL (production). Both express "only live rows must be unique".
    """
    from sqlalchemy import text

    clause = text("deleted_at IS NULL")
    return {"sqlite_where": clause, "postgresql_where": clause}


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (
        Index("uq_tags_name_live", "name", unique=True, **partial_unique_where()),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    deleted_at: Mapped[dt.datetime | None] = soft_delete_column()

    patients: Mapped[list["Patient"]] = relationship(
        secondary="patient_tags", back_populates="tags"
    )


class Diagnosis(Base):
    __tablename__ = "diagnoses"
    __table_args__ = (
        Index("uq_diagnoses_name_live", "name", unique=True, **partial_unique_where()),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    deleted_at: Mapped[dt.datetime | None] = soft_delete_column()

    patients: Mapped[list["Patient"]] = relationship(
        secondary="patient_diagnoses", back_populates="diagnoses"
    )


patient_tags = Table(
    "patient_tags",
    Base.metadata,
    Column("patient_id", ForeignKey("patients.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)

patient_diagnoses = Table(
    "patient_diagnoses",
    Base.metadata,
    Column("patient_id", ForeignKey("patients.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "diagnosis_id",
        ForeignKey("diagnoses.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Gender(enum.Enum):
    MALE = 0
    FEMALE = 1


class Patient(Base):
    __tablename__ = "patients"
    __table_args__ = (
        Index("ix_patients_national_id", "national_id"),
        Index("ix_patients_last_first_name", "last_name", "first_name"),
        Index(
            "uq_patients_national_id_live",
            "national_id",
            unique=True,
            **partial_unique_where(),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    national_id: Mapped[str] = mapped_column(String(10), nullable=False)
    first_name: Mapped[str] = mapped_column(String(128), nullable=False)
    last_name: Mapped[str] = mapped_column(String(128), nullable=False)
    insurance: Mapped[str | None] = mapped_column(String(128))
    year_of_birth: Mapped[str] = mapped_column(String(4), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    gender: Mapped[Gender] = mapped_column(SmallInteger, nullable=False)
    deleted_at: Mapped[dt.datetime | None] = soft_delete_column()
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    tags: Mapped[list[Tag]] = relationship(
        secondary=patient_tags, back_populates="patients", lazy="selectin"
    )
    diagnoses: Mapped[list[Diagnosis]] = relationship(
        secondary=patient_diagnoses, back_populates="patients", lazy="selectin"
    )
    appointments: Mapped[list["Appointment"]] = relationship(
        back_populates="patient", cascade="all, delete-orphan"
    )


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (Index("ix_appointments_scheduled_at", "scheduled_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"), nullable=False
    )
    scheduled_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    cm: Mapped[str] = mapped_column(Text, default="", nullable=False)
    hx: Mapped[str] = mapped_column(Text, default="", nullable=False)
    px: Mapped[str] = mapped_column(Text, default="", nullable=False)
    rx: Mapped[str] = mapped_column(Text, default="", nullable=False)
    deleted_at: Mapped[dt.datetime | None] = soft_delete_column()
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    patient: Mapped[Patient] = relationship(back_populates="appointments")
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="appointment", cascade="all, delete-orphan"
    )
    attachments: Mapped[list["Attachment"]] = relationship(
        back_populates="appointment", cascade="all, delete-orphan"
    )


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_appointment_id", "appointment_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    appointment_id: Mapped[int] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False
    )
    description: Mapped[str] = mapped_column(String(128), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    pos: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    deleted_at: Mapped[dt.datetime | None] = soft_delete_column()

    appointment: Mapped[Appointment] = relationship(
        back_populates="transactions", lazy="joined"
    )


class Attachment(Base):
    __tablename__ = "attachments"
    __table_args__ = (
        Index(
            "uq_attachments_stored_filename_live",
            "stored_filename",
            unique=True,
            **partial_unique_where(),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    appointment_id: Mapped[int] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False
    )
    description: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    stored_filename: Mapped[str | None] = mapped_column(String(255))
    original_filename: Mapped[str | None] = mapped_column(String(255))
    mime_type: Mapped[str | None] = mapped_column(String(128))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    missing_file: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[dt.datetime | None] = soft_delete_column()
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    appointment: Mapped[Appointment] = relationship(back_populates="attachments")
