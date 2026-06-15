from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from opsguard_api.db import SessionLocal, init_database
from opsguard_api.main import app
from opsguard_api.models import (
    AuditActorType,
    AuditEvent,
    AuditEventSource,
    AuditEventStatus,
    AuditEventType,
    Document,
    DocumentStatus,
)
from opsguard_api.schemas import AuditEventCreateInternal
from opsguard_api.services import audit_events as audit_events_service

TEST_AUDIT_TITLE_PREFIX = "Test Audit Event Document "


def delete_audit_event_data() -> None:
    with SessionLocal() as db:
        db.execute(delete(AuditEvent))
        db.execute(
            delete(Document).where(Document.title.like(f"{TEST_AUDIT_TITLE_PREFIX}%"))
        )
        db.commit()


def create_audit_document() -> int:
    with SessionLocal() as db:
        document = Document(
            title=f"{TEST_AUDIT_TITLE_PREFIX}{uuid4()}",
            source_type="uploaded_file",
            source_path=f"data/raw/test-audit-event-{uuid4()}.txt",
            status=DocumentStatus.UPLOADED.value,
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        return document.id


def create_audit_event(
    *,
    event_type: AuditEventType = AuditEventType.REVIEW_TASK_CREATED,
    document_id: int | None = None,
    status: AuditEventStatus = AuditEventStatus.SUCCESS,
    source: AuditEventSource = AuditEventSource.MANUAL,
    summary: str = "Test audit event.",
) -> int:
    with SessionLocal() as db:
        event = audit_events_service.create_audit_event(
            db=db,
            event_in=AuditEventCreateInternal(
                event_type=event_type,
                actor_type=AuditActorType.HUMAN,
                actor_id=None,
                document_id=document_id,
                review_task_id=None,
                source=source,
                status=status,
                summary=summary,
                metadata={"safe_key": "safe value"},
            ),
        )
        return event.id


@pytest.fixture(autouse=True)
def clean_audit_event_data() -> Iterator[None]:
    init_database()
    delete_audit_event_data()
    yield
    delete_audit_event_data()


def test_create_audit_event_via_service() -> None:
    document_id = create_audit_document()

    with SessionLocal() as db:
        event = audit_events_service.create_audit_event(
            db=db,
            event_in=AuditEventCreateInternal(
                event_type=AuditEventType.REVIEW_TASK_CREATED,
                actor_type=AuditActorType.HUMAN,
                actor_id=None,
                document_id=document_id,
                review_task_id=None,
                source=AuditEventSource.MANUAL,
                status=AuditEventStatus.SUCCESS,
                summary="Manual review task created for test document.",
                metadata={"chunk_id": None, "severity": "medium"},
            ),
        )

    assert event.id > 0
    assert event.document_id == document_id
    assert event.event_type == AuditEventType.REVIEW_TASK_CREATED.value
    assert event.actor_type == AuditActorType.HUMAN.value
    assert event.event_metadata == {"chunk_id": None, "severity": "medium"}


def test_list_audit_events() -> None:
    first_event_id = create_audit_event(summary="First event.")
    second_event_id = create_audit_event(summary="Second event.")

    with TestClient(app) as client:
        response = client.get("/audit-events")

    assert response.status_code == 200
    event_ids = {event["id"] for event in response.json()}
    assert first_event_id in event_ids
    assert second_event_id in event_ids


def test_list_audit_events_filters_by_document_id() -> None:
    first_document_id = create_audit_document()
    second_document_id = create_audit_document()
    first_event_id = create_audit_event(document_id=first_document_id)
    create_audit_event(document_id=second_document_id)

    with TestClient(app) as client:
        response = client.get(
            "/audit-events",
            params={"document_id": first_document_id},
        )

    payload = response.json()

    assert response.status_code == 200
    assert [event["id"] for event in payload] == [first_event_id]


def test_list_audit_events_filters_by_event_type() -> None:
    suggested_event_id = create_audit_event(
        event_type=AuditEventType.AI_REVIEW_TASK_SUGGESTED,
        source=AuditEventSource.AI,
    )
    create_audit_event(event_type=AuditEventType.REVIEW_TASK_CREATED)

    with TestClient(app) as client:
        response = client.get(
            "/audit-events",
            params={"event_type": "ai_review_task_suggested"},
        )

    payload = response.json()

    assert response.status_code == 200
    assert [event["id"] for event in payload] == [suggested_event_id]
    assert payload[0]["event_type"] == "ai_review_task_suggested"


def test_list_audit_events_filters_by_status() -> None:
    rejected_event_id = create_audit_event(
        event_type=AuditEventType.AI_REVIEW_TASK_REJECTED,
        status=AuditEventStatus.REJECTED,
        source=AuditEventSource.AI,
    )
    create_audit_event(status=AuditEventStatus.SUCCESS)

    with TestClient(app) as client:
        response = client.get("/audit-events", params={"status": "rejected"})

    payload = response.json()

    assert response.status_code == 200
    assert [event["id"] for event in payload] == [rejected_event_id]
    assert payload[0]["status"] == "rejected"


def test_get_audit_event_by_id() -> None:
    event_id = create_audit_event(summary="Fetch this event.")

    with TestClient(app) as client:
        response = client.get(f"/audit-events/{event_id}")

    payload = response.json()

    assert response.status_code == 200
    assert payload["id"] == event_id
    assert payload["summary"] == "Fetch this event."
    assert payload["metadata"] == {"safe_key": "safe value"}


def test_audit_event_metadata_drops_embeddings_and_sensitive_values() -> None:
    with SessionLocal() as db:
        event = audit_events_service.create_audit_event(
            db=db,
            event_in=AuditEventCreateInternal(
                event_type=AuditEventType.AI_REVIEW_TASK_REJECTED,
                actor_type=AuditActorType.AI,
                actor_id=None,
                document_id=None,
                review_task_id=None,
                source=AuditEventSource.AI,
                status=AuditEventStatus.REJECTED,
                summary="Rejected unsafe metadata.",
                metadata={
                    "embedding": [0.1, 0.2, 0.3],
                    "system_prompt": "hidden instructions",
                    "api_key": "sk-demo",
                    "validation_error": "OPENAI_API_KEY=demo-secret-token",
                    "safe": {
                        "chunk_ids": [1, 2],
                        "token": "secret-token",
                    },
                },
            ),
        )
        persisted_event = db.scalar(select(AuditEvent).where(AuditEvent.id == event.id))

    assert persisted_event is not None
    assert persisted_event.event_metadata == {
        "validation_error": "OPENAI_API_KEY=[REDACTED_SECRET]",
        "safe": {"chunk_ids": [1, 2]},
    }
