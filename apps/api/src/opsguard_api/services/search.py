from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from opsguard_api.config import Settings
from opsguard_api.constants import DEFAULT_EMBEDDING_DIMENSIONS
from opsguard_api.models import Document, DocumentChunk
from opsguard_api.schemas import SemanticSearchRequest
from opsguard_api.services.embeddings import (
    EmbeddingClient,
    EmbeddingClientError,
    EmbeddingConfigurationError,
    EmbeddingProviderError,
)


class SemanticSearchError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class SemanticSearchResultData:
    document_id: int
    document_title: str
    chunk_id: int
    chunk_index: int
    section_title: str | None
    content: str
    similarity_score: float


@dataclass(frozen=True)
class SemanticSearchResponseData:
    query: str
    top_k: int
    result_count: int
    results: list[SemanticSearchResultData]


def semantic_search(
    db: Session,
    search_in: SemanticSearchRequest,
    settings: Settings,
    embedding_client: EmbeddingClient,
) -> SemanticSearchResponseData:
    query = search_in.query.strip()
    top_k = _validated_top_k(search_in.top_k, settings)
    _validate_query(query, settings)
    _validate_embedding_settings(settings, embedding_client)

    if search_in.document_id is not None:
        document = db.get(Document, search_in.document_id)
        if document is None:
            raise SemanticSearchError("Document not found.", status_code=404)

    if not _has_embedded_chunks(db, search_in.document_id):
        return SemanticSearchResponseData(
            query=query,
            top_k=top_k,
            result_count=0,
            results=[],
        )

    query_embedding = _embed_query(query, embedding_client)
    results = _search_embedded_chunks(
        db=db,
        query_embedding=query_embedding,
        document_id=search_in.document_id,
        top_k=top_k,
    )

    return SemanticSearchResponseData(
        query=query,
        top_k=top_k,
        result_count=len(results),
        results=results,
    )


def _validated_top_k(top_k: int | None, settings: Settings) -> int:
    if settings.default_search_top_k > settings.max_search_top_k:
        raise SemanticSearchError(
            "DEFAULT_SEARCH_TOP_K must be less than or equal to MAX_SEARCH_TOP_K.",
            status_code=500,
        )

    resolved_top_k = top_k if top_k is not None else settings.default_search_top_k
    if resolved_top_k > settings.max_search_top_k:
        raise SemanticSearchError(
            f"top_k must be less than or equal to {settings.max_search_top_k}.",
            status_code=400,
        )

    return resolved_top_k


def _validate_query(query: str, settings: Settings) -> None:
    if not query:
        raise SemanticSearchError("Query cannot be empty.")

    if len(query) > settings.max_search_query_chars:
        raise SemanticSearchError(
            f"Query must be {settings.max_search_query_chars} characters or fewer."
        )


def _validate_embedding_settings(
    settings: Settings,
    embedding_client: EmbeddingClient,
) -> None:
    if settings.embedding_dimensions != DEFAULT_EMBEDDING_DIMENSIONS:
        raise SemanticSearchError(
            "EMBEDDING_DIMENSIONS must match the database vector dimension "
            f"({DEFAULT_EMBEDDING_DIMENSIONS}).",
            status_code=500,
        )

    if embedding_client.dimensions != settings.embedding_dimensions:
        raise SemanticSearchError(
            "Embedding client dimensions do not match EMBEDDING_DIMENSIONS.",
            status_code=500,
        )


def _has_embedded_chunks(db: Session, document_id: int | None) -> bool:
    statement = select(DocumentChunk.id).where(DocumentChunk.embedding.is_not(None))
    if document_id is not None:
        statement = statement.where(DocumentChunk.document_id == document_id)

    return db.execute(statement.limit(1)).first() is not None


def _embed_query(
    query: str,
    embedding_client: EmbeddingClient,
) -> list[float]:
    try:
        embedding_client.validate_configuration()
        embeddings = embedding_client.embed_texts([query])
    except EmbeddingConfigurationError as exc:
        raise SemanticSearchError(exc.message, status_code=500) from exc
    except EmbeddingProviderError as exc:
        raise SemanticSearchError(exc.message, status_code=502) from exc
    except EmbeddingClientError as exc:
        raise SemanticSearchError(exc.message, status_code=500) from exc

    if len(embeddings) != 1:
        raise SemanticSearchError(
            "Embedding provider returned an unexpected number of vectors.",
            status_code=502,
        )

    query_embedding = embeddings[0]
    if len(query_embedding) != embedding_client.dimensions:
        raise SemanticSearchError(
            "Embedding provider returned vectors with unexpected dimensions.",
            status_code=502,
        )

    return query_embedding


def _search_embedded_chunks(
    db: Session,
    query_embedding: list[float],
    document_id: int | None,
    top_k: int,
) -> list[SemanticSearchResultData]:
    distance_expression = DocumentChunk.embedding.cosine_distance(  # type: ignore[attr-defined]
        query_embedding
    ).label("distance")

    statement = (
        select(
            DocumentChunk,
            Document.title.label("document_title"),
            distance_expression,
        )
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(DocumentChunk.embedding.is_not(None))
        .order_by(distance_expression, DocumentChunk.id)
        .limit(top_k)
    )
    if document_id is not None:
        statement = statement.where(DocumentChunk.document_id == document_id)

    try:
        rows = db.execute(statement).all()
    except SQLAlchemyError as exc:
        raise SemanticSearchError("Semantic search failed.", status_code=500) from exc

    results: list[SemanticSearchResultData] = []
    for chunk, document_title, distance in rows:
        results.append(
            SemanticSearchResultData(
                document_id=chunk.document_id,
                document_title=document_title,
                chunk_id=chunk.id,
                chunk_index=chunk.chunk_index,
                section_title=chunk.section_title,
                content=chunk.content,
                similarity_score=1.0 - float(distance),
            )
        )

    return results
