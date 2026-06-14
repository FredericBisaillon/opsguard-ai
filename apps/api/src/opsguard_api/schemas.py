from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from opsguard_api.models import (
    DocumentStatus,
    ReviewTaskSeverity,
    ReviewTaskSource,
    ReviewTaskStatus,
)


class DocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    source_type: str = Field(min_length=1, max_length=50)
    source_path: str = Field(min_length=1)


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    source_type: str
    source_path: str
    status: DocumentStatus
    created_at: datetime
    updated_at: datetime


class DocumentExtractionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: int
    status: DocumentStatus
    extracted_text_path: str
    character_count: int
    message: str


class DocumentChunkingRead(BaseModel):
    document_id: int
    status: DocumentStatus
    chunk_count: int
    chunk_max_chars: int
    chunk_overlap_chars: int
    message: str


class DocumentEmbeddingRead(BaseModel):
    document_id: int
    status: DocumentStatus
    embedding_model: str
    embedding_dimensions: int
    embedded_chunk_count: int
    message: str


class DocumentChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    chunk_index: int
    content: str
    character_count: int
    section_title: str | None
    start_char: int | None
    end_char: int | None
    created_at: datetime


class ReviewTaskCreate(BaseModel):
    document_id: int = Field(gt=0)
    chunk_id: int | None = Field(default=None, gt=0)
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    severity: ReviewTaskSeverity = ReviewTaskSeverity.MEDIUM
    status: ReviewTaskStatus = ReviewTaskStatus.OPEN

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        title = value.strip()
        if not title:
            raise ValueError("Title cannot be empty.")
        return title

    @field_validator("description")
    @classmethod
    def description_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value

        description = value.strip()
        if not description:
            raise ValueError("Description cannot be empty.")
        return description


class ReviewTaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    severity: ReviewTaskSeverity | None = None
    status: ReviewTaskStatus | None = None

    @model_validator(mode="after")
    def required_fields_must_not_be_null(self) -> "ReviewTaskUpdate":
        null_fields = [
            field_name
            for field_name in ("title", "severity", "status")
            if field_name in self.model_fields_set
            and getattr(self, field_name) is None
        ]
        if null_fields:
            raise ValueError(f"{', '.join(null_fields)} cannot be null.")

        return self

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value

        title = value.strip()
        if not title:
            raise ValueError("Title cannot be empty.")
        return title

    @field_validator("description")
    @classmethod
    def description_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value

        description = value.strip()
        if not description:
            raise ValueError("Description cannot be empty.")
        return description


class ReviewTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    chunk_id: int | None
    title: str
    description: str | None
    severity: ReviewTaskSeverity
    status: ReviewTaskStatus
    source: ReviewTaskSource
    created_at: datetime
    updated_at: datetime


class SemanticSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    document_id: int | None = Field(default=None, gt=0)
    top_k: int | None = Field(default=None, ge=1)

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        query = value.strip()
        if not query:
            raise ValueError("Query cannot be empty.")
        return query


class SemanticSearchResult(BaseModel):
    document_id: int
    document_title: str
    chunk_id: int
    chunk_index: int
    section_title: str | None
    content: str
    similarity_score: float


class SemanticSearchResponse(BaseModel):
    query: str
    top_k: int
    result_count: int
    results: list[SemanticSearchResult]


class AnswerRequest(BaseModel):
    query: str = Field(min_length=1)
    document_id: int | None = Field(default=None, gt=0)
    top_k: int | None = Field(default=None, ge=1)

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        query = value.strip()
        if not query:
            raise ValueError("Query cannot be empty.")
        return query


class AnswerCitation(BaseModel):
    source_id: str
    document_id: int
    document_title: str
    chunk_id: int
    chunk_index: int
    section_title: str | None
    excerpt: str
    similarity_score: float


class AnswerResponse(BaseModel):
    query: str
    answer: str
    is_answered: bool
    citations: list[AnswerCitation]
    retrieved_chunk_count: int
