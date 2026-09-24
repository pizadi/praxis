from pydantic import BaseModel, ConfigDict, Field


class NamedRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class NamedCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)


class NamedRenameIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
