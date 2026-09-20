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
    # DEPRECATED since 1.3: legacy free-text prescription. Never written by
    # the app anymore (prescriptions are structured rows now); kept as a
    # lossless archive of pre-1.3 data. Still gated by medical_notes.view.
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
    # Since 1.3 files belong to the PATIENT, not the appointment — they
    # survive appointment deletion and are managed on the patient page.
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"), nullable=False
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

    patient: Mapped[Patient] = relationship()


class QuestionnaireTemplate(Base):
    """Admin-defined questionnaire format.

    `format_json` holds the validated format document:
    {"version": 1, "title": str, "questions": [
        {"key": "snake_case", "label": str, "type": "number"|"choice"|"string",
         "required": bool, ...type-specific fields...}
    ]}
    Responses store raw key→value JSON (nullable); rendering merges them with
    the *current* template (no snapshot): removed keys are ignored, new
    questions render as null, invalid values render as missing.
    """

    __tablename__ = "questionnaire_templates"
    __table_args__ = (
        Index(
            "uq_questionnaire_templates_name_live",
            "name",
            unique=True,
            **partial_unique_where(),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    format_json: Mapped[str] = mapped_column(Text, nullable=False)
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

    responses: Mapped[list["QuestionnaireResponse"]] = relationship(
        back_populates="template"
    )


class QuestionnaireResponse(Base):
    """One filled questionnaire, attached to a PATIENT (not an appointment).

    `answers_json` maps question key → value (int/float | str | null).
    Keys not in the (possibly edited) template are tolerated in storage and
    ignored at render time; required/validity is enforced only at write time.
    """

    __tablename__ = "questionnaire_responses"
    __table_args__ = (
        Index("ix_questionnaire_responses_patient_id", "patient_id"),
        Index("ix_questionnaire_responses_template_id", "template_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"), nullable=False
    )
    template_id: Mapped[int] = mapped_column(
        ForeignKey("questionnaire_templates.id"), nullable=False
    )
    answers_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
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

    patient: Mapped[Patient] = relationship()
    template: Mapped[QuestionnaireTemplate] = relationship(back_populates="responses")


# ---------------------------------------------------------------------------
# Prescriptions (v1.3) — structured replacement for the legacy free-text
# `appointments.rx` column. A prescription belongs to a PATIENT (like
# questionnaire responses); `prescription_items` is a tag-like dictionary
# (autocomplete); the link table carries the per-item quantity (NULL =
# unspecified/legacy).
# ---------------------------------------------------------------------------


class PrescriptionItem(Base):
    """Tag-like prescription entry (a drug, a test, an instruction…)."""

    __tablename__ = "prescription_items"
    __table_args__ = (
        Index(
            "uq_prescription_items_name_live",
            "name",
            unique=True,
            **partial_unique_where(),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    deleted_at: Mapped[dt.datetime | None] = soft_delete_column()


class Prescription(Base):
    """One prescription: patient + timestamp + items/quantities + notes.

    `source_appointment_id` records which (legacy or live) appointment the
    prescription was derived from during data migration — provenance only,
    intentionally NOT a FK so it survives appointment purges. Legacy
    migration fills it; UI-created prescriptions leave it NULL.
    """

    __tablename__ = "prescriptions"
    __table_args__ = (
        Index("ix_prescriptions_patient_id", "patient_id"),
        Index("ix_prescriptions_source_appointment_id", "source_appointment_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"), nullable=False
    )
    prescribed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    source_appointment_id: Mapped[int | None] = mapped_column(nullable=True)
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

    patient: Mapped[Patient] = relationship()
    links: Mapped[list["PrescriptionItemLink"]] = relationship(
        back_populates="prescription", cascade="all, delete-orphan"
    )


class PrescriptionItemLink(Base):
    """M2M prescription ↔ prescription_item with a per-item quantity.

    A prescription's items are a SET (unique pair); editing a prescription
    replaces its links. Rows hard-delete with their parents (links are
    never soft-deleted independently).
    """

    __tablename__ = "prescription_item_links"
    __table_args__ = (
        Index(
            "uq_prescription_item_links_pair",
            "prescription_id",
            "item_id",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    prescription_id: Mapped[int] = mapped_column(
        ForeignKey("prescriptions.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[int] = mapped_column(
        ForeignKey("prescription_items.id", ondelete="CASCADE"), nullable=False
    )
    quantity: Mapped[int | None] = mapped_column(nullable=True)

    prescription: Mapped[Prescription] = relationship(back_populates="links")
    item: Mapped[PrescriptionItem] = relationship()
