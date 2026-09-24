import datetime as dt
import typing as t

from pydantic import BaseModel, ConfigDict, Field


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
    """One step along the visit pipeline; the server enforces boundaries."""

    direction: t.Literal["advance", "regress"]
