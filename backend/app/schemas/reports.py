import datetime as dt

from pydantic import BaseModel, ConfigDict


class PaymentTypeStat(BaseModel):
    """Per-description aggregates for one day."""

    description: str
    count: int
    total_amount: int
    pos_amount: int
    cash_amount: int


class DescriptionStat(BaseModel):
    description: str
    count: int
    total_amount: int


class StatsSummary(BaseModel):
    start: dt.date
    end: dt.date
    num_appointments: int
    total_amount: int
    pos_amount: int
    cash_amount: int
    num_transactions: int
    by_description: list[DescriptionStat]


class DailyStat(BaseModel):
    date: dt.date
    num_appointments: int
    total_amount: int


class TrashItemOut(BaseModel):
    """One soft-deleted row, with context for display in the trash panel."""

    id: int
    type: str
    deleted_at: dt.datetime
    title: str
    subtitle: str = ""
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
