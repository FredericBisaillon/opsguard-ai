from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from opsguard_api.models import DocumentStatus


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
