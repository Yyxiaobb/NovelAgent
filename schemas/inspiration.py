from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class InspirationCreate(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=5000)


class InspirationUpdate(InspirationCreate):
    refined_content: str | None = Field(default=None, max_length=20000)


class InspirationInfo(BaseModel):
    id: int
    title: str
    content: str
    refined_content: str | None
    is_deleted: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InspirationRefineResponse(InspirationInfo):
    pass
