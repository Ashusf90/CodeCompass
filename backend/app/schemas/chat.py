from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=2000)
    limit: int = Field(default=5, ge=1, le=10)
    language: str | None = Field(default=None, max_length=50)
    file_type: str | None = Field(default=None, max_length=50)
    rerank: bool = False
    exclude_tests: bool = False


class SearchHit(BaseModel):
    file_path: str
    symbol_name: str | None
    content: str
    start_line: int
    end_line: int
    similarity: float
    lexical_score: float = 0.0
    retrieval_score: float
    github_url: str


class SearchResponse(BaseModel):
    repository_id: UUID
    query: str
    results: list[SearchHit]


class ChatSessionCreate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)


class ChatStreamRequest(SearchRequest):
    session_id: UUID | None = None


class ChatSessionResponse(BaseModel):
    id: UUID
    repository_id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ChatMessageResponse(BaseModel):
    id: UUID
    session_id: UUID
    role: str
    content: str
    citations: list | None
    created_at: datetime
