import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str
    role_id: int
    role_name: str
    permissions: list[str] = Field(default_factory=list)
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
