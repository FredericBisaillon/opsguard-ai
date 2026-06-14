import re
from dataclasses import dataclass, replace

from sqlalchemy.orm import Session

from opsguard_api.config import Settings
from opsguard_api.schemas import SemanticSearchRequest
from opsguard_api.services import search as search_service
from opsguard_api.services.embeddings import EmbeddingClient

MIN_CONTEXT_EXCERPT_CHARS = 80

CONTEXT_DELIMITER_REPLACEMENT = "[REMOVED_CONTEXT_DELIMITER]"
REDACTED_SECRET = "[REDACTED_SECRET]"

_CONTEXT_DELIMITER_PATTERN = re.compile(
    r"-{2,}\s*(?:begin|end)\s+(?:retrieved\s+sources|source)\b[^\n]*-{2,}",
    re.IGNORECASE,
)
_OPENAI_KEY_PATTERN = re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{12,}\b")
_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"\b([-A-Za-z0-9_]*api[_-]?key|[-A-Za-z0-9_]*secret|"
    r"[-A-Za-z0-9_]*token|[-A-Za-z0-9_]*password|"
    r"[-A-Za-z0-9_]*credential)\s*[:=]\s*([^\s,;]+)",
    re.IGNORECASE,
)
_PROMPT_INJECTION_SIGNAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "ignore_previous_instructions",
        re.compile(
            r"\b(ignore|disregard|forget|override)\b[\s\S]{0,80}"
            r"\b(previous|prior|above|earlier|system|developer|user)\b"
            r"[\s\S]{0,80}\b(instruction|prompt|message|rule)s?\b",
            re.IGNORECASE,
        ),
    ),
    (
        "role_override",
        re.compile(
            r"\b(you are now|act as|pretend to be|new role|"
            r"system message:|developer message:)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "system_prompt_exfiltration",
        re.compile(
            r"\b(reveal|print|show|output|repeat|disclose)\b[\s\S]{0,80}"
            r"\b(system prompt|developer prompt|hidden instructions|"
            r"initial instructions)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "secret_exfiltration",
        re.compile(
            r"\b(reveal|print|show|output|send|exfiltrate|disclose)\b"
            r"[\s\S]{0,80}\b(api key|secret|token|password|"
            r"environment variable|env var|credential)s?\b",
            re.IGNORECASE,
        ),
    ),
    (
        "tool_or_external_action",
        re.compile(
            r"\b(call|use|invoke|execute|run)\b[\s\S]{0,80}"
            r"\b(tool|function|browser|shell|terminal|command)\b",
            re.IGNORECASE,
        ),
    ),
)


@dataclass(frozen=True)
class RetrievalSourceData:
    source_id: str
    document_id: int
    document_title: str
    chunk_id: int
    chunk_index: int
    section_title: str | None
    excerpt: str
    similarity_score: float
    prompt_injection_signals: tuple[str, ...]


@dataclass(frozen=True)
class RetrievalContextData:
    query: str
    context_text: str
    retrieved_chunk_count: int
    sources: list[RetrievalSourceData]


def retrieve_answer_context(
    db: Session,
    query: str,
    document_id: int | None,
    top_k: int | None,
    settings: Settings,
    embedding_client: EmbeddingClient,
) -> RetrievalContextData:
    search_response = search_service.semantic_search(
        db=db,
        search_in=SemanticSearchRequest(
            query=query,
            document_id=document_id,
            top_k=top_k,
        ),
        settings=settings,
        embedding_client=embedding_client,
    )
    sources = _build_sources(search_response.results, settings)

    return RetrievalContextData(
        query=search_response.query,
        context_text="\n\n".join(_format_source(source) for source in sources),
        retrieved_chunk_count=search_response.result_count,
        sources=sources,
    )


def _build_sources(
    results: list[search_service.SemanticSearchResultData],
    settings: Settings,
) -> list[RetrievalSourceData]:
    sources: list[RetrievalSourceData] = []
    used_chars = 0

    for source_index, result in enumerate(results, start=1):
        normalized_content = _normalize_content(result.content)
        prompt_injection_signals = detect_prompt_injection_signals(
            normalized_content
        )
        excerpt = _truncate_text(
            _safe_source_excerpt(normalized_content),
            settings.answer_source_max_chars,
        )
        if not excerpt:
            continue

        source = RetrievalSourceData(
            source_id=f"S{source_index}",
            document_id=result.document_id,
            document_title=result.document_title,
            chunk_id=result.chunk_id,
            chunk_index=result.chunk_index,
            section_title=result.section_title,
            excerpt=excerpt,
            similarity_score=result.similarity_score,
            prompt_injection_signals=prompt_injection_signals,
        )
        block = _format_source(source)
        separator_chars = 2 if sources else 0

        next_context_chars = used_chars + separator_chars + len(block)
        if next_context_chars > settings.answer_context_max_chars:
            remaining_chars = (
                settings.answer_context_max_chars - used_chars - separator_chars
            )
            fitted_source = _fit_source_to_remaining_context(
                source,
                remaining_chars,
            )
            if fitted_source is None:
                break

            source = fitted_source
            block = _format_source(source)

        sources.append(source)
        used_chars += separator_chars + len(block)

    return sources


def _fit_source_to_remaining_context(
    source: RetrievalSourceData,
    remaining_chars: int,
) -> RetrievalSourceData | None:
    empty_excerpt_block = _format_source(replace(source, excerpt=""))
    available_excerpt_chars = remaining_chars - len(empty_excerpt_block)
    if available_excerpt_chars < MIN_CONTEXT_EXCERPT_CHARS:
        return None

    return replace(
        source,
        excerpt=_truncate_text(source.excerpt, available_excerpt_chars),
    )


def _normalize_content(content: str) -> str:
    return "\n".join(line.strip() for line in content.splitlines() if line.strip())


def detect_prompt_injection_signals(content: str) -> tuple[str, ...]:
    return tuple(
        signal
        for signal, pattern in _PROMPT_INJECTION_SIGNAL_PATTERNS
        if pattern.search(content)
    )


def _safe_source_excerpt(content: str) -> str:
    return _escape_context_delimiters(_redact_potential_secrets(content))


def _redact_potential_secrets(content: str) -> str:
    redacted = _OPENAI_KEY_PATTERN.sub(REDACTED_SECRET, content)
    return _SECRET_ASSIGNMENT_PATTERN.sub(
        lambda match: f"{match.group(1)}={REDACTED_SECRET}",
        redacted,
    )


def _escape_context_delimiters(content: str) -> str:
    return _CONTEXT_DELIMITER_PATTERN.sub(CONTEXT_DELIMITER_REPLACEMENT, content)


def _truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text

    if max_chars <= 3:
        return text[:max_chars]

    return f"{text[: max_chars - 3].rstrip()}..."


def _format_source(source: RetrievalSourceData) -> str:
    section = source.section_title or "None"
    signals = (
        ", ".join(source.prompt_injection_signals)
        if source.prompt_injection_signals
        else "none"
    )
    return "\n".join(
        [
            f"----- BEGIN SOURCE {source.source_id} -----",
            f"source_id: {source.source_id}",
            f"source_marker: [{source.source_id}]",
            f"document_id: {source.document_id}",
            f"document_title: {source.document_title}",
            f"chunk_id: {source.chunk_id}",
            f"chunk_index: {source.chunk_index}",
            f"section_title: {section}",
            f"similarity_score: {source.similarity_score:.4f}",
            f"detected_prompt_injection_signals: {signals}",
            f"----- BEGIN SOURCE {source.source_id} CONTENT -----",
            source.excerpt,
            f"----- END SOURCE {source.source_id} CONTENT -----",
            f"----- END SOURCE {source.source_id} -----",
        ]
    )
