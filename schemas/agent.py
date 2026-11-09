from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator
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
    review_enabled: bool = False
    review_rounds: int = 0
    review_final_score: Optional[int] = None
    review_stop_reason: Optional[str] = None
    review_error: Optional[str] = None
    review_history: list[dict] = Field(default_factory=list)
    revision_decisions: list[dict] = Field(default_factory=list)


ReviewIssueCategory = Literal[
    "goal", "continuity", "character", "causality",
    "style", "pacing", "ending",
]
ReviewIssueSeverity = Literal["minor", "major", "critical"]


class ReviewIssue(BaseModel):
    """A concrete, evidence-backed issue found in a generated draft."""

    id: str = Field(..., min_length=1, max_length=80)
    category: ReviewIssueCategory
    severity: ReviewIssueSeverity
    evidence: str = Field(..., min_length=1, max_length=1000)
    suggestion: str = Field(..., min_length=1, max_length=1000)
    must_fix: bool = False


class ContentReview(BaseModel):
    """Structured editorial review returned by the read-only reviewer agent."""

    overall_score: int = Field(..., ge=0, le=100)
    summary: str = Field(..., min_length=1, max_length=2000)
    strengths: list[str] = Field(default_factory=list, max_length=8)
    issues: list[ReviewIssue] = Field(default_factory=list, max_length=20)
    dimension_scores: dict[str, int] = Field(default_factory=dict, max_length=10)
    stop_recommendation: bool = False

    @field_validator("dimension_scores")
    @classmethod
    def validate_dimension_scores(cls, value: dict[str, int]) -> dict[str, int]:
        allowed = {"goal", "continuity", "character", "causality", "style", "pacing", "ending"}
        if any(key not in allowed or score < 0 or score > 100 for key, score in value.items()):
            raise ValueError("dimension_scores must contain only 0-100 scores for known dimensions")
        return value


class RevisionDecision(BaseModel):
    issue_id: str = Field(..., min_length=1, max_length=80)
    decision: Literal["accepted", "partially_accepted", "rejected"]
    reason: str = Field(..., min_length=1, max_length=1000)


class RevisionOutput(BaseModel):
    content: str = Field(..., min_length=1, max_length=100000)
    revision_decisions: list[RevisionDecision] = Field(default_factory=list, max_length=20)


class ChapterMemoryGenerationRequest(BaseModel):
    user_idea: Optional[str] = Field(None, max_length=3000)


class ChapterMemoryGenerationResponse(BaseModel):
    project_id: int
    chapter_id: int
    summary: str
    memory: ChapterMemory
