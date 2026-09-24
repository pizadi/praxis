import datetime as dt
import typing as t

from pydantic import BaseModel, ConfigDict, Field


class QuestionnaireTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    format: dict[str, t.Any] = Field(default_factory=dict)
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
    answers: dict[str, t.Any] = Field(default_factory=dict)
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


class FormulaQuestionRef(BaseModel):
    key: str = Field(min_length=1, max_length=64)
    type: t.Literal["number", "choice", "string"]


class FormulaValidationIn(BaseModel):
    score_formula: str = ""
    questions: list[FormulaQuestionRef] = Field(default_factory=list)
