"""Pydantic schemas, split by API domain and re-exported for compatibility."""

from app.schemas.appointments import (
    AppointmentBase,
    AppointmentBrief,
    AppointmentCreateIn,
    AppointmentOut,
    AppointmentStageChangeIn,
    AppointmentUpdateIn,
)
from app.schemas.attachments import (
    AttachmentCreateIn,
    AttachmentOut,
    AttachmentUpdateIn,
)
from app.schemas.auth import LoginIn, TokenPair
from app.schemas.patients import PatientBase, PatientCreateIn, PatientOut, PatientUpdateIn
from app.schemas.prescriptions import (
    PrescriptionCreateIn,
    PrescriptionItemLinkIn,
    PrescriptionItemLinkOut,
    PrescriptionOut,
    PrescriptionUpdateIn,
)
from app.schemas.questionnaires import (
    FormulaQuestionRef,
    FormulaValidationIn,
    QuestionnaireResponseCreateIn,
    QuestionnaireResponseOut,
    QuestionnaireResponseReportOut,
    QuestionnaireResponseUpdateIn,
    QuestionnaireTemplateCreateIn,
    QuestionnaireTemplateOut,
    QuestionnaireTemplateUpdateIn,
)
from app.schemas.reports import (
    AuditEntryOut,
    DailyStat,
    DescriptionStat,
    PaymentTypeStat,
    StatsSummary,
    TrashItemOut,
)
from app.schemas.roles import RoleCreateIn, RoleOut, RoleUpdateIn
from app.schemas.taxonomies import NamedCreateIn, NamedRef, NamedRenameIn
from app.schemas.transactions import (
    PatientPaymentOut,
    PatientTransactionOut,
    TransactionBase,
    TransactionCreateIn,
    TransactionOut,
    TransactionUpdateIn,
)
from app.schemas.users import UserCreateIn, UserOut, UserUpdateIn

__all__ = [
    "AppointmentBase",
    "AppointmentBrief",
    "AppointmentCreateIn",
    "AppointmentOut",
    "AppointmentStageChangeIn",
    "AppointmentUpdateIn",
    "AttachmentCreateIn",
    "AttachmentOut",
    "AttachmentUpdateIn",
    "AuditEntryOut",
    "DailyStat",
    "DescriptionStat",
    "FormulaQuestionRef",
    "FormulaValidationIn",
    "LoginIn",
    "NamedCreateIn",
    "NamedRef",
    "NamedRenameIn",
    "PatientBase",
    "PatientCreateIn",
    "PatientOut",
    "PatientPaymentOut",
    "PatientTransactionOut",
    "PatientUpdateIn",
    "PaymentTypeStat",
    "PrescriptionCreateIn",
    "PrescriptionItemLinkIn",
    "PrescriptionItemLinkOut",
    "PrescriptionOut",
    "PrescriptionUpdateIn",
    "QuestionnaireResponseCreateIn",
    "QuestionnaireResponseOut",
    "QuestionnaireResponseReportOut",
    "QuestionnaireResponseUpdateIn",
    "QuestionnaireTemplateCreateIn",
    "QuestionnaireTemplateOut",
    "QuestionnaireTemplateUpdateIn",
    "RoleCreateIn",
    "RoleOut",
    "RoleUpdateIn",
    "StatsSummary",
    "TokenPair",
    "TrashItemOut",
    "TransactionBase",
    "TransactionCreateIn",
    "TransactionOut",
    "TransactionUpdateIn",
    "UserCreateIn",
    "UserOut",
    "UserUpdateIn",
]
