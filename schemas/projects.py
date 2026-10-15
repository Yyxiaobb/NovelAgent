from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class ProjectRequest(BaseModel):
    projectname: Optional[str] = Field(None, min_length=2, max_length=20, description="小说名称")
    introduction: Optional[str] = Field(None, max_length=500, description="小说简介")
class ProjectInfoBase(ProjectRequest):
    id: int
    total_words: int = 0
    chapter_count: int = 0
    created_at: datetime
    updated_at: datetime
    status: str

    model_config = ConfigDict(from_attributes=True)

class ProjectUpdateRequest(ProjectRequest):
    status: str
