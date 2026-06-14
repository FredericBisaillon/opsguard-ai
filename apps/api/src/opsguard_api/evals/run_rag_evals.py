import argparse
from collections.abc import Sequence
from pathlib import Path

from opsguard_api.config import PROJECT_ROOT, Settings, get_settings
from opsguard_api.evals.rag import (
    RagEvalCase,
    RagEvalCaseLoadError,
    RagEvalCitation,
    RagEvalPipelineOutput,
    RagEvalReportPaths,
    RagEvalResult,
    RagEvalRetrievedChunk,
    RagEvalSummary,
    load_eval_cases,
    score_case,
    score_case_error,
    summarize_results,
    write_reports,
)
from opsguard_api.services import answer as answer_service
from opsguard_api.services import retrieval
from opsguard_api.services import search as search_service
from opsguard_api.services.embeddings import (
    EmbeddingClient,
    EmbeddingConfigurationError,
    OpenAIEmbeddingClient,
)
from opsguard_api.services.llm import LLMClient, LLMConfigurationError, OpenAILLMClient

DEFAULT_CASES_PATH = PROJECT_ROOT / "data" / "eval" / "rag_eval_cases.jsonl"
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "reports" / "evals"


def run_eval_cases(
    cases: list[RagEvalCase],
    settings: Settings,
    embedding_client: EmbeddingClient,
    llm_client: LLMClient,
) -> list[RagEvalResult]:
    from opsguard_api.db import SessionLocal

    results: list[RagEvalResult] = []
    with SessionLocal() as db:
        for case in cases:
            try:
                context = retrieval.retrieve_answer_context(
                    db=db,
                    query=case.query,
                    document_id=case.document_id,
                    top_k=case.top_k,
                    settings=settings,
                    embedding_client=embedding_client,
                )
                answer = answer_service.answer_from_context(
                    query=context.query,
                    context=context,
                    llm_client=llm_client,
                )
            except (
                answer_service.AnswerError,
                search_service.SemanticSearchError,
            ) as exc:
                results.append(score_case_error(case, exc.message))
                continue

            results.append(score_case(case, _pipeline_output(context, answer)))

    return results


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    cases_path = _resolve_repo_path(args.cases)
    reports_dir = _resolve_repo_path(args.reports_dir)

    try:
        settings = get_settings()
    except Exception as exc:
        print(f"Could not load settings: {exc}")
        return 2

    if not settings.openai_api_key or not settings.openai_api_key.strip():
        print(
            "OPENAI_API_KEY is required to run RAG evals. "
            "Set it in the repo root .env file or your shell environment."
        )
        return 2

    embedding_client = OpenAIEmbeddingClient(
        api_key=settings.openai_api_key,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
    )
    llm_client = OpenAILLMClient(
        api_key=settings.openai_api_key,
        model=settings.llm_model,
    )

    try:
        embedding_client.validate_configuration()
        llm_client.validate_configuration()
        cases = load_eval_cases(cases_path)
        from opsguard_api.db import init_database

        init_database()
        results = run_eval_cases(
            cases=cases,
            settings=settings,
            embedding_client=embedding_client,
            llm_client=llm_client,
        )
    except (
        EmbeddingConfigurationError,
        LLMConfigurationError,
        RagEvalCaseLoadError,
    ) as exc:
        print(exc.message)
        return 2
    except Exception as exc:
        print(f"RAG eval runner failed: {exc}")
        return 2

    summary = summarize_results(results)
    report_paths = write_reports(
        results=results,
        summary=summary,
        reports_dir=reports_dir,
    )
    _print_summary(summary=summary, report_paths=report_paths)

    return 0 if summary.failed_cases == 0 else 1


def _pipeline_output(
    context: retrieval.RetrievalContextData,
    answer: answer_service.AnswerResponseData,
) -> RagEvalPipelineOutput:
    return RagEvalPipelineOutput(
        answer=answer.answer,
        is_answered=answer.is_answered,
        citations=[
            RagEvalCitation(
                source_id=citation.source_id,
                chunk_id=citation.chunk_id,
                chunk_index=citation.chunk_index,
                section_title=citation.section_title,
            )
            for citation in answer.citations
        ],
        retrieved_chunks=[
            RagEvalRetrievedChunk(
                source_id=source.source_id,
                document_id=source.document_id,
                document_title=source.document_title,
                chunk_id=source.chunk_id,
                chunk_index=source.chunk_index,
                section_title=source.section_title,
                similarity_score=source.similarity_score,
                excerpt=source.excerpt,
            )
            for source in context.sources
        ],
    )


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the minimal OpsGuard AI RAG evaluation harness."
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=DEFAULT_CASES_PATH,
        help="Path to a JSONL eval dataset.",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=DEFAULT_REPORTS_DIR,
        help="Directory where eval reports will be written.",
    )
    return parser.parse_args(argv)


def _resolve_repo_path(path: Path) -> Path:
    if path.is_absolute():
        return path

    cwd_path = Path.cwd() / path
    if cwd_path.exists():
        return cwd_path

    return PROJECT_ROOT / path


def _print_summary(
    summary: RagEvalSummary,
    report_paths: RagEvalReportPaths,
) -> None:
    print("RAG eval summary")
    print(f"  total cases: {summary.total_cases}")
    print(f"  passed cases: {summary.passed_cases}")
    print(f"  failed cases: {summary.failed_cases}")
    print(f"  retrieval hit rate: {_format_rate(summary.retrieval_hit_rate)}")
    print(f"  citation rate: {_format_rate(summary.citation_rate)}")
    print(f"  abstention accuracy: {_format_rate(summary.abstention_accuracy)}")
    print(
        "  expected text match rate: "
        f"{_format_rate(summary.expected_text_match_rate)}"
    )
    print(f"  markdown report: {report_paths.markdown_path}")
    print(f"  json results: {report_paths.json_path}")


def _format_rate(value: float | None) -> str:
    if value is None:
        return "n/a"

    return f"{value:.1%}"


if __name__ == "__main__":
    raise SystemExit(main())
