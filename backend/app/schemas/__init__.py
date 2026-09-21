"""Pydantic v2 request/response schemas.

Field rules mirror the legacy model's *intended* validation (anchored regexes),
while the DB itself stays permissive for dirty legacy rows.
"""

import datetime as dt
import json
import re
import typing as t

from pydantic import BaseModel, ConfigDict, Field, field_validator

NATIONAL_ID_RE = re.compile(r"^[0-9]{10}$")
YEAR_RE = re.compile(r"^[0-9]{4}$")
PHONE_RE = re.compile(r"^[0-9]+$")


# --- Auth / users -------------------------------------------------------------


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshIn(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str
    role_id: int
    role_name: str
    permissions: list[str] = []
    is_active: bool
    created_at: dt.datetime


class UserCreateIn(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(default="", max_length=128)
    role_id: int


class UserUpdateIn(BaseModel):
    full_name: str | None = Field(default=None, max_length=128)
    role_id: int | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


# --- Roles ----------------------------------------------------------------------


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    is_system: bool
    permissions: list[str] = []
    user_count: int = 0
    created_at: dt.datetime

    @classmethod
    def json_sorted(cls, perms: list[str]) -> str:
        """Canonical (deduplicated, sorted) JSON storage for a permission set."""
        return json.dumps(sorted(set(perms)), ensure_ascii=False)


class RoleCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    permissions: list[str] = Field(default_factory=list)


class RoleUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    permissions: list[str] | None = None


# --- Tags & diagnoses ----------------------------------------------------------


class NamedRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class NamedCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)


class NamedRenameIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)


# --- Patients ------------------------------------------------------------------


class PatientBase(BaseModel):
    national_id: str = Field(pattern=NATIONAL_ID_RE.pattern)
    first_name: str = Field(min_length=1, max_length=128)
    last_name: str = Field(min_length=1, max_length=128)
    insurance: str | None = Field(default=None, max_length=128)
    year_of_birth: str = Field(pattern=YEAR_RE.pattern)
    phone_number: str = Field(default="", max_length=20)
    gender: t.Literal[0, 1]

    @field_validator("national_id", "year_of_birth", "phone_number")
    @classmethod
    def no_space_trim(cls, v: str) -> str:
        return v.strip()

    @field_validator("insurance")
    @classmethod
    def blank_to_none(cls, v: str | None) -> str | None:
        return v or None


class PatientCreateIn(PatientBase):
    tag_ids: list[int] = Field(default_factory=list)
    diagnosis_ids: list[int] = Field(default_factory=list)


class PatientUpdateIn(BaseModel):
    national_id: str | None = Field(default=None, pattern=NATIONAL_ID_RE.pattern)
    first_name: str | None = Field(default=None, min_length=1, max_length=128)
    last_name: str | None = Field(default=None, min_length=1, max_length=128)
    insurance: str | None = Field(default=None, max_length=128)
    year_of_birth: str | None = Field(default=None, pattern=YEAR_RE.pattern)
    phone_number: str | None = Field(default=None, max_length=20)
    gender: t.Literal[0, 1] | None = None
    tag_ids: list[int] | None = None
    diagnosis_ids: list[int] | None = None


class PatientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    national_id: str
    first_name: str
    last_name: str
    insurance: str | None
    year_of_birth: str
    phone_number: str
    gender: int
    tags: list[NamedRef] = []
    diagnoses: list[NamedRef] = []
    created_at: dt.datetime
    updated_at: dt.datetime


# --- Appointments ---------------------------------------------------------------


class AppointmentBase(BaseModel):
    scheduled_at: dt.datetime
    notes: str = Field(default="", max_length=10000)
    cm: str = Field(default="", max_length=100000)
    hx: str = Field(default="", max_length=100000)
    px: str = Field(default="", max_length=100000)
    rx: str = Field(default="", max_length=100000)


class AppointmentCreateIn(AppointmentBase):
    pass


class AppointmentUpdateIn(BaseModel):
    scheduled_at: dt.datetime | None = None
    notes: str | None = Field(default=None, max_length=10000)
    cm: str | None = Field(default=None, max_length=100000)
    hx: str | None = Field(default=None, max_length=100000)
    px: str | None = Field(default=None, max_length=100000)
    rx: str | None = Field(default=None, max_length=100000)


class AppointmentBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    patient_id: int
    scheduled_at: dt.datetime
    stage: int
    patient_first_name: str
    patient_last_name: str
    patient_national_id: str


class AppointmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    patient_id: int
    scheduled_at: dt.datetime
    stage: int
    notes: str
    cm: str
    hx: str
    px: str
    rx: str
    patient_first_name: str
    patient_last_name: str
    patient_national_id: str
    created_at: dt.datetime
    updated_at: dt.datetime


class AppointmentStageChangeIn(BaseModel):
    """One step along the visit pipeline (advance/regress); the server
    computes the target stage and enforces the boundaries."""

    direction: t.Literal["advance", "regress"]


# --- Attachments -----------------------------------------------------------------


