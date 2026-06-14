from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from opsguard_api.config import Settings, get_settings
from opsguard_api.constants import DEFAULT_EMBEDDING_DIMENSIONS
from opsguard_api.db import SessionLocal, init_database
from opsguard_api.dependencies import get_embedding_client
from opsguard_api.main import app
from opsguard_api.models import Document, DocumentChunk, DocumentStatus
from opsguard_api.services.embeddings import EmbeddingProviderError

TEST_SEARCH_TITLE_PREFIX = "Test Search Document "


@dataclass(frozen=True)
class SearchChunkInput:
    content: str
    embedding: list[float] | None
    section_title: str | None = None


class FakeSearchEmbeddingClient:
    model = "fake-search-embedding-model"
    dimensions = DEFAULT_EMBEDDING_DIMENSIONS

    def __init__(
        self,
        embedding: list[float] | None = None,
        fail: bool = False,
    ) -> None:
        self.embedding = embedding or vector(1.0, 0.0)
        self.fail = fail
        self.calls: list[list[str]] = []

    def validate_configuration(self) -> None:
        pass

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        if self.fail:
            raise EmbeddingProviderError("Embedding provider failed.")

        return [self.embedding for _text in texts]


def vector(first: float, second: float = 0.0) -> list[float]:
    return [first, second] + [0.0] * (DEFAULT_EMBEDDING_DIMENSIONS - 2)


def delete_search_documents() -> None:
    with SessionLocal() as db:
        document_ids = list(
            db.scalars(
                select(Document.id).where(
                    Document.title.like(f"{TEST_SEARCH_TITLE_PREFIX}%")
                )
            ).all()
        )
        if document_ids:
            db.execute(delete(Document).where(Document.id.in_(document_ids)))
        db.commit()


def create_search_document(
    chunks: Sequence[SearchChunkInput],
    status: DocumentStatus = DocumentStatus.EMBEDDED,
) -> int:
    with SessionLocal() as db:
        document = Document(
            title=f"{TEST_SEARCH_TITLE_PREFIX}{uuid4()}",
            source_type="uploaded_file",
            source_path=f"data/raw/test-search-{uuid4()}.txt",
            status=status.value,
        )
        db.add(document)
        db.flush()

        for index, chunk in enumerate(chunks):
            db.add(
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=index,
                    content=chunk.content,
                    character_count=len(chunk.content),
                    section_title=chunk.section_title,
                    start_char=None,
                    end_char=None,
                    embedding=chunk.embedding,
                )
            )

        db.commit()
        db.refresh(document)
        return document.id


@pytest.fixture(autouse=True)
def clean_search_data() -> Iterator[None]:
    init_database()
    app.dependency_overrides.pop(get_embedding_client, None)
    app.dependency_overrides.pop(get_settings, None)
    delete_search_documents()
    yield
    app.dependency_overrides.pop(get_embedding_client, None)
    app.dependency_overrides.pop(get_settings, None)
    delete_search_documents()


