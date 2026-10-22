from typing import Literal, Optional

from pydantic import BaseModel, Field
from schemas.projects import ChapterMemory, ChapterPlan
from schemas.knowledge_base import KnowledgeCitation


ProjectField = Literal["projectname", "introduction", "project_type"]


class ProjectFieldGenerationRequest(BaseModel):
    field: ProjectField
    projectname: Optional[str] = Field(None, max_length=50)
    introduction: Optional[str] = Field(None, max_length=1000)
    project_type: Optional[str] = Field(None, max_length=30)


class ProjectFieldGenerationResponse(BaseModel):
    field: ProjectField
    value: str


class IdeaRefinementRequest(BaseModel):
    idea: str = Field(min_length=1, max_length=5000)


class IdeaRefinementResponse(BaseModel):
    idea: str
    refined_idea: str


class OutlineGenerationRequest(BaseModel):
    expected_words: int = Field(..., gt=0, le=10000000)
    user_idea: Optional[str] = Field(None, max_length=5000)
    knowledge_base_ids: list[int] = Field(default_factory=list, max_length=10)


class OutlineGenerationResponse(BaseModel):
    project_id: int
    expected_words: int
    outline: str
    citations: list[KnowledgeCitation] = Field(default_factory=list)


class ChapterPlanGenerationRequest(BaseModel):
    expected_words: int = Field(3000, gt=0, le=100000)
    user_idea: Optional[str] = Field(None, max_length=5000)
    knowledge_base_ids: list[int] = Field(default_factory=list, max_length=10)


class ChapterPlanGenerationResponse(BaseModel):
    project_id: int
    chapter_id: int
    plan: ChapterPlan
    citations: list[KnowledgeCitation] = Field(default_factory=list)


class ChapterGenerationRequest(BaseModel):
    plan: Optional[ChapterPlan] = None
    expected_words: Optional[int] = Field(None, gt=0, le=100000)
    user_idea: Optional[str] = Field(None, max_length=5000)
    knowledge_base_ids: list[int] = Field(default_factory=list, max_length=10)


class ChapterGenerationResponse(BaseModel):
    project_id: int
    chapter_id: int
    expected_words: int
    plan: ChapterPlan
    content: str
    citations: list[KnowledgeCitation] = Field(default_factory=list)


class ChapterMemoryGenerationRequest(BaseModel):
    user_idea: Optional[str] = Field(None, max_length=3000)


class ChapterMemoryGenerationResponse(BaseModel):
    project_id: int
    chapter_id: int
    summary: str
    memory: ChapterMemory
