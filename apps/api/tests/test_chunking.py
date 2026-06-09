from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from opsguard_api.config import Settings, get_settings
from opsguard_api.db import SessionLocal, init_database
from opsguard_api.main import app
from opsguard_api.models import Document, DocumentChunk, DocumentStatus
from opsguard_api.services.chunking import chunk_text

TEST_CHUNK_TITLE_PREFIX = "Test Chunk Document "


def delete_test_chunk_documents() -> None:
    with SessionLocal() as db:
        document_ids = list(
            db.scalars(
                select(Document.id).where(
                    Document.title.like(f"{TEST_CHUNK_TITLE_PREFIX}%")
                )
            ).all()
        )
        if document_ids:
            db.execute(
                delete(DocumentChunk).where(
                    DocumentChunk.document_id.in_(document_ids)
                )
            )
            db.execute(delete(Document).where(Document.id.in_(document_ids)))
        db.commit()


def create_document_with_extracted_text(
    client: TestClient,
    settings: Settings,
    extracted_text: str | None,
    status: DocumentStatus = DocumentStatus.TEXT_EXTRACTED,
) -> int:
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.extracted_text_dir.mkdir(parents=True, exist_ok=True)

    source_path = settings.upload_dir.resolve() / f"{uuid4()}.txt"
    source_path.write_text("source text placeholder", encoding="utf-8")

    response = client.post(
        "/documents",
        json={
            "title": f"{TEST_CHUNK_TITLE_PREFIX}{uuid4()}",
            "source_type": "uploaded_file",
            "source_path": source_path.as_posix(),
        },
    )
    assert response.status_code == 201
    document_id = int(response.json()["id"])

    if extracted_text is not None:
        extracted_text_path = settings.extracted_text_dir.resolve()
        extracted_text_path = extracted_text_path / f"document-{document_id}.txt"
        extracted_text_path.write_text(extracted_text, encoding="utf-8")

    with SessionLocal() as db:
        document = db.get(Document, document_id)
        assert document is not None
        document.status = status.value
        db.add(document)
        db.commit()

    return document_id


def document_status(document_id: int) -> str:
    with SessionLocal() as db:
        document = db.get(Document, document_id)
        assert document is not None
        return document.status


@pytest.fixture(autouse=True)
def clean_test_chunk_data() -> Iterator[None]:
    init_database()
    delete_test_chunk_documents()
    yield
    delete_test_chunk_documents()


@pytest.fixture
def chunk_settings(tmp_path: Path) -> Iterator[Settings]:
    settings = Settings(
        database_url=get_settings().database_url,
        upload_dir=tmp_path / "uploads",
        extracted_text_dir=tmp_path / "extracted",
        max_upload_size_mb=10,
        chunk_max_chars=180,
        chunk_overlap_chars=30,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    yield settings
    app.dependency_overrides.pop(get_settings, None)


def test_chunk_text_handles_short_text() -> None:
    chunks = chunk_text(
        text="Access reviews happen quarterly.",
        max_chars=1200,
        overlap_chars=150,
    )

    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].content == "Access reviews happen quarterly."
    assert chunks[0].character_count == len(chunks[0].content)
    assert chunks[0].section_title is None


def test_chunk_text_keeps_markdown_section_titles() -> None:
    chunks = chunk_text(
        text=(
            "# Security Policy\n\n"
            "Access is reviewed quarterly.\n\n"
            "## Incident Response\n\n"
            "Containment starts within one hour."
        ),
        max_chars=120,
        overlap_chars=20,
    )

    assert [chunk.section_title for chunk in chunks] == [
        "Security Policy",
        "Incident Response",
    ]
    assert chunks[0].content.startswith("Section: Security Policy")
    assert chunks[1].content.startswith("Section: Incident Response")


def test_chunk_text_splits_long_text_without_excessive_size() -> None:
    text = " ".join(f"Sentence {index} keeps useful context." for index in range(40))

    chunks = chunk_text(text=text, max_chars=140, overlap_chars=20)

    assert len(chunks) > 1
    assert all(chunk.character_count <= 140 for chunk in chunks)
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))


