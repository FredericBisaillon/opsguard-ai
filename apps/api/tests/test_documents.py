from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from opsguard_api.db import SessionLocal, init_database
from opsguard_api.main import app
from opsguard_api.models import Document

TEST_SOURCE_PREFIX = "data/raw/test-document-"


def delete_test_documents() -> None:
    with SessionLocal() as db:
        db.execute(
            delete(Document).where(Document.source_path.like(f"{TEST_SOURCE_PREFIX}%"))
        )
        db.commit()


@pytest.fixture(autouse=True)
def clean_test_documents() -> Iterator[None]:
    init_database()
    delete_test_documents()
    yield
    delete_test_documents()


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
