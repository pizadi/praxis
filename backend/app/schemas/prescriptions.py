import datetime as dt

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PrescriptionItemLinkIn(BaseModel):
    """One existing item id or a new name, plus optional quantity."""

    item_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=128)
    quantity: int | None = Field(default=None, ge=1, le=10**6)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("name must not be blank")
        return value


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
    items: list[PrescriptionItemLinkOut] = Field(default_factory=list)
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
