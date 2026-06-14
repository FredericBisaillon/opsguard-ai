import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class RagEvalCaseLoadError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class RagEvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    document_id: int | None = Field(default=None, gt=0)
    top_k: int | None = Field(default=None, ge=1)
    expected_answer_contains: list[str] = Field(default_factory=list)
    expected_section_title: str | None = None
    expected_chunk_ids: list[int] = Field(default_factory=list)
    should_abstain: bool = False

    @field_validator("id", "query")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value cannot be blank.")
        return cleaned

    @field_validator("expected_answer_contains")
    @classmethod
    def expected_text_must_not_be_blank(cls, values: list[str]) -> list[str]:
        cleaned_values = [value.strip() for value in values]
        if any(not value for value in cleaned_values):
            raise ValueError("Expected answer text cannot be blank.")
        return cleaned_values

    @field_validator("expected_section_title")
    @classmethod
    def empty_section_title_is_none(cls, value: str | None) -> str | None:
        if value is None:
            return None

        cleaned = value.strip()
        return cleaned or None

    @field_validator("expected_chunk_ids")
    @classmethod
    def expected_chunk_ids_must_be_positive(cls, values: list[int]) -> list[int]:
        if any(value <= 0 for value in values):
            raise ValueError("Expected chunk ids must be positive.")
        return values


@dataclass(frozen=True)
class RagEvalRetrievedChunk:
    source_id: str
    document_id: int
    document_title: str
    chunk_id: int
    chunk_index: int
    section_title: str | None
    similarity_score: float
    excerpt: str


@dataclass(frozen=True)
class RagEvalCitation:
    source_id: str
    chunk_id: int
    chunk_index: int
    section_title: str | None


@dataclass(frozen=True)
class RagEvalPipelineOutput:
    answer: str
    is_answered: bool
    citations: list[RagEvalCitation] = field(default_factory=list)
    retrieved_chunks: list[RagEvalRetrievedChunk] = field(default_factory=list)


@dataclass(frozen=True)
class RagEvalMetrics:
    retrieval_hit: bool | None
    section_hit: bool | None
    result_count: int
    has_citation: bool
    expected_text_found: bool | None
    abstention_correct: bool
    answer_non_empty: bool | None


@dataclass(frozen=True)
class RagEvalResult:
    case: RagEvalCase
    answer: str
    is_answered: bool
    citations: list[RagEvalCitation]
    retrieved_chunks: list[RagEvalRetrievedChunk]
    metrics: RagEvalMetrics
    passed: bool
    failures: list[str]
    error: str | None = None


@dataclass(frozen=True)
class RagEvalSummary:
    total_cases: int
    passed_cases: int
    failed_cases: int
    retrieval_hit_rate: float | None
    citation_rate: float | None
    abstention_accuracy: float | None
    expected_text_match_rate: float | None


@dataclass(frozen=True)
class RagEvalReportPaths:
    markdown_path: Path
    json_path: Path


SOURCE_MARKER_PATTERN = re.compile(r"\[S\d+\]")


def load_eval_cases(path: Path) -> list[RagEvalCase]:
    cases: list[RagEvalCase] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RagEvalCaseLoadError(f"Could not read eval cases: {path}") from exc

    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue

        try:
            payload: Any = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RagEvalCaseLoadError(
                f"Invalid JSON on line {line_number}: {exc.msg}"
            ) from exc

        try:
            cases.append(RagEvalCase.model_validate(payload))
        except ValidationError as exc:
            raise RagEvalCaseLoadError(
                f"Invalid eval case on line {line_number}: {exc}"
            ) from exc

    if not cases:
        raise RagEvalCaseLoadError("Eval cases file did not contain any cases.")

    return cases


def score_case(case: RagEvalCase, output: RagEvalPipelineOutput) -> RagEvalResult:
    expected_chunk_ids = set(case.expected_chunk_ids)
    retrieved_chunk_ids = {chunk.chunk_id for chunk in output.retrieved_chunks}
    retrieval_hit = (
        None
        if not expected_chunk_ids
        else bool(expected_chunk_ids.intersection(retrieved_chunk_ids))
    )

    expected_section_title = _normalize_text(case.expected_section_title)
    section_hit = (
        None
        if expected_section_title is None
        else any(
            _normalize_text(chunk.section_title) == expected_section_title
            for chunk in output.retrieved_chunks
        )
    )

    expected_text_found = (
        None
        if not case.expected_answer_contains
        else _answer_contains_expected_text(
            answer=output.answer,
            expected_texts=case.expected_answer_contains,
        )
    )
    abstention_correct = (
        not output.is_answered if case.should_abstain else output.is_answered
    )
    answer_non_empty = None if case.should_abstain else bool(output.answer.strip())
    has_citation = bool(output.citations) or bool(
        SOURCE_MARKER_PATTERN.search(output.answer)
    )

    metrics = RagEvalMetrics(
        retrieval_hit=retrieval_hit,
        section_hit=section_hit,
        result_count=len(output.retrieved_chunks),
        has_citation=has_citation,
        expected_text_found=expected_text_found,
        abstention_correct=abstention_correct,
        answer_non_empty=answer_non_empty,
    )
    failures = _case_failures(case, metrics)

    return RagEvalResult(
        case=case,
        answer=output.answer,
        is_answered=output.is_answered,
        citations=output.citations,
        retrieved_chunks=output.retrieved_chunks,
        metrics=metrics,
        passed=not failures,
        failures=failures,
    )


def score_case_error(case: RagEvalCase, error: str) -> RagEvalResult:
    metrics = RagEvalMetrics(
        retrieval_hit=None,
        section_hit=None,
        result_count=0,
        has_citation=False,
        expected_text_found=None,
        abstention_correct=False,
        answer_non_empty=None,
    )
    return RagEvalResult(
        case=case,
        answer="",
        is_answered=False,
        citations=[],
        retrieved_chunks=[],
        metrics=metrics,
        passed=False,
        failures=[error],
        error=error,
    )


