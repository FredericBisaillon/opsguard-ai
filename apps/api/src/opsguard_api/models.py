from datetime import datetime
from enum import StrEnum
from typing import Any

from pgvector.sqlalchemy import VECTOR  # type: ignore[import-untyped]
from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opsguard_api.constants import DEFAULT_EMBEDDING_DIMENSIONS
from opsguard_api.db import Base


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    EXTRACTING = "extracting"
    TEXT_EXTRACTED = "text_extracted"
    EXTRACTION_FAILED = "extraction_failed"
    CHUNKING = "chunking"
    CHUNKED = "chunked"
    CHUNKING_FAILED = "chunking_failed"
    EMBEDDING = "embedding"
    EMBEDDED = "embedded"
    EMBEDDING_FAILED = "embedding_failed"
    PENDING = "pending"
    PROCESSED = "processed"
    FAILED = "failed"


class ReviewTaskSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReviewTaskStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class ReviewTaskSource(StrEnum):
    MANUAL = "manual"
    AI_SUGGESTED = "ai_suggested"


class AuditEventType(StrEnum):
    REVIEW_TASK_CREATED = "review_task_created"
    REVIEW_TASK_DISMISSED = "review_task_dismissed"
    AI_REVIEW_TASK_SUGGESTED = "ai_review_task_suggested"
    AI_REVIEW_TASK_CREATED = "ai_review_task_created"
    AI_REVIEW_TASK_REJECTED = "ai_review_task_rejected"
    AI_REVIEW_NO_SUGGESTION = "ai_review_no_suggestion"
    RAG_PROMPT_INJECTION_DETECTED = "rag_prompt_injection_detected"


class AuditActorType(StrEnum):
    SYSTEM = "system"
    HUMAN = "human"
    AI = "ai"


class AuditEventSource(StrEnum):
    MANUAL = "manual"
    AI = "ai"
    API = "api"
    SYSTEM = "system"


class AuditEventStatus(StrEnum):
    SUCCESS = "success"
    REJECTED = "rejected"
    FAILED = "failed"
    INFO = "info"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=DocumentStatus.UPLOADED.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="DocumentChunk.chunk_index",
    )
    review_tasks: Mapped[list["ReviewTask"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by=lambda: ReviewTask.created_at.desc(),
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_document_chunks_document_id_chunk_index",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    character_count: Mapped[int] = mapped_column(Integer, nullable=False)
    section_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    start_char: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_char: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(
        VECTOR(DEFAULT_EMBEDDING_DIMENSIONS),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    document: Mapped[Document] = relationship(back_populates="chunks")
    review_tasks: Mapped[list["ReviewTask"]] = relationship(
        back_populates="chunk",
        passive_deletes=True,
    )


class ReviewTask(Base):
    __tablename__ = "review_tasks"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_review_tasks_severity",
        ),
        CheckConstraint(
            "status IN ('open', 'in_progress', 'resolved', 'dismissed')",
            name="ck_review_tasks_status",
        ),
        CheckConstraint(
            "source IN ('manual', 'ai_suggested')",
            name="ck_review_tasks_source",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ReviewTaskSeverity.MEDIUM.value,
        server_default=ReviewTaskSeverity.MEDIUM.value,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ReviewTaskStatus.OPEN.value,
        server_default=ReviewTaskStatus.OPEN.value,
    )
    source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ReviewTaskSource.MANUAL.value,
        server_default=ReviewTaskSource.MANUAL.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    document: Mapped[Document] = relationship(back_populates="review_tasks")
    chunk: Mapped[DocumentChunk | None] = relationship(back_populates="review_tasks")


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ("
            "'review_task_created', "
            "'review_task_dismissed', "
            "'ai_review_task_suggested', "
            "'ai_review_task_created', "
            "'ai_review_task_rejected', "
            "'ai_review_no_suggestion', "
            "'rag_prompt_injection_detected'"
            ")",
            name="ck_audit_events_event_type",
        ),
        CheckConstraint(
            "actor_type IN ('system', 'human', 'ai')",
            name="ck_audit_events_actor_type",
        ),
        CheckConstraint(
            "source IN ('manual', 'ai', 'api', 'system')",
            name="ck_audit_events_source",
        ),
        CheckConstraint(
            "status IN ('success', 'rejected', 'failed', 'info')",
            name="ck_audit_events_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    review_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("review_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSON,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
