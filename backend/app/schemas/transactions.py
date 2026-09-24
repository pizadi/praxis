import datetime as dt

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TransactionBase(BaseModel):
    description: str = Field(min_length=1, max_length=128)
    amount: int = Field(ge=0, le=10**15)
    pos: bool = True

    @field_validator("description", mode="before")
    @classmethod
    def strip_description(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class TransactionCreateIn(TransactionBase):
    pass


class TransactionUpdateIn(BaseModel):
    description: str | None = Field(default=None, min_length=1, max_length=128)
    amount: int | None = Field(default=None, ge=0, le=10**15)
    pos: bool | None = None

    @field_validator("description", mode="before")
    @classmethod
    def strip_description(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


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
    """Transaction + appointment date + owning patient, for day-wide views."""

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