class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    patient_id: int
    description: str
    notes: str
    stored_filename: str | None
    original_filename: str | None
    mime_type: str | None
    size_bytes: int | None
    missing_file: bool
    created_at: dt.datetime
    updated_at: dt.datetime


class AttachmentCreateIn(BaseModel):
    description: str = Field(default="", max_length=128)
    notes: str = Field(default="", max_length=10000)


class AttachmentUpdateIn(BaseModel):
    description: str | None = Field(default=None, max_length=128)
    notes: str | None = Field(default=None, max_length=10000)


# --- Prescriptions ------------------------------------------------------------------


class PrescriptionItemLinkIn(BaseModel):
    """One item of a prescription: an existing item id OR a new name
    (auto-registered in the dictionary), plus an optional quantity."""

    item_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=128)
    quantity: int | None = Field(default=None, ge=1, le=10**6)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("name must not be blank")
        return v


class PrescriptionItemLinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_id: int
    item_name: str
    quantity: int | None


class PrescriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    patient_id: int
    prescribed_at: dt.datetime
    notes: str
    created_by_username: str | None = None
    source_appointment_id: int | None = None
    items: list[PrescriptionItemLinkOut] = []
    created_at: dt.datetime
    updated_at: dt.datetime


class PrescriptionCreateIn(BaseModel):
    prescribed_at: dt.datetime | None = None
    notes: str = Field(default="", max_length=10000)
    items: list[PrescriptionItemLinkIn] = Field(default_factory=list)


class PrescriptionUpdateIn(BaseModel):
    prescribed_at: dt.datetime | None = None
    notes: str | None = Field(default=None, max_length=10000)
    items: list[PrescriptionItemLinkIn] | None = None


# --- Transactions ------------------------------------------------------------------


class TransactionBase(BaseModel):
    description: str = Field(min_length=1, max_length=128)
    amount: int = Field(ge=0, le=10**15)
    pos: bool = True


class TransactionCreateIn(TransactionBase):
    pass


class TransactionUpdateIn(BaseModel):
    description: str | None = Field(default=None, min_length=1, max_length=128)
    amount: int | None = Field(default=None, ge=0, le=10**15)
    pos: bool | None = None


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    appointment_id: int
    description: str
    amount: int
    pos: bool


class PatientTransactionOut(BaseModel):
    """Transaction with its appointment date, for patient-level payment views."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    appointment_id: int
    appointment_scheduled_at: dt.datetime
    description: str
    amount: int
    pos: bool


class PatientPaymentOut(BaseModel):
    """Transaction + appointment date + owning patient, for day-wide payment views."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    appointment_id: int
    appointment_scheduled_at: dt.datetime
    patient_id: int
    patient_first_name: str
    patient_last_name: str
    description: str
    amount: int
    pos: bool


class PaymentTypeStat(BaseModel):
    """Per-payment-type (description) aggregates for one day."""

    description: str
    count: int
    total_amount: int
    pos_amount: int
    cash_amount: int


# --- Stats ---------------------------------------------------------------------------


class StatsSummary(BaseModel):
    start: dt.date
    end: dt.date
    num_appointments: int
    total_amount: int
    pos_amount: int
    cash_amount: int
    num_transactions: int
    by_description: list["DescriptionStat"]


class DescriptionStat(BaseModel):
    description: str
    count: int
    total_amount: int


class DailyStat(BaseModel):
    date: dt.date
    num_appointments: int
    total_amount: int


# --- Trash (soft-deleted items) -------------------------------------------------------


class TrashItemOut(BaseModel):
    """One soft-deleted row, with context for display in the trash panel."""

    id: int
    type: str  # patients | appointments | transactions | attachments | tags | diagnoses | users
    deleted_at: dt.datetime
    # human context (which fields are set depends on the type)
    title: str
    subtitle: str = ""
    # for appointments/files/txns: whether the parent is also deleted
    parent_deleted: bool = False


class AuditEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    username: str
    action: str
    entity_type: str
    entity_id: int | None
    summary: str
    details: str | None
    ip_address: str
    created_at: dt.datetime


# --- Questionnaires -------------------------------------------------------------------


class QuestionnaireTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    format: dict[str, t.Any] = {}
    created_at: dt.datetime
    updated_at: dt.datetime


class QuestionnaireTemplateCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=512)
    format: dict[str, t.Any]


class QuestionnaireTemplateUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=512)
    format: dict[str, t.Any] | None = None


class QuestionnaireResponseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    patient_id: int
    template_id: int
    template_name: str = ""
    answers: dict[str, t.Any] = {}
    created_by_username: str | None = None
    created_at: dt.datetime
    updated_at: dt.datetime


class QuestionnaireResponseReportOut(QuestionnaireResponseOut):
    """Row of the cross-patient responses report (adds patient identity)."""

    patient_national_id: str = ""


class QuestionnaireResponseCreateIn(BaseModel):
    template_id: int
    answers: dict[str, t.Any] = Field(default_factory=dict)


class QuestionnaireResponseUpdateIn(BaseModel):
    answers: dict[str, t.Any]
