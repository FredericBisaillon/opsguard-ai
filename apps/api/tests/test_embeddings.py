from collections.abc import Iterator, Sequence
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from opsguard_api.config import Settings, get_settings
from opsguard_api.constants import DEFAULT_EMBEDDING_DIMENSIONS
from opsguard_api.db import SessionLocal, init_database
from opsguard_api.main import app
from opsguard_api.models import Document, DocumentChunk, DocumentStatus
from opsguard_api.routes.documents import get_embedding_client
from opsguard_api.services.embeddings import EmbeddingProviderError

TEST_EMBED_TITLE_PREFIX = "Test Embed Document "


class FakeEmbeddingClient:
    model = "fake-embedding-model"
    dimensions = DEFAULT_EMBEDDING_DIMENSIONS

    def __init__(self, value: float = 1.0, fail: bool = False) -> None:
        self.value = value
        self.fail = fail
        self.calls: list[list[str]] = []

    def validate_configuration(self) -> None:
        pass

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        if self.fail:
            raise EmbeddingProviderError("Embedding provider failed.")

        return [[self.value] * self.dimensions for _text in texts]


def delete_test_embedding_documents() -> None:
    with SessionLocal() as db:
        document_ids = list(
            db.scalars(
                select(Document.id).where(
                    Document.title.like(f"{TEST_EMBED_TITLE_PREFIX}%")
                )
            ).all()
        )
        if document_ids:
            db.execute(delete(Document).where(Document.id.in_(document_ids)))
        db.commit()


def create_document_with_chunks(
    *,
    status: DocumentStatus = DocumentStatus.CHUNKED,
    chunk_count: int = 2,
) -> int:
    with SessionLocal() as db:
        document = Document(
            title=f"{TEST_EMBED_TITLE_PREFIX}{uuid4()}",
            source_type="uploaded_file",
            source_path=f"data/raw/test-embed-{uuid4()}.txt",
            status=status.value,
        )
        db.add(document)
        db.flush()

        for index in range(chunk_count):
            db.add(
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=index,
                    content=f"Chunk {index} content for embedding.",
                    character_count=len(f"Chunk {index} content for embedding."),
                    section_title=None,
                    start_char=None,
                    end_char=None,
                )
            )

        db.commit()
        db.refresh(document)
        return document.id


def document_status(document_id: int) -> str:
    with SessionLocal() as db:
        document = db.get(Document, document_id)
        assert document is not None
        return document.status


def document_chunks(document_id: int) -> list[DocumentChunk]:
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == document_id)
                .order_by(DocumentChunk.chunk_index)
            ).all()
        )


def embedding_length(chunk: DocumentChunk) -> int:
    assert chunk.embedding is not None
    return len(chunk.embedding)


def embedding_first_value(chunk: DocumentChunk) -> float:
    assert chunk.embedding is not None
    return float(chunk.embedding[0])


@pytest.fixture(autouse=True)
def clean_embedding_data() -> Iterator[None]:
    init_database()
    app.dependency_overrides.pop(get_embedding_client, None)
    app.dependency_overrides.pop(get_settings, None)
    delete_test_embedding_documents()
    yield
    app.dependency_overrides.pop(get_embedding_client, None)
    app.dependency_overrides.pop(get_settings, None)
    delete_test_embedding_documents()


