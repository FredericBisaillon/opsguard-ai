from collections.abc import Iterator
from pathlib import Path
from typing import TypedDict, cast
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, or_

from opsguard_api.config import Settings, get_settings
from opsguard_api.db import SessionLocal, init_database
from opsguard_api.main import app
from opsguard_api.models import Document, DocumentStatus

TEST_SOURCE_PREFIX = "data/raw/test-document-"
TEST_UPLOAD_TITLE_PREFIX = "Test Uploaded Document "


class ExtractionResponse(TypedDict):
    document_id: int
    status: str
    extracted_text_path: str
    character_count: int
    message: str


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


def document_status(document_id: int) -> str:
    with SessionLocal() as db:
        document = db.get(Document, document_id)
        assert document is not None
        return document.status


def create_document_for_source_path(
    client: TestClient,
    source_path: Path,
    source_type: str = "uploaded_file",
) -> int:
    response = client.post(
        "/documents",
        json={
            "title": f"{TEST_UPLOAD_TITLE_PREFIX}{uuid4()}",
            "source_type": source_type,
            "source_path": source_path.as_posix(),
        },
    )
    assert response.status_code == 201
    return int(response.json()["id"])


def extract_uploaded_file(
    client: TestClient,
    filename: str,
    file_bytes: bytes,
    content_type: str,
) -> ExtractionResponse:
    upload_response = client.post(
        "/documents/upload",
        data={"title": f"{TEST_UPLOAD_TITLE_PREFIX}{uuid4()}"},
        files={"file": (filename, file_bytes, content_type)},
    )
    assert upload_response.status_code == 201
    uploaded_document = cast(dict[str, object], upload_response.json())
    document_id = uploaded_document["id"]
    assert isinstance(document_id, int)

    extraction_response = client.post(
        f"/documents/{document_id}/extract-text"
    )
    assert extraction_response.status_code == 200
    return cast(ExtractionResponse, extraction_response.json())


def tiny_pdf_with_text(text: str) -> bytes:
    escaped_text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    content_stream = f"BT /F1 24 Tf 72 720 Td ({escaped_text}) Tj ET".encode()
    content_object = (
        b"<< /Length "
        + str(len(content_stream)).encode()
        + b" >>\nstream\n"
        + content_stream
        + b"\nendstream"
    )
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        content_object,
    ]

    pdf = b"%PDF-1.4\n"
    offsets = []
    for object_number, pdf_object in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += f"{object_number} 0 obj\n".encode()
        pdf += pdf_object + b"\nendobj\n"

    xref_offset = len(pdf)
    pdf += b"xref\n0 6\n0000000000 65535 f \n"
    for offset in offsets:
        pdf += f"{offset:010d} 00000 n \n".encode()
    pdf += (
        b"trailer\n<< /Root 1 0 R /Size 6 >>\nstartxref\n"
        + str(xref_offset).encode()
        + b"\n%%EOF\n"
    )
    return pdf


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
        extracted_text_dir=tmp_path / "extracted",
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
        extracted_text_dir=tmp_path / "extracted",
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
                    "notes.docx",
                    b"plain text",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )

    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "Only PDF, Markdown, and plain text files are supported."
    )
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


def test_extract_markdown_file_saves_text_and_updates_document(
    upload_settings: Settings,
) -> None:
    markdown_text = "# Security policy\n\nAll access is reviewed quarterly.\n"

    with TestClient(app) as client:
        extraction = extract_uploaded_file(
            client=client,
            filename="security-policy.md",
            file_bytes=markdown_text.encode(),
            content_type="text/markdown",
        )

    extracted_path = Path(str(extraction["extracted_text_path"]))

    assert extraction["document_id"] > 0
    assert extraction["status"] == DocumentStatus.TEXT_EXTRACTED.value
    assert extraction["character_count"] == len(markdown_text)
    assert extraction["message"] == "Text extracted successfully."
    assert extracted_path.parent == upload_settings.extracted_text_dir.resolve()
    assert extracted_path.read_text(encoding="utf-8") == markdown_text
    assert document_status(int(extraction["document_id"])) == "text_extracted"


