import datetime as dt
import typing as t

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import NATIONAL_ID_RE, YEAR_RE
from app.schemas.taxonomies import NamedRef


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
    def no_space_trim(cls, value: str) -> str:
        return value.strip()

    @field_validator("insurance")
    @classmethod
    def blank_to_none(cls, value: str | None) -> str | None:
        return value or None


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
    tags: list[NamedRef] = Field(default_factory=list)
    diagnoses: list[NamedRef] = Field(default_factory=list)
    created_at: dt.datetime
    updated_at: dt.datetime