@pytest.fixture
def search_settings() -> Settings:
    settings = Settings(
        database_url=get_settings().database_url,
        embedding_dimensions=DEFAULT_EMBEDDING_DIMENSIONS,
        default_search_top_k=5,
        max_search_top_k=20,
        max_search_query_chars=1000,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    return settings


def test_search_rejects_blank_query(search_settings: Settings) -> None:
    fake_client = FakeSearchEmbeddingClient()
    app.dependency_overrides[get_embedding_client] = lambda: fake_client

    with TestClient(app) as client:
        response = client.post("/search", json={"query": "   "})

    assert search_settings.default_search_top_k == 5
    assert response.status_code == 422
    assert fake_client.calls == []


def test_search_rejects_invalid_top_k(search_settings: Settings) -> None:
    fake_client = FakeSearchEmbeddingClient()
    app.dependency_overrides[get_embedding_client] = lambda: fake_client

    with TestClient(app) as client:
        response = client.post("/search", json={"query": "incident", "top_k": 0})

    assert search_settings.max_search_top_k == 20
    assert response.status_code == 422
    assert fake_client.calls == []


def test_search_rejects_top_k_above_configured_max() -> None:
    settings = Settings(
        database_url=get_settings().database_url,
        embedding_dimensions=DEFAULT_EMBEDDING_DIMENSIONS,
        default_search_top_k=1,
        max_search_top_k=2,
        max_search_query_chars=1000,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    fake_client = FakeSearchEmbeddingClient()
    app.dependency_overrides[get_embedding_client] = lambda: fake_client

    with TestClient(app) as client:
        response = client.post("/search", json={"query": "incident", "top_k": 3})

    assert response.status_code == 400
    assert response.json()["detail"] == "top_k must be less than or equal to 2."
    assert fake_client.calls == []


def test_search_rejects_query_above_configured_length() -> None:
    settings = Settings(
        database_url=get_settings().database_url,
        embedding_dimensions=DEFAULT_EMBEDDING_DIMENSIONS,
        default_search_top_k=1,
        max_search_top_k=5,
        max_search_query_chars=10,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    fake_client = FakeSearchEmbeddingClient()
    app.dependency_overrides[get_embedding_client] = lambda: fake_client

    with TestClient(app) as client:
        response = client.post(
            "/search",
            json={"query": "this query is too long"},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Query must be 10 characters or fewer."
    assert fake_client.calls == []


def test_search_without_embedded_chunks_returns_empty_response(
    search_settings: Settings,
) -> None:
    document_id = create_search_document(
        [
            SearchChunkInput(content="Unembedded incident policy.", embedding=None),
        ],
        status=DocumentStatus.CHUNKED,
    )
    fake_client = FakeSearchEmbeddingClient()
    app.dependency_overrides[get_embedding_client] = lambda: fake_client

    with TestClient(app) as client:
        response = client.post(
            "/search",
            json={"query": "incident policy", "document_id": document_id},
        )

    assert search_settings.default_search_top_k == 5
    assert response.status_code == 200
    assert response.json() == {
        "query": "incident policy",
        "top_k": 5,
        "result_count": 0,
        "results": [],
    }
    assert fake_client.calls == []


def test_search_returns_best_embedded_chunks_in_order(
    search_settings: Settings,
) -> None:
    document_id = create_search_document(
        [
            SearchChunkInput(
                content="Close but not exact incident reporting guidance.",
                embedding=vector(0.8, 0.6),
                section_title="Reporting",
            ),
            SearchChunkInput(
                content="Exact incident reporting deadline.",
                embedding=vector(1.0, 0.0),
                section_title="Deadlines",
            ),
            SearchChunkInput(
                content="Unrelated lunch policy.",
                embedding=vector(-1.0, 0.0),
                section_title="Office",
            ),
        ]
    )
    fake_client = FakeSearchEmbeddingClient(embedding=vector(1.0, 0.0))
    app.dependency_overrides[get_embedding_client] = lambda: fake_client

    with TestClient(app) as client:
        response = client.post(
            "/search",
            json={"query": "incident reporting deadline", "top_k": 2},
        )

    payload = response.json()
    results = payload["results"]

    assert search_settings.embedding_dimensions == DEFAULT_EMBEDDING_DIMENSIONS
    assert response.status_code == 200
    assert payload["query"] == "incident reporting deadline"
    assert payload["top_k"] == 2
    assert payload["result_count"] == 2
    assert [result["content"] for result in results] == [
        "Exact incident reporting deadline.",
        "Close but not exact incident reporting guidance.",
    ]
    assert [result["document_id"] for result in results] == [
        document_id,
        document_id,
    ]
    assert results[0]["similarity_score"] > results[1]["similarity_score"]
    assert results[0]["chunk_id"] > 0
    assert results[0]["chunk_index"] == 1
    assert results[0]["section_title"] == "Deadlines"
    assert fake_client.calls == [["incident reporting deadline"]]


def test_search_filters_by_document_id(search_settings: Settings) -> None:
    first_document_id = create_search_document(
        [
            SearchChunkInput(
                content="Incident reporting deadline in selected document.",
                embedding=vector(0.8, 0.6),
            ),
        ]
    )
    second_document_id = create_search_document(
        [
            SearchChunkInput(
                content="Incident reporting deadline in other document.",
                embedding=vector(1.0, 0.0),
            ),
        ]
    )
    fake_client = FakeSearchEmbeddingClient(embedding=vector(1.0, 0.0))
    app.dependency_overrides[get_embedding_client] = lambda: fake_client

    with TestClient(app) as client:
        response = client.post(
            "/search",
            json={
                "query": "incident reporting deadline",
                "document_id": first_document_id,
                "top_k": 5,
            },
        )

    results = response.json()["results"]

    assert search_settings.default_search_top_k == 5
    assert second_document_id != first_document_id
    assert response.status_code == 200
    assert len(results) == 1
    assert results[0]["document_id"] == first_document_id
    assert results[0]["content"] == "Incident reporting deadline in selected document."


def test_search_without_document_id_can_return_multiple_documents(
    search_settings: Settings,
) -> None:
    first_document_id = create_search_document(
        [
            SearchChunkInput(
                content="Incident reporting deadline in first document.",
                embedding=vector(1.0, 0.0),
            ),
        ]
    )
    second_document_id = create_search_document(
        [
            SearchChunkInput(
                content="Incident reporting deadline in second document.",
                embedding=vector(0.8, 0.6),
            ),
        ]
    )
    fake_client = FakeSearchEmbeddingClient(embedding=vector(1.0, 0.0))
    app.dependency_overrides[get_embedding_client] = lambda: fake_client

    with TestClient(app) as client:
        response = client.post(
            "/search",
            json={"query": "incident reporting deadline", "top_k": 2},
        )

    document_ids = {result["document_id"] for result in response.json()["results"]}

    assert search_settings.max_search_top_k == 20
    assert response.status_code == 200
    assert document_ids == {first_document_id, second_document_id}


def test_search_ignores_chunks_without_embeddings(search_settings: Settings) -> None:
    create_search_document(
        [
            SearchChunkInput(
                content="Embedded incident reporting deadline.",
                embedding=vector(1.0, 0.0),
            ),
            SearchChunkInput(
                content="Missing vector should not be returned.",
                embedding=None,
            ),
        ]
    )
    fake_client = FakeSearchEmbeddingClient(embedding=vector(1.0, 0.0))
    app.dependency_overrides[get_embedding_client] = lambda: fake_client

    with TestClient(app) as client:
        response = client.post(
            "/search",
            json={"query": "incident reporting deadline", "top_k": 5},
        )

    results = response.json()["results"]

    assert search_settings.default_search_top_k == 5
    assert response.status_code == 200
    assert len(results) == 1
    assert results[0]["content"] == "Embedded incident reporting deadline."


def test_search_response_does_not_expose_vectors(search_settings: Settings) -> None:
    create_search_document(
        [
            SearchChunkInput(
                content="Incident reporting deadline.",
                embedding=vector(1.0, 0.0),
            ),
        ]
    )
    fake_client = FakeSearchEmbeddingClient(embedding=vector(1.0, 0.0))
    app.dependency_overrides[get_embedding_client] = lambda: fake_client

    with TestClient(app) as client:
        response = client.post(
            "/search",
            json={"query": "incident reporting deadline"},
        )

    payload = response.json()
    result = payload["results"][0]

    assert search_settings.default_search_top_k == 5
    assert response.status_code == 200
    assert "embedding" not in payload
    assert "embedding" not in result
    assert set(result) == {
        "document_id",
        "document_title",
        "chunk_id",
        "chunk_index",
        "section_title",
        "content",
        "similarity_score",
    }


def test_search_provider_error_returns_clean_error(search_settings: Settings) -> None:
    create_search_document(
        [
            SearchChunkInput(
                content="Incident reporting deadline.",
                embedding=vector(1.0, 0.0),
            ),
        ]
    )
    fake_client = FakeSearchEmbeddingClient(fail=True)
    app.dependency_overrides[get_embedding_client] = lambda: fake_client

    with TestClient(app) as client:
        response = client.post(
            "/search",
            json={"query": "incident reporting deadline"},
        )

    assert search_settings.default_search_top_k == 5
    assert response.status_code == 502
    assert response.json()["detail"] == "Embedding provider failed."
    assert fake_client.calls == [["incident reporting deadline"]]