def test_extract_plain_text_file_saves_text(
    upload_settings: Settings,
) -> None:
    text = "Incident response notes\nContainment owner: platform team\n"

    with TestClient(app) as client:
        extraction = extract_uploaded_file(
            client=client,
            filename="incident-notes.txt",
            file_bytes=text.encode(),
            content_type="text/plain",
        )

    extracted_path = Path(str(extraction["extracted_text_path"]))

    assert extraction["status"] == "text_extracted"
    assert extraction["character_count"] == len(text)
    assert extracted_path.read_text(encoding="utf-8") == text


def test_extract_pdf_file_saves_extractable_text(
    upload_settings: Settings,
) -> None:
    pdf_text = "Hello PDF text"

    with TestClient(app) as client:
        extraction = extract_uploaded_file(
            client=client,
            filename="incident-guide.pdf",
            file_bytes=tiny_pdf_with_text(pdf_text),
            content_type="application/pdf",
        )

    extracted_path = Path(str(extraction["extracted_text_path"]))

    assert extraction["status"] == "text_extracted"
    assert pdf_text in extracted_path.read_text(encoding="utf-8")


def test_extract_pdf_without_text_fails_cleanly(
    upload_settings: Settings,
) -> None:
    with TestClient(app) as client:
        upload_response = client.post(
            "/documents/upload",
            data={"title": f"{TEST_UPLOAD_TITLE_PREFIX}{uuid4()}"},
            files={
                "file": (
                    "image-only.pdf",
                    tiny_pdf_with_text(""),
                    "application/pdf",
                )
            },
        )
        assert upload_response.status_code == 201
        document_id = int(upload_response.json()["id"])

        response = client.post(f"/documents/{document_id}/extract-text")

    assert response.status_code == 400
    assert response.json()["detail"] == "PDF does not contain extractable text."
    assert document_status(document_id) == "extraction_failed"


def test_extract_document_returns_404_for_missing_document() -> None:
    with TestClient(app) as client:
        response = client.post("/documents/999999999/extract-text")

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found."


def test_extract_document_returns_404_when_source_file_is_missing(
    upload_settings: Settings,
) -> None:
    missing_source_path = upload_settings.upload_dir.resolve() / f"{uuid4()}.md"

    with TestClient(app) as client:
        document_id = create_document_for_source_path(client, missing_source_path)
        response = client.post(f"/documents/{document_id}/extract-text")

    assert response.status_code == 404
    assert response.json()["detail"] == "Source file not found."
    assert document_status(document_id) == "extraction_failed"


def test_extract_document_rejects_source_path_outside_upload_dir(
    upload_settings: Settings,
) -> None:
    outside_source_path = upload_settings.upload_dir.resolve().parent / f"{uuid4()}.md"
    outside_source_path.write_text("# Outside upload dir\n", encoding="utf-8")

    with TestClient(app) as client:
        document_id = create_document_for_source_path(client, outside_source_path)
        response = client.post(f"/documents/{document_id}/extract-text")

    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "Document source path is outside the configured upload directory."
    )
    assert document_status(document_id) == "extraction_failed"


def test_extract_document_rejects_unsupported_source_type(
    upload_settings: Settings,
) -> None:
    unsupported_source_path = upload_settings.upload_dir.resolve() / f"{uuid4()}.docx"
    unsupported_source_path.write_bytes(b"docx bytes")

    with TestClient(app) as client:
        document_id = create_document_for_source_path(client, unsupported_source_path)
        response = client.post(f"/documents/{document_id}/extract-text")

    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "Document type is not supported for text extraction."
    )
    assert document_status(document_id) == "extraction_failed"


def test_extract_document_rejects_empty_text(
    upload_settings: Settings,
) -> None:
    empty_source_path = upload_settings.upload_dir.resolve() / f"{uuid4()}.txt"
    empty_source_path.write_text("", encoding="utf-8")

    with TestClient(app) as client:
        document_id = create_document_for_source_path(client, empty_source_path)
        response = client.post(f"/documents/{document_id}/extract-text")

    assert response.status_code == 400
    assert response.json()["detail"] == "File does not contain extractable text."
    assert document_status(document_id) == "extraction_failed"
