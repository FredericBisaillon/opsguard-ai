from dataclasses import dataclass

from sqlalchemy.orm import Session

from opsguard_api.config import Settings
from opsguard_api.constants import ANSWER_ABSTENTION_MESSAGE
from opsguard_api.schemas import AnswerRequest
from opsguard_api.services import retrieval
from opsguard_api.services import search as search_service
from opsguard_api.services.embeddings import EmbeddingClient
from opsguard_api.services.llm import (
    LLMAnswerData,
    LLMClient,
    LLMClientError,
    LLMConfigurationError,
    LLMMessage,
    LLMProviderError,
    LLMResponseError,
)

SYSTEM_PROMPT = """You answer user questions using only the provided document sources.
Do not use outside knowledge. Do not call tools. Do not browse.
Return only valid JSON with this shape:
{"is_answered": true, "answer": "...", "citations": ["S1"]}

Rules:
- If the sources do not contain the answer, set is_answered to false.
- Use the abstention answer and return an empty citations list.
- If is_answered is true, every factual claim must be grounded in the sources.
- Include source markers such as [S1] in the answer text.
- Include only source IDs that appear in the provided sources.
- Answer in the same language as the question.
"""


@dataclass(frozen=True)
class AnswerCitationData:
    source_id: str
    document_id: int
    document_title: str
    chunk_id: int
    chunk_index: int
    section_title: str | None
    excerpt: str
    similarity_score: float


@dataclass(frozen=True)
class AnswerResponseData:
    query: str
    answer: str
    is_answered: bool
    citations: list[AnswerCitationData]
    retrieved_chunk_count: int


class AnswerError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def answer_question(
    db: Session,
    answer_in: AnswerRequest,
    settings: Settings,
    embedding_client: EmbeddingClient,
    llm_client: LLMClient,
) -> AnswerResponseData:
    query = answer_in.query.strip()

    try:
        context = retrieval.retrieve_answer_context(
            db=db,
            query=query,
            document_id=answer_in.document_id,
            top_k=answer_in.top_k,
            settings=settings,
            embedding_client=embedding_client,
        )
    except search_service.SemanticSearchError as exc:
        raise AnswerError(exc.message, status_code=exc.status_code) from exc

    if not context.sources:
        return _abstained_response(
            query=context.query,
            retrieved_chunk_count=context.retrieved_chunk_count,
        )

    try:
        llm_answer = llm_client.generate_answer(
            _build_messages(query=context.query, context_text=context.context_text)
        )
    except LLMConfigurationError as exc:
        raise AnswerError(exc.message, status_code=500) from exc
    except LLMProviderError as exc:
        raise AnswerError(exc.message, status_code=502) from exc
    except LLMResponseError as exc:
        raise AnswerError(exc.message, status_code=502) from exc
    except LLMClientError as exc:
        raise AnswerError(exc.message, status_code=500) from exc

    return _response_from_llm_answer(
        query=context.query,
        context=context,
        llm_answer=llm_answer,
    )


def _build_messages(query: str, context_text: str) -> list[LLMMessage]:
    user_prompt = "\n\n".join(
        [
            f"Abstention answer: {ANSWER_ABSTENTION_MESSAGE}",
            f"Question:\n{query}",
            f"Sources:\n{context_text}",
        ]
    )
    return [
        LLMMessage(role="system", content=SYSTEM_PROMPT),
        LLMMessage(role="user", content=user_prompt),
    ]


def _response_from_llm_answer(
    query: str,
    context: retrieval.RetrievalContextData,
    llm_answer: LLMAnswerData,
) -> AnswerResponseData:
    if not llm_answer.is_answered or not llm_answer.answer:
        return _abstained_response(
            query=query,
            retrieved_chunk_count=context.retrieved_chunk_count,
        )

    citations = _citations_from_llm_answer(context.sources, llm_answer.citations)
    if not citations:
        return _abstained_response(
            query=query,
            retrieved_chunk_count=context.retrieved_chunk_count,
        )

    return AnswerResponseData(
        query=query,
        answer=llm_answer.answer,
        is_answered=True,
        citations=citations,
        retrieved_chunk_count=context.retrieved_chunk_count,
    )


def _citations_from_llm_answer(
    sources: list[retrieval.RetrievalSourceData],
    citation_ids: list[str],
) -> list[AnswerCitationData]:
    source_by_id = {source.source_id: source for source in sources}
    deduped_ids: list[str] = []
    for citation_id in citation_ids:
        if citation_id not in deduped_ids:
            deduped_ids.append(citation_id)

    if not deduped_ids:
        return []

    if any(citation_id not in source_by_id for citation_id in deduped_ids):
        return []

    return [
        _citation_from_source(source_by_id[citation_id])
        for citation_id in deduped_ids
    ]


def _citation_from_source(
    source: retrieval.RetrievalSourceData,
) -> AnswerCitationData:
    return AnswerCitationData(
        source_id=source.source_id,
        document_id=source.document_id,
        document_title=source.document_title,
        chunk_id=source.chunk_id,
        chunk_index=source.chunk_index,
        section_title=source.section_title,
        excerpt=source.excerpt,
        similarity_score=source.similarity_score,
    )


def _abstained_response(
    query: str,
    retrieved_chunk_count: int,
) -> AnswerResponseData:
    return AnswerResponseData(
        query=query,
        answer=ANSWER_ABSTENTION_MESSAGE,
        is_answered=False,
        citations=[],
        retrieved_chunk_count=retrieved_chunk_count,
    )
