from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from opsguard_api.db import SessionLocal, init_database
from opsguard_api.main import app
from opsguard_api.models import Document, DocumentChunk, DocumentStatus

TEST_REVIEW_TASK_TITLE_PREFIX = "Test Review Task Document "


@dataclass(frozen=True)
class ReviewTaskDocumentData:
    document_id: int
    chunk_ids: list[int]


def delete_review_task_documents() -> None:
    with SessionLocal() as db:
        document_ids = list(
            db.scalars(
                select(Document.id).where(
                    Document.title.like(f"{TEST_REVIEW_TASK_TITLE_PREFIX}%")
                )
            ).all()
        )
        if document_ids:
            db.execute(delete(Document).where(Document.id.in_(document_ids)))
        db.commit()


def create_review_task_document(
    chunk_contents: Sequence[str] = (),
) -> ReviewTaskDocumentData:
    with SessionLocal() as db:
        document = Document(
            title=f"{TEST_REVIEW_TASK_TITLE_PREFIX}{uuid4()}",
            source_type="uploaded_file",
            source_path=f"data/raw/test-review-task-{uuid4()}.txt",
            status=DocumentStatus.CHUNKED.value
            if chunk_contents
            else DocumentStatus.UPLOADED.value,
        )
        db.add(document)
        db.flush()

        chunks: list[DocumentChunk] = []
        for index, content in enumerate(chunk_contents):
            chunk = DocumentChunk(
                document_id=document.id,
                chunk_index=index,
                content=content,
                character_count=len(content),
                section_title=None,
                start_char=None,
                end_char=None,
                embedding=None,
            )
            db.add(chunk)
            chunks.append(chunk)

        db.commit()

        return ReviewTaskDocumentData(
            document_id=document.id,
            chunk_ids=[chunk.id for chunk in chunks],
        )


@pytest.fixture(autouse=True)
def clean_review_task_data() -> Iterator[None]:
    init_database()
    delete_review_task_documents()
    yield
    delete_review_task_documents()


def test_create_review_task_for_document() -> None:
    document = create_review_task_document()

    with TestClient(app) as client:
        response = client.post(
            "/review-tasks",
            json={
                "document_id": document.document_id,
                "title": "Verify incident response section",
                "description": "Check escalation timing.",
                "severity": "high",
            },
        )

    payload = response.json()

    assert response.status_code == 201
    assert payload["id"] > 0
    assert payload["document_id"] == document.document_id
    assert payload["chunk_id"] is None
    assert payload["title"] == "Verify incident response section"
    assert payload["description"] == "Check escalation timing."
    assert payload["severity"] == "high"
    assert payload["status"] == "open"
    assert payload["source"] == "manual"
    assert payload["created_at"]
    assert payload["updated_at"]


def test_create_review_task_for_chunk() -> None:
    document = create_review_task_document(
        ["MFA is required for privileged accounts."]
    )
    chunk_id = document.chunk_ids[0]

    with TestClient(app) as client:
        response = client.post(
            "/review-tasks",
            json={
                "document_id": document.document_id,
                "chunk_id": chunk_id,
                "title": "MFA clause may need evidence",
                "severity": "medium",
            },
        )

    payload = response.json()

    assert response.status_code == 201
    assert payload["document_id"] == document.document_id
    assert payload["chunk_id"] == chunk_id
    assert payload["source"] == "manual"


def test_create_review_task_rejects_missing_document() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/review-tasks",
            json={
                "document_id": 999999,
                "title": "Missing document task",
            },
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found."


