from typing import Literal, Optional

from pydantic import BaseModel, Field
from schemas.projects import ChapterMemory, ChapterPlan


ProjectField = Literal["projectname", "introduction", "project_type"]


class ProjectFieldGenerationRequest(BaseModel):
    field: ProjectField
    projectname: Optional[str] = Field(None, max_length=50)
    introduction: Optional[str] = Field(None, max_length=1000)
    project_type: Optional[str] = Field(None, max_length=30)


class ProjectFieldGenerationResponse(BaseModel):
    field: ProjectField
    value: str


class OutlineGenerationRequest(BaseModel):
    expected_words: int = Field(..., gt=0, le=10000000)
    user_idea: Optional[str] = Field(None, max_length=5000)


class OutlineGenerationResponse(BaseModel):
    project_id: int
    expected_words: int
    outline: str


class ChapterPlanGenerationRequest(BaseModel):
    expected_words: int = Field(3000, gt=0, le=100000)
    user_idea: Optional[str] = Field(None, max_length=5000)


class ChapterPlanGenerationResponse(BaseModel):
    project_id: int
    chapter_id: int
    plan: ChapterPlan


class ChapterGenerationRequest(BaseModel):
    plan: Optional[ChapterPlan] = None
    expected_words: Optional[int] = Field(None, gt=0, le=100000)
    user_idea: Optional[str] = Field(None, max_length=5000)


class ChapterGenerationResponse(BaseModel):
    project_id: int
    chapter_id: int
    expected_words: int
    plan: ChapterPlan
    content: str


class ChapterMemoryGenerationRequest(BaseModel):
    user_idea: Optional[str] = Field(None, max_length=3000)


class ChapterMemoryGenerationResponse(BaseModel):
    project_id: int
    chapter_id: int
    summary: str
    memory: ChapterMemory
