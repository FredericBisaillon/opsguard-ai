from pathlib import Path

from opsguard_api.evals.rag import (
    RagEvalCase,
    RagEvalCitation,
    RagEvalPipelineOutput,
    RagEvalRetrievedChunk,
    generate_markdown_report,
    load_eval_cases,
    score_case,
    summarize_results,
    write_reports,
)


def test_load_eval_cases_from_jsonl(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.jsonl"
    cases_path.write_text(
        "\n".join(
            [
                (
                    '{"id": "incident-001", '
                    '"query": "What is the deadline?", '
                    '"document_id": 1, '
                    '"expected_answer_contains": ["24 hours"], '
                    '"expected_section_title": "Incident Reporting", '
                    '"expected_chunk_ids": [12], '
                    '"should_abstain": false}'
                ),
                (
                    '{"id": "unknown-001", '
                    '"query": "What is the travel policy?", '
                    '"document_id": 1, '
                    '"should_abstain": true}'
                ),
            ]
        ),
        encoding="utf-8",
    )

    cases = load_eval_cases(cases_path)

    assert [case.id for case in cases] == ["incident-001", "unknown-001"]
    assert cases[0].expected_chunk_ids == [12]
    assert cases[0].expected_section_title == "Incident Reporting"
    assert cases[1].should_abstain is True


def test_score_case_marks_retrieval_hit() -> None:
    result = score_case(
        eval_case(expected_chunk_ids=[12]),
        output(retrieved_chunks=[retrieved_chunk(chunk_id=12)]),
    )

    assert result.metrics.retrieval_hit is True
    assert result.passed is True


def test_score_case_marks_retrieval_miss() -> None:
    result = score_case(
        eval_case(expected_chunk_ids=[12]),
        output(retrieved_chunks=[retrieved_chunk(chunk_id=99)]),
    )

    assert result.metrics.retrieval_hit is False
    assert result.passed is False
    assert "Expected chunk was not retrieved." in result.failures


def test_score_case_tracks_citation_presence() -> None:
    with_citation = score_case(
        eval_case(),
        output(citations=[citation()]),
    )
    without_citation = score_case(
        eval_case(),
        output(citations=[], answer="Security incidents must be reported soon."),
    )

    assert with_citation.metrics.has_citation is True
    assert without_citation.metrics.has_citation is False
    assert without_citation.passed is False
    assert "Expected at least one citation." in without_citation.failures


def test_score_case_tracks_correct_abstention() -> None:
    result = score_case(
        eval_case(should_abstain=True, expected_answer_contains=[]),
        output(
            answer="Je ne sais pas d'apres les sources disponibles.",
            is_answered=False,
        ),
    )

    assert result.metrics.abstention_correct is True
    assert result.metrics.answer_non_empty is None
    assert result.passed is True


def test_summarize_results_calculates_global_rates() -> None:
    passing = score_case(
        eval_case(expected_answer_contains=["24 hours"], expected_chunk_ids=[12]),
        output(retrieved_chunks=[retrieved_chunk(chunk_id=12)]),
    )
    failing = score_case(
        eval_case(
            case_id="incident-002",
            expected_answer_contains=["24 hours"],
            expected_chunk_ids=[12],
        ),
        output(
            answer="I do not know.",
            citations=[],
            retrieved_chunks=[retrieved_chunk(chunk_id=99)],
        ),
    )

    summary = summarize_results([passing, failing])

    assert summary.total_cases == 2
    assert summary.passed_cases == 1
    assert summary.failed_cases == 1
    assert summary.retrieval_hit_rate == 0.5
    assert summary.citation_rate == 0.5
    assert summary.abstention_accuracy == 1.0
    assert summary.expected_text_match_rate == 0.5


def test_markdown_report_and_json_results_are_generated(tmp_path: Path) -> None:
    result = score_case(
        eval_case(expected_answer_contains=["24 hours"], expected_chunk_ids=[12]),
        output(retrieved_chunks=[retrieved_chunk(chunk_id=12)]),
    )
    summary = summarize_results([result])

    markdown = generate_markdown_report(results=[result], summary=summary)
    paths = write_reports(results=[result], summary=summary, reports_dir=tmp_path)

    assert "# RAG Evaluation Report" in markdown
    assert "| Passed cases | 1 |" in markdown
    assert paths.markdown_path.read_text(encoding="utf-8") == markdown
    assert '"passed": true' in paths.json_path.read_text(encoding="utf-8")


def eval_case(
    *,
    case_id: str = "incident-001",
    expected_answer_contains: list[str] | None = None,
    expected_section_title: str | None = None,
    expected_chunk_ids: list[int] | None = None,
    should_abstain: bool = False,
) -> RagEvalCase:
    return RagEvalCase(
        id=case_id,
        query="What is the incident reporting deadline?",
        document_id=1,
        expected_answer_contains=(
            ["24 hours"]
            if expected_answer_contains is None
            else expected_answer_contains
        ),
        expected_section_title=expected_section_title,
        expected_chunk_ids=[] if expected_chunk_ids is None else expected_chunk_ids,
        should_abstain=should_abstain,
    )


def output(
    *,
    answer: str = "Security incidents must be reported within 24 hours. [S1]",
    is_answered: bool = True,
    citations: list[RagEvalCitation] | None = None,
    retrieved_chunks: list[RagEvalRetrievedChunk] | None = None,
) -> RagEvalPipelineOutput:
    return RagEvalPipelineOutput(
        answer=answer,
        is_answered=is_answered,
        citations=[citation()] if citations is None else citations,
        retrieved_chunks=(
            [retrieved_chunk()] if retrieved_chunks is None else retrieved_chunks
        ),
    )


def retrieved_chunk(
    *,
    chunk_id: int = 12,
    section_title: str | None = "Incident Reporting",
) -> RagEvalRetrievedChunk:
    return RagEvalRetrievedChunk(
        source_id="S1",
        document_id=1,
        document_title="Security Policy",
        chunk_id=chunk_id,
        chunk_index=0,
        section_title=section_title,
        similarity_score=0.91,
        excerpt="Security incidents must be reported within 24 hours.",
    )


def citation() -> RagEvalCitation:
    return RagEvalCitation(
        source_id="S1",
        chunk_id=12,
        chunk_index=0,
        section_title="Incident Reporting",
    )
