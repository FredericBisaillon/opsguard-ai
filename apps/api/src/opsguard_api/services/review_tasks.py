from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from opsguard_api.models import (
    AuditActorType,
    AuditEventSource,
    AuditEventStatus,
    AuditEventType,
    Document,
    DocumentChunk,
    ReviewTask,
    ReviewTaskSeverity,
    ReviewTaskSource,
    ReviewTaskStatus,
)
from opsguard_api.schemas import (
    AuditEventCreateInternal,
    ReviewTaskCreate,
    ReviewTaskUpdate,
)
from opsguard_api.services import audit_events as audit_events_service


class ReviewTaskError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def create_review_task(db: Session, task_in: ReviewTaskCreate) -> ReviewTask:
    return _create_review_task(
        db=db,
        task_in=task_in,
        source=ReviewTaskSource.MANUAL,
        audit_manual_creation=True,
    )


def create_ai_suggested_review_task(
    db: Session,
    task_in: ReviewTaskCreate,
) -> ReviewTask:
    return _create_review_task(
        db=db,
        task_in=task_in,
        source=ReviewTaskSource.AI_SUGGESTED,
    )


def _create_review_task(
    db: Session,
    task_in: ReviewTaskCreate,
    source: ReviewTaskSource,
    audit_manual_creation: bool = False,
) -> ReviewTask:
    _get_document_or_raise(db, task_in.document_id)
    _validate_chunk_reference(
        db=db,
        document_id=task_in.document_id,
        chunk_id=task_in.chunk_id,
    )

    task = ReviewTask(
        document_id=task_in.document_id,
        chunk_id=task_in.chunk_id,
        title=task_in.title,
        description=task_in.description,
        severity=task_in.severity.value,
        status=task_in.status.value,
        source=source.value,
    )

    db.add(task)
    db.flush()

    if audit_manual_creation:
        audit_events_service.create_audit_event(
            db=db,
            event_in=AuditEventCreateInternal(
                event_type=AuditEventType.REVIEW_TASK_CREATED,
                actor_type=AuditActorType.HUMAN,
                actor_id=None,
                document_id=task.document_id,
                review_task_id=task.id,
                source=AuditEventSource.MANUAL,
                status=AuditEventStatus.SUCCESS,
                summary=(
                    "Manual review task created "
                    f"for document {task.document_id}."
                ),
                metadata={
                    "chunk_id": task.chunk_id,
                    "severity": task.severity,
                    "task_status": task.status,
                },
            ),
            commit=False,
        )

    db.commit()
    db.refresh(task)

    return task


def list_review_tasks(
    db: Session,
    document_id: int | None = None,
    status: ReviewTaskStatus | None = None,
    severity: ReviewTaskSeverity | None = None,
) -> list[ReviewTask]:
    statement = select(ReviewTask).order_by(
        ReviewTask.created_at.desc(),
        ReviewTask.id.desc(),
    )

    if document_id is not None:
        statement = statement.where(ReviewTask.document_id == document_id)
    if status is not None:
        statement = statement.where(ReviewTask.status == status.value)
    if severity is not None:
        statement = statement.where(ReviewTask.severity == severity.value)

    return list(db.scalars(statement).all())


def get_review_task(db: Session, task_id: int) -> ReviewTask:
    task = db.get(ReviewTask, task_id)
    if task is None:
        raise ReviewTaskError("Review task not found.", status_code=404)

    return task


def update_review_task(
    db: Session,
    task_id: int,
    task_in: ReviewTaskUpdate,
) -> ReviewTask:
    task = get_review_task(db, task_id)
    changes = task_in.model_dump(exclude_unset=True)

    for field_name, value in changes.items():
        if isinstance(value, StrEnum):
            value = value.value
        setattr(task, field_name, value)

    db.add(task)
    db.commit()
    db.refresh(task)

    return task


def dismiss_review_task(db: Session, task_id: int) -> ReviewTask:
    task = get_review_task(db, task_id)
    previous_status = task.status
    task.status = ReviewTaskStatus.DISMISSED.value

    db.add(task)
    db.flush()
    audit_events_service.create_audit_event(
        db=db,
        event_in=AuditEventCreateInternal(
            event_type=AuditEventType.REVIEW_TASK_DISMISSED,
            actor_type=AuditActorType.HUMAN,
            actor_id=None,
            document_id=task.document_id,
            review_task_id=task.id,
            source=AuditEventSource.MANUAL,
            status=AuditEventStatus.SUCCESS,
            summary=f"Review task {task.id} dismissed.",
            metadata={
                "previous_status": previous_status,
                "new_status": task.status,
            },
        ),
        commit=False,
    )

    db.commit()
    db.refresh(task)

    return task


def _get_document_or_raise(db: Session, document_id: int) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise ReviewTaskError("Document not found.", status_code=404)

    return document


def _validate_chunk_reference(
    db: Session,
    document_id: int,
    chunk_id: int | None,
) -> None:
    if chunk_id is None:
        return

    chunk = db.get(DocumentChunk, chunk_id)
    if chunk is None:
        raise ReviewTaskError("Chunk not found.", status_code=404)

    if chunk.document_id != document_id:
        raise ReviewTaskError(
            "Chunk does not belong to the provided document.",
            status_code=400,
        )
