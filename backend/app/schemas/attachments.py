import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


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