def summarize_results(results: list[RagEvalResult]) -> RagEvalSummary:
    total_cases = len(results)
    passed_cases = sum(1 for result in results if result.passed)
    failed_cases = total_cases - passed_cases
    non_abstain_results = [
        result for result in results if not result.case.should_abstain
    ]

    return RagEvalSummary(
        total_cases=total_cases,
        passed_cases=passed_cases,
        failed_cases=failed_cases,
        retrieval_hit_rate=_rate(
            result.metrics.retrieval_hit
            for result in results
            if result.metrics.retrieval_hit is not None
        ),
        citation_rate=_rate(
            result.metrics.has_citation for result in non_abstain_results
        ),
        abstention_accuracy=_rate(
            result.metrics.abstention_correct for result in results
        ),
        expected_text_match_rate=_rate(
            result.metrics.expected_text_found
            for result in results
            if result.metrics.expected_text_found is not None
        ),
    )


def write_reports(
    results: list[RagEvalResult],
    summary: RagEvalSummary,
    reports_dir: Path,
) -> RagEvalReportPaths:
    reports_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = reports_dir / "rag_eval_report.md"
    json_path = reports_dir / "rag_eval_results.json"

    markdown_path.write_text(
        generate_markdown_report(results=results, summary=summary),
        encoding="utf-8",
    )
    json_path.write_text(
        json.dumps(results_payload(results=results, summary=summary), indent=2),
        encoding="utf-8",
    )

    return RagEvalReportPaths(markdown_path=markdown_path, json_path=json_path)


def results_payload(
    results: list[RagEvalResult],
    summary: RagEvalSummary,
) -> dict[str, Any]:
    return {
        "summary": asdict(summary),
        "results": [result_to_dict(result) for result in results],
    }


def result_to_dict(result: RagEvalResult) -> dict[str, Any]:
    return {
        "case": result.case.model_dump(),
        "answer": result.answer,
        "is_answered": result.is_answered,
        "citations": [asdict(citation) for citation in result.citations],
        "retrieved_chunks": [
            asdict(retrieved_chunk) for retrieved_chunk in result.retrieved_chunks
        ],
        "metrics": asdict(result.metrics),
        "passed": result.passed,
        "failures": result.failures,
        "error": result.error,
    }


def generate_markdown_report(
    results: list[RagEvalResult],
    summary: RagEvalSummary,
) -> str:
    lines = [
        "# RAG Evaluation Report",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Total cases | {summary.total_cases} |",
        f"| Passed cases | {summary.passed_cases} |",
        f"| Failed cases | {summary.failed_cases} |",
        f"| Retrieval hit rate | {_format_rate(summary.retrieval_hit_rate)} |",
        f"| Citation rate | {_format_rate(summary.citation_rate)} |",
        f"| Abstention accuracy | {_format_rate(summary.abstention_accuracy)} |",
        (
            "| Expected text match rate | "
            f"{_format_rate(summary.expected_text_match_rate)} |"
        ),
        "",
        "## Cases",
        "",
        (
            "| Case | Status | Retrieval | Section | Citation | Abstention | "
            "Expected text | Results | Failures |"
        ),
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]

    for result in results:
        status = "PASS" if result.passed else "FAIL"
        failures = "<br>".join(_markdown_cell(failure) for failure in result.failures)
        lines.append(
            f"| {_markdown_cell(result.case.id)} "
            f"| {status} "
            f"| {_format_optional_bool(result.metrics.retrieval_hit)} "
            f"| {_format_optional_bool(result.metrics.section_hit)} "
            f"| {_format_bool(result.metrics.has_citation)} "
            f"| {_format_bool(result.metrics.abstention_correct)} "
            f"| {_format_optional_bool(result.metrics.expected_text_found)} "
            f"| {result.metrics.result_count} "
            f"| {failures} |"
        )

    lines.append("")
    return "\n".join(lines)


def _case_failures(case: RagEvalCase, metrics: RagEvalMetrics) -> list[str]:
    failures: list[str] = []
    if metrics.retrieval_hit is False:
        failures.append("Expected chunk was not retrieved.")
    if metrics.section_hit is False:
        failures.append("Expected section was not retrieved.")
    if not metrics.abstention_correct:
        if case.should_abstain:
            failures.append("Expected abstention, but the system answered.")
        else:
            failures.append("Expected an answer, but the system abstained.")
    if not case.should_abstain and not metrics.has_citation:
        failures.append("Expected at least one citation.")
    if metrics.expected_text_found is False:
        failures.append("Expected answer text was not found.")
    if metrics.answer_non_empty is False:
        failures.append("Expected a non-empty answer.")
    return failures


def _answer_contains_expected_text(
    answer: str,
    expected_texts: list[str],
) -> bool:
    normalized_answer = _normalize_for_contains(answer)
    return all(
        _normalize_for_contains(expected_text) in normalized_answer
        for expected_text in expected_texts
    )


def _normalize_for_contains(value: str) -> str:
    return " ".join(value.casefold().split())


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None

    cleaned = " ".join(value.casefold().split())
    return cleaned or None


def _rate(values: Any) -> float | None:
    bool_values = list(values)
    if not bool_values:
        return None

    return sum(1 for value in bool_values if value) / len(bool_values)


def _format_rate(value: float | None) -> str:
    if value is None:
        return "n/a"

    return f"{value:.1%}"


def _format_bool(value: bool) -> str:
    return "yes" if value else "no"


def _format_optional_bool(value: bool | None) -> str:
    if value is None:
        return "n/a"

    return _format_bool(value)


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")