def test_chunk_endpoint_creates_chunks_and_updates_document_status(
    chunk_settings: Settings,
) -> None:
    text = (
        "# Security Policy\n\n"
        "Access reviews happen quarterly. "
        "Privileged access is approved by security.\n\n"
        "## Incident Response\n\n"
        "Containment begins quickly. Evidence is preserved for audit review."
    )

    with TestClient(app) as client:
        document_id = create_document_with_extracted_text(client, chunk_settings, text)
        response = client.post(f"/documents/{document_id}/chunk")
        chunks_response = client.get(f"/documents/{document_id}/chunks")

    assert response.status_code == 200
    payload = response.json()
    assert payload["document_id"] == document_id
    assert payload["status"] == DocumentStatus.CHUNKED.value
    assert payload["chunk_count"] >= 2
    assert payload["chunk_max_chars"] == chunk_settings.chunk_max_chars
    assert payload["chunk_overlap_chars"] == chunk_settings.chunk_overlap_chars
    assert payload["message"] == "Document chunked successfully."
    assert document_status(document_id) == DocumentStatus.CHUNKED.value

    assert chunks_response.status_code == 200
    chunks = chunks_response.json()
    assert len(chunks) == payload["chunk_count"]
    assert {chunk["document_id"] for chunk in chunks} == {document_id}
    assert [chunk["chunk_index"] for chunk in chunks] == list(range(len(chunks)))
    assert any(chunk["section_title"] == "Incident Response" for chunk in chunks)


def test_chunk_endpoint_is_idempotent(chunk_settings: Settings) -> None:
    text = "# Operations\n\n" + " ".join(
        f"Operational control {index} is reviewed." for index in range(25)
    )

    with TestClient(app) as client:
        document_id = create_document_with_extracted_text(client, chunk_settings, text)
        first_response = client.post(f"/documents/{document_id}/chunk")
        first_chunks = client.get(f"/documents/{document_id}/chunks").json()

        second_response = client.post(f"/documents/{document_id}/chunk")
        second_chunks = client.get(f"/documents/{document_id}/chunks").json()

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["chunk_count"] == second_response.json()["chunk_count"]
    assert len(first_chunks) == len(second_chunks)
    assert [chunk["chunk_index"] for chunk in second_chunks] == list(
        range(len(second_chunks))
    )


def test_chunk_endpoint_returns_404_for_missing_document() -> None:
    with TestClient(app) as client:
        response = client.post("/documents/999999999/chunk")

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found."


def test_chunk_endpoint_rejects_document_without_extracted_text(
    chunk_settings: Settings,
) -> None:
    with TestClient(app) as client:
        document_id = create_document_with_extracted_text(
            client=client,
            settings=chunk_settings,
            extracted_text=None,
            status=DocumentStatus.UPLOADED,
        )
        response = client.post(f"/documents/{document_id}/chunk")

    assert response.status_code == 409
    assert (
        response.json()["detail"]
        == "Document text must be extracted before chunking."
    )
    assert document_status(document_id) == DocumentStatus.UPLOADED.value


def test_chunk_endpoint_returns_404_when_extracted_text_file_is_missing(
    chunk_settings: Settings,
) -> None:
    with TestClient(app) as client:
        document_id = create_document_with_extracted_text(
            client=client,
            settings=chunk_settings,
            extracted_text=None,
        )
        response = client.post(f"/documents/{document_id}/chunk")

    assert response.status_code == 404
    assert response.json()["detail"] == "Extracted text file not found."
    assert document_status(document_id) == DocumentStatus.CHUNKING_FAILED.value


def test_chunk_endpoint_rejects_empty_extracted_text(
    chunk_settings: Settings,
) -> None:
    with TestClient(app) as client:
        document_id = create_document_with_extracted_text(
            client=client,
            settings=chunk_settings,
            extracted_text=" \n\n ",
        )
        response = client.post(f"/documents/{document_id}/chunk")

    assert response.status_code == 400
    assert response.json()["detail"] == "Extracted text is empty."
    assert document_status(document_id) == DocumentStatus.CHUNKING_FAILED.value
