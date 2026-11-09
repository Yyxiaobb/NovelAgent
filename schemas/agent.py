from typing import Optional

from pydantic import BaseModel, Field
from schemas.projects import ChapterMemory, ChapterPlan
from schemas.knowledge_base import KnowledgeCitation


class IdeaRefinementRequest(BaseModel):
    idea: str = Field(min_length=1, max_length=5000)


class IdeaRefinementResponse(BaseModel):
    idea: str
    refined_idea: str


class OutlineGenerationRequest(BaseModel):
    expected_words: int = Field(..., gt=0, le=10000000)
    user_idea: Optional[str] = Field(None, max_length=3000)
    inspiration_ids: list[int] = Field(default_factory=list, max_length=10)
    knowledge_base_ids: list[int] = Field(default_factory=list, max_length=10)


class ProjectCoverGenerationRequest(BaseModel):
    author_name: str = Field(..., min_length=1, max_length=50)


class OutlineVolumeGenerationRequest(BaseModel):
    user_idea: Optional[str] = Field(None, max_length=5000)
    knowledge_base_ids: list[int] = Field(default_factory=list, max_length=10)


class OutlineVolumePlanGenerationRequest(BaseModel):
    expected_words: int = Field(..., gt=0, le=10000000)
    replace_existing: bool = False
    user_idea: Optional[str] = Field(None, max_length=5000)
    knowledge_base_ids: list[int] = Field(default_factory=list, max_length=10)


class OutlineVolumePlanItem(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    stage_goal: str = Field(..., min_length=1, max_length=2000)
    central_conflict: str = Field(..., min_length=1, max_length=2000)
    key_events: list[str] = Field(..., min_length=3, max_length=6)
    character_arc: str = Field(..., min_length=1, max_length=2000)
    ending_hook: str = Field(..., min_length=1, max_length=2000)


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
    volume_id: Optional[int] = None
    volume_complete: bool = False
    volume_completion_note: Optional[str] = None


class RollingChapterPlanGenerationRequest(BaseModel):
    # Existing chapters are identified by ID. New chapters are represented by
    # chapter_numbers and are only persisted after the model returns a valid
    # complete batch.
    chapter_ids: list[int] = Field(default_factory=list, max_length=5)
    chapter_numbers: list[int] = Field(default_factory=list, max_length=5)
    expected_words: int = Field(3000, gt=0, le=100000)
    user_idea: Optional[str] = Field(None, max_length=5000)
    knowledge_base_ids: list[int] = Field(default_factory=list, max_length=10)


class RollingChapterPlanItem(BaseModel):
    chapter_id: int
    chapter_number: int
    chapter_name: str
    plan: ChapterPlan


class RollingChapterPlanGenerationResponse(BaseModel):
    project_id: int
    plans: list[RollingChapterPlanItem]
    citations: list[KnowledgeCitation] = Field(default_factory=list)
    volume_id: Optional[int] = None
    volume_complete: bool = False
    volume_completion_note: Optional[str] = None


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
