from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


MemoryCategory = Literal["character", "world", "thread", "timeline"]


class StoryMemoryRequest(BaseModel):
    category: MemoryCategory
    title: str = Field(..., min_length=1, max_length=100)
    content: str = Field(..., min_length=1, max_length=10000)
    keywords: list[str] = Field(default_factory=list, max_length=30)
    source_chapter_id: int | None = Field(default=None, gt=0)
    is_active: bool = True


class StoryMemoryInfo(BaseModel):
    id: int
    project_id: int
    category: MemoryCategory
    title: str
    content: str
    keywords: list[str]
    source_chapter_id: int | None
    is_active: bool
    review_status: Literal["pending", "approved", "rejected"]
    origin: Literal["manual", "chapter_extract"]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StoryMemoryReviewRequest(BaseModel):
    decision: Literal["approved", "rejected"]


class StoryMemoryBatchReviewRequest(BaseModel):
    memory_ids: list[int] = Field(..., min_length=1, max_length=100)
    decision: Literal["approved", "rejected"]


class StoryMemoryConflictInfo(BaseModel):
    first_id: int
    second_id: int
    category: MemoryCategory
    similarity: float
    reason: Literal["same_title", "shared_keywords", "similar_content"]
