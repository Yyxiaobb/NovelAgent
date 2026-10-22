from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)


class KnowledgeBaseInfo(BaseModel):
    id: int
    name: str
    description: str | None
    document_count: int
    ready_document_count: int
    created_at: datetime
    updated_at: datetime
    is_deleted: bool = False


class KnowledgeDocumentCreate(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=1_000_000)


class KnowledgeDocumentInfo(BaseModel):
    id: int
    knowledge_base_id: int
    filename: str
    status: str
    error_message: str | None
    chunk_count: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class KnowledgeCitation(BaseModel):
    knowledge_base_id: int
    knowledge_base_name: str
    document_id: int
    filename: str
    chunk_index: int
    similarity: float
    excerpt: str
