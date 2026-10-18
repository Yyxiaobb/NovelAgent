from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field, ConfigDict


class ProjectRequest(BaseModel):
    projectname: Optional[str] = Field(None, min_length=2, max_length=20, description="小说名称")
    introduction: Optional[str] = Field(None, max_length=500, description="小说简介")
    project_type: Optional[str] = Field(None, max_length=30, description="作品类型")
    cover_url: Optional[str] = Field(None, max_length=500, description="作品封面地址")
    outline: Optional[str] = Field(None, max_length=100000, description="作品大纲")
    expected_words: Optional[int] = Field(None, gt=0, le=10000000, description="期望作品字数")
    status: Optional[Literal["连载中", "完结", "断更"]] = Field(None, description="作品状态")
class ProjectInfoBase(ProjectRequest):
    id: int
    expected_words: Optional[int] = None
    total_words: int = 0
    chapter_count: int = 0
    created_at: datetime
    updated_at: datetime
    status: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class ProjectUpdateRequest(ProjectRequest):
    pass


class OutlineRequest(BaseModel):
    outline: Optional[str] = Field(None, max_length=100000, description="作品大纲")


class OutlineInfo(BaseModel):
    project_id: int
    outline: Optional[str] = None


class OutlineVersionInfo(BaseModel):
    id: int
    project_id: int
    version_number: int
    source: str
    outline: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChapterPlan(BaseModel):
    objective: str = Field(..., min_length=1, max_length=2000, description="本章目标")
    conflict: str = Field(..., min_length=1, max_length=2000, description="本章核心冲突")
    key_events: str = Field(..., min_length=1, max_length=10000, description="关键情节")
    ending_hook: str = Field(..., min_length=1, max_length=2000, description="结尾钩子")
    expected_words: int = Field(..., gt=0, le=100000, description="本章目标字数")


class ChapterMemory(BaseModel):
    character_state: str = Field(..., max_length=10000, description="人物状态变化")
    setting_changes: str = Field(..., max_length=10000, description="设定变化")
    unresolved_threads: str = Field(..., max_length=10000, description="未解决线索")
    timeline: str = Field(..., max_length=5000, description="时间线信息")


class ChapterRequest(BaseModel):
    chapter_number: int = Field(..., gt=0, description="章节编号")
    chaptername: Optional[str] = Field(None, max_length=50, description="章节名称")
    content: Optional[str] = Field(None, max_length=100000, description="章节内容")
    plan: Optional[ChapterPlan] = Field(None, description="章节规划")
    summary: Optional[str] = Field(None, max_length=20000, description="章节摘要")
    memory: Optional[ChapterMemory] = Field(None, description="章节记忆")


class ChapterInfo(BaseModel):
    id: int
    project_id: int
    chapter_number: int
    chaptername: Optional[str] = None
    content: Optional[str] = None
    plan: Optional[ChapterPlan] = None
    summary: Optional[str] = None
    memory: Optional[ChapterMemory] = None
    created_at: datetime
    updated_at: datetime
    is_deleted: bool = False

    model_config = ConfigDict(from_attributes=True)


class ChapterVersionInfo(BaseModel):
    id: int
    chapter_id: int
    version_number: int
    source: str
    chapter_number: int
    chaptername: Optional[str] = None
    content: Optional[str] = None
    plan: Optional[ChapterPlan] = None
    summary: Optional[str] = None
    memory: Optional[ChapterMemory] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RecycledChapterInfo(ChapterInfo):
    projectname: Optional[str] = None
    project_status: Optional[str] = None