@pytest.fixture
def embedding_settings() -> Settings:
    settings = Settings(
        database_url=get_settings().database_url,
        embedding_dimensions=DEFAULT_EMBEDDING_DIMENSIONS,
        embedding_batch_size=2,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    return settings


def test_embed_returns_404_for_missing_document(
    embedding_settings: Settings,
) -> None:
    fake_client = FakeEmbeddingClient()
    app.dependency_overrides[get_embedding_client] = lambda: fake_client

    with TestClient(app) as client:
        response = client.post("/documents/999999999/embed")

    assert embedding_settings.embedding_dimensions == DEFAULT_EMBEDDING_DIMENSIONS
    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found."
    assert fake_client.calls == []


def test_embed_rejects_document_that_is_not_chunked(
    embedding_settings: Settings,
) -> None:
    document_id = create_document_with_chunks(
        status=DocumentStatus.TEXT_EXTRACTED,
        chunk_count=1,
    )
    fake_client = FakeEmbeddingClient()
    app.dependency_overrides[get_embedding_client] = lambda: fake_client

    with TestClient(app) as client:
        response = client.post(f"/documents/{document_id}/embed")

    assert embedding_settings.embedding_dimensions == DEFAULT_EMBEDDING_DIMENSIONS
    assert response.status_code == 409
    assert response.json()["detail"] == "Document must be chunked before embedding."
    assert document_status(document_id) == DocumentStatus.TEXT_EXTRACTED.value
    assert fake_client.calls == []


def test_embed_rejects_chunked_document_without_chunks(
    embedding_settings: Settings,
) -> None:
    document_id = create_document_with_chunks(chunk_count=0)
    fake_client = FakeEmbeddingClient()
    app.dependency_overrides[get_embedding_client] = lambda: fake_client

    with TestClient(app) as client:
        response = client.post(f"/documents/{document_id}/embed")

    assert embedding_settings.embedding_dimensions == DEFAULT_EMBEDDING_DIMENSIONS
    assert response.status_code == 409
    assert response.json()["detail"] == "Document has no chunks to embed."
    assert document_status(document_id) == DocumentStatus.CHUNKED.value
    assert fake_client.calls == []


def test_embed_success_stores_vectors_and_updates_document_status(
    embedding_settings: Settings,
) -> None:
    document_id = create_document_with_chunks(chunk_count=3)
    fake_client = FakeEmbeddingClient(value=3.5)
    app.dependency_overrides[get_embedding_client] = lambda: fake_client

    with TestClient(app) as client:
        response = client.post(f"/documents/{document_id}/embed")

    payload = response.json()
    chunks = document_chunks(document_id)

    assert embedding_settings.embedding_batch_size == 2
    assert response.status_code == 200
    assert payload == {
        "document_id": document_id,
        "status": DocumentStatus.EMBEDDED.value,
        "embedding_model": fake_client.model,
        "embedding_dimensions": DEFAULT_EMBEDDING_DIMENSIONS,
        "embedded_chunk_count": 3,
        "message": "Document chunks embedded successfully.",
    }
    assert document_status(document_id) == DocumentStatus.EMBEDDED.value
    assert len(chunks) == 3
    assert all(chunk.embedding is not None for chunk in chunks)
    assert all(
        embedding_length(chunk) == DEFAULT_EMBEDDING_DIMENSIONS for chunk in chunks
    )
    assert all(embedding_first_value(chunk) == 3.5 for chunk in chunks)
    assert [len(call) for call in fake_client.calls] == [2, 1]


def test_embed_is_idempotent_and_replaces_existing_embeddings(
    embedding_settings: Settings,
) -> None:
    document_id = create_document_with_chunks(chunk_count=2)

    first_client = FakeEmbeddingClient(value=1.0)
    app.dependency_overrides[get_embedding_client] = lambda: first_client
    with TestClient(app) as client:
        first_response = client.post(f"/documents/{document_id}/embed")

    first_chunks = document_chunks(document_id)
    first_chunk_ids = [chunk.id for chunk in first_chunks]
    assert first_response.status_code == 200
    assert [embedding_first_value(chunk) for chunk in first_chunks] == [1.0, 1.0]

    second_client = FakeEmbeddingClient(value=2.0)
    app.dependency_overrides[get_embedding_client] = lambda: second_client
    with TestClient(app) as client:
        second_response = client.post(f"/documents/{document_id}/embed")

    second_chunks = document_chunks(document_id)

    assert embedding_settings.embedding_dimensions == DEFAULT_EMBEDDING_DIMENSIONS
    assert second_response.status_code == 200
    assert second_response.json()["embedded_chunk_count"] == 2
    assert [chunk.id for chunk in second_chunks] == first_chunk_ids
    assert [embedding_first_value(chunk) for chunk in second_chunks] == [
        2.0,
        2.0,
    ]
    assert len(second_chunks) == 2


def test_embed_provider_error_marks_document_failed(
    embedding_settings: Settings,
) -> None:
    document_id = create_document_with_chunks(chunk_count=1)
    fake_client = FakeEmbeddingClient(fail=True)
    app.dependency_overrides[get_embedding_client] = lambda: fake_client

    with TestClient(app) as client:
        response = client.post(f"/documents/{document_id}/embed")

    assert embedding_settings.embedding_dimensions == DEFAULT_EMBEDDING_DIMENSIONS
    assert response.status_code == 502
    assert response.json()["detail"] == "Embedding provider failed."
    assert document_status(document_id) == DocumentStatus.EMBEDDING_FAILED.value
    assert document_chunks(document_id)[0].embedding is None


def test_embed_response_does_not_expose_vectors(
    embedding_settings: Settings,
) -> None:
    document_id = create_document_with_chunks(chunk_count=1)
    fake_client = FakeEmbeddingClient()
    app.dependency_overrides[get_embedding_client] = lambda: fake_client

    with TestClient(app) as client:
        response = client.post(f"/documents/{document_id}/embed")

    payload = response.json()

    assert embedding_settings.embedding_dimensions == DEFAULT_EMBEDDING_DIMENSIONS
    assert response.status_code == 200
    assert set(payload) == {
        "document_id",
        "status",
        "embedding_model",
        "embedding_dimensions",
        "embedded_chunk_count",
        "message",
    }
    assert all(not isinstance(value, list) for value in payload.values())


def test_embed_returns_clean_error_when_openai_api_key_is_missing() -> None:
    settings = Settings(
        database_url=get_settings().database_url,
        openai_api_key=None,
        embedding_dimensions=DEFAULT_EMBEDDING_DIMENSIONS,
        embedding_batch_size=2,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    document_id = create_document_with_chunks(chunk_count=1)

    with TestClient(app) as client:
        response = client.post(f"/documents/{document_id}/embed")

    assert response.status_code == 500
    assert response.json()["detail"] == (
        "OPENAI_API_KEY is required to generate embeddings."
    )
    assert document_status(document_id) == DocumentStatus.CHUNKED.value
