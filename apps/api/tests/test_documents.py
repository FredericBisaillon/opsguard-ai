from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, or_

from opsguard_api.config import Settings, get_settings
from opsguard_api.db import SessionLocal, init_database
from opsguard_api.main import app
from opsguard_api.models import Document

TEST_SOURCE_PREFIX = "data/raw/test-document-"
TEST_UPLOAD_TITLE_PREFIX = "Test Uploaded Document "


def delete_test_documents() -> None:
    with SessionLocal() as db:
        db.execute(
            delete(Document).where(
                or_(
                    Document.source_path.like(f"{TEST_SOURCE_PREFIX}%"),
                    Document.title.like(f"{TEST_UPLOAD_TITLE_PREFIX}%"),
                )
            )
        )
        db.commit()


@pytest.fixture(autouse=True)
def clean_test_documents() -> Iterator[None]:
    init_database()
    delete_test_documents()
    yield
    delete_test_documents()


@pytest.fixture
def upload_settings(tmp_path: Path) -> Iterator[Settings]:
    settings = Settings(
        database_url=get_settings().database_url,
        upload_dir=tmp_path,
        max_upload_size_mb=10,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    yield settings
    app.dependency_overrides.pop(get_settings, None)


@pytest.fixture
def small_upload_settings(tmp_path: Path) -> Iterator[Settings]:
    settings = Settings(
        database_url=get_settings().database_url,
        upload_dir=tmp_path,
        max_upload_size_mb=1,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    yield settings
    app.dependency_overrides.pop(get_settings, None)


def test_create_and_list_documents() -> None:
    source_path = f"{TEST_SOURCE_PREFIX}{uuid4()}.pdf"
    payload = {
        "title": "NIST Incident Response Guide",
        "source_type": "public_pdf",
        "source_path": source_path,
    }

    with TestClient(app) as client:
        create_response = client.post("/documents", json=payload)

        assert create_response.status_code == 201
        created_document = create_response.json()
        assert created_document["id"] > 0
        assert created_document["title"] == payload["title"]
        assert created_document["source_type"] == payload["source_type"]
        assert created_document["source_path"] == payload["source_path"]
        assert created_document["status"] == "uploaded"
        assert created_document["created_at"]
        assert created_document["updated_at"]

        list_response = client.get("/documents")

        assert list_response.status_code == 200
        documents = list_response.json()
        assert any(
            document["id"] == created_document["id"]
            and document["source_path"] == source_path
            for document in documents
        )


def test_upload_pdf_creates_document_and_saves_file(
    upload_settings: Settings,
) -> None:
    title = f"{TEST_UPLOAD_TITLE_PREFIX}{uuid4()}"
    file_bytes = b"%PDF-1.4\n% test pdf\n"

    with TestClient(app) as client:
        response = client.post(
            "/documents/upload",
            data={"title": title},
            files={
                "file": (
                    "../../incident-response.pdf",
                    file_bytes,
                    "application/pdf",
                )
            },
        )

    assert response.status_code == 201
    created_document = response.json()
    saved_path = Path(created_document["source_path"])

    assert created_document["id"] > 0
    assert created_document["title"] == title
    assert created_document["source_type"] == "uploaded_file"
    assert created_document["status"] == "uploaded"
    assert saved_path.parent == upload_settings.upload_dir.resolve()
    assert saved_path.suffix == ".pdf"
    assert saved_path.name != "incident-response.pdf"
    assert ".." not in saved_path.parts
    assert saved_path.read_bytes() == file_bytes


def test_upload_markdown_uses_original_filename_as_default_title(
    upload_settings: Settings,
) -> None:
    filename = f"{TEST_UPLOAD_TITLE_PREFIX}{uuid4()}.md"

    with TestClient(app) as client:
        response = client.post(
            "/documents/upload",
            files={
                "file": (
                    filename,
                    b"# Security policy\n",
                    "text/markdown",
                )
            },
        )

    assert response.status_code == 201
    created_document = response.json()

    assert created_document["title"] == filename
    assert created_document["source_type"] == "uploaded_file"
    assert Path(created_document["source_path"]).suffix == ".md"


def test_upload_rejects_unsupported_file_type(
    upload_settings: Settings,
) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/documents/upload",
            data={"title": f"{TEST_UPLOAD_TITLE_PREFIX}{uuid4()}"},
            files={
                "file": (
                    "notes.txt",
                    b"plain text",
                    "text/plain",
                )
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Only PDF and Markdown files are supported."
    assert list(upload_settings.upload_dir.iterdir()) == []


def test_upload_rejects_empty_file(
    upload_settings: Settings,
) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/documents/upload",
            data={"title": f"{TEST_UPLOAD_TITLE_PREFIX}{uuid4()}"},
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded file cannot be empty."
    assert list(upload_settings.upload_dir.iterdir()) == []


def test_upload_rejects_file_over_size_limit(
    small_upload_settings: Settings,
) -> None:
    oversized_file = b"a" * (small_upload_settings.max_upload_size_bytes + 1)

    with TestClient(app) as client:
        response = client.post(
            "/documents/upload",
            data={"title": f"{TEST_UPLOAD_TITLE_PREFIX}{uuid4()}"},
            files={"file": ("large.md", oversized_file, "text/markdown")},
        )

    assert response.status_code == 413
    assert response.json()["detail"] == "File exceeds the 1 MB upload limit."
    assert list(small_upload_settings.upload_dir.iterdir()) == []