def test_create_review_task_rejects_missing_chunk() -> None:
    document = create_review_task_document()

    with TestClient(app) as client:
        response = client.post(
            "/review-tasks",
            json={
                "document_id": document.document_id,
                "chunk_id": 999999,
                "title": "Missing chunk task",
            },
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Chunk not found."


def test_create_review_task_rejects_chunk_from_other_document() -> None:
    first_document = create_review_task_document(["Incident response section."])
    second_document = create_review_task_document(["Access review section."])

    with TestClient(app) as client:
        response = client.post(
            "/review-tasks",
            json={
                "document_id": first_document.document_id,
                "chunk_id": second_document.chunk_ids[0],
                "title": "Cross-document chunk task",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Chunk does not belong to the provided document."
    )


def test_list_review_tasks() -> None:
    document = create_review_task_document()

    with TestClient(app) as client:
        first_response = client.post(
            "/review-tasks",
            json={
                "document_id": document.document_id,
                "title": "First task",
            },
        )
        second_response = client.post(
            "/review-tasks",
            json={
                "document_id": document.document_id,
                "title": "Second task",
                "severity": "critical",
            },
        )
        list_response = client.get("/review-tasks")

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    assert list_response.status_code == 200
    task_ids = {task["id"] for task in list_response.json()}
    assert first_response.json()["id"] in task_ids
    assert second_response.json()["id"] in task_ids


def test_list_review_tasks_filters_by_document_id() -> None:
    first_document = create_review_task_document()
    second_document = create_review_task_document()

    with TestClient(app) as client:
        first_response = client.post(
            "/review-tasks",
            json={
                "document_id": first_document.document_id,
                "title": "First document task",
            },
        )
        client.post(
            "/review-tasks",
            json={
                "document_id": second_document.document_id,
                "title": "Second document task",
            },
        )
        list_response = client.get(
            "/review-tasks",
            params={"document_id": first_document.document_id},
        )

    payload = list_response.json()

    assert first_response.status_code == 201
    assert list_response.status_code == 200
    assert [task["id"] for task in payload] == [first_response.json()["id"]]


def test_list_review_tasks_filters_by_status() -> None:
    document = create_review_task_document()

    with TestClient(app) as client:
        open_response = client.post(
            "/review-tasks",
            json={
                "document_id": document.document_id,
                "title": "Open task",
            },
        )
        client.post(
            "/review-tasks",
            json={
                "document_id": document.document_id,
                "title": "Resolved task",
                "status": "resolved",
            },
        )
        list_response = client.get("/review-tasks", params={"status": "open"})

    payload = list_response.json()

    assert open_response.status_code == 201
    assert list_response.status_code == 200
    assert [task["id"] for task in payload] == [open_response.json()["id"]]


def test_list_review_tasks_filters_by_severity() -> None:
    document = create_review_task_document()

    with TestClient(app) as client:
        high_response = client.post(
            "/review-tasks",
            json={
                "document_id": document.document_id,
                "title": "High task",
                "severity": "high",
            },
        )
        client.post(
            "/review-tasks",
            json={
                "document_id": document.document_id,
                "title": "Low task",
                "severity": "low",
            },
        )
        list_response = client.get("/review-tasks", params={"severity": "high"})

    payload = list_response.json()

    assert high_response.status_code == 201
    assert list_response.status_code == 200
    assert [task["id"] for task in payload] == [high_response.json()["id"]]


def test_get_review_task_by_id() -> None:
    document = create_review_task_document()

    with TestClient(app) as client:
        create_response = client.post(
            "/review-tasks",
            json={
                "document_id": document.document_id,
                "title": "Task to fetch",
            },
        )
        task_id = create_response.json()["id"]
        get_response = client.get(f"/review-tasks/{task_id}")

    assert create_response.status_code == 201
    assert get_response.status_code == 200
    assert get_response.json()["id"] == task_id
    assert get_response.json()["title"] == "Task to fetch"


def test_update_review_task() -> None:
    document = create_review_task_document()

    with TestClient(app) as client:
        create_response = client.post(
            "/review-tasks",
            json={
                "document_id": document.document_id,
                "title": "Task before update",
                "description": "Old description",
                "severity": "low",
            },
        )
        task_id = create_response.json()["id"]
        update_response = client.patch(
            f"/review-tasks/{task_id}",
            json={
                "title": "Task after update",
                "description": "New description",
                "severity": "critical",
                "status": "in_progress",
            },
        )

    payload = update_response.json()

    assert create_response.status_code == 201
    assert update_response.status_code == 200
    assert payload["id"] == task_id
    assert payload["title"] == "Task after update"
    assert payload["description"] == "New description"
    assert payload["severity"] == "critical"
    assert payload["status"] == "in_progress"


def test_dismiss_review_task() -> None:
    document = create_review_task_document()

    with TestClient(app) as client:
        create_response = client.post(
            "/review-tasks",
            json={
                "document_id": document.document_id,
                "title": "Task to dismiss",
            },
        )
        task_id = create_response.json()["id"]
        dismiss_response = client.post(f"/review-tasks/{task_id}/dismiss")

    assert create_response.status_code == 201
    assert dismiss_response.status_code == 200
    assert dismiss_response.json()["id"] == task_id
    assert dismiss_response.json()["status"] == "dismissed"


def test_review_task_source_defaults_to_manual() -> None:
    document = create_review_task_document()

    with TestClient(app) as client:
        response = client.post(
            "/review-tasks",
            json={
                "document_id": document.document_id,
                "title": "Manual source task",
            },
        )

    assert response.status_code == 201
    assert response.json()["source"] == "manual"


def test_review_task_rejects_invalid_severity_and_status() -> None:
    document = create_review_task_document()

    with TestClient(app) as client:
        invalid_severity_response = client.post(
            "/review-tasks",
            json={
                "document_id": document.document_id,
                "title": "Invalid severity task",
                "severity": "urgent",
            },
        )
        invalid_status_response = client.post(
            "/review-tasks",
            json={
                "document_id": document.document_id,
                "title": "Invalid status task",
                "status": "done",
            },
        )

    assert invalid_severity_response.status_code == 422
    assert invalid_status_response.status_code == 422


def test_review_task_rejects_blank_title_and_description() -> None:
    document = create_review_task_document()

    with TestClient(app) as client:
        blank_title_response = client.post(
            "/review-tasks",
            json={
                "document_id": document.document_id,
                "title": "   ",
            },
        )
        blank_description_response = client.post(
            "/review-tasks",
            json={
                "document_id": document.document_id,
                "title": "Blank description task",
                "description": "   ",
            },
        )

    assert blank_title_response.status_code == 422
    assert blank_description_response.status_code == 422
