import datetime as dt
import json

from pydantic import BaseModel, ConfigDict, Field


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    is_system: bool
    permissions: list[str] = Field(default_factory=list)
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
