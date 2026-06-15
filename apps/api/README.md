# OpsGuard AI API

Minimal FastAPI backend for OpsGuard AI.

## Current endpoints

- `GET /health` returns `{"status": "ok"}`.
- `POST /documents` creates a document row.
- `GET /documents` lists document rows.
- `POST /documents/upload` accepts a PDF, Markdown, or plain text file, stores it locally, and creates a document row with status `uploaded`.
- `POST /documents/{document_id}/extract-text` extracts text from an uploaded PDF, Markdown, or plain text file, stores the extracted text locally, and updates the document status.
- `POST /documents/{document_id}/chunk` chunks extracted text into ordered, structure-aware document chunks.
- `POST /documents/{document_id}/embed` generates embeddings for persisted chunks and stores them in pgvector.
- `POST /search` retrieves the most relevant embedded chunks with pgvector semantic search.
- `POST /answer` builds a controlled, source-delimited RAG context from retrieved chunks and returns an answer with chunk citations or an abstention.
- `GET /documents/{document_id}/chunks` lists persisted chunks for a document.
- `python -m opsguard_api.evals.run_rag_evals` runs the local RAG eval harness against a JSONL dataset and writes reports under `reports/evals`.

## RAG answer security

`POST /answer` treats retrieved source content as untrusted data. Sources are
wrapped in explicit `BEGIN/END SOURCE` delimiters, suspicious prompt-injection
signals are annotated in the context, and obvious secret-like assignments are
redacted before excerpts are sent to the LLM or returned as citations.

## RAG eval harness

From `apps/api`:

```bash
PYTHONPATH=src uv run python -m opsguard_api.evals.run_rag_evals --cases data/eval/rag_eval_cases.jsonl
```

The runner uses the real retrieval and answer services, so `OPENAI_API_KEY` must be
configured when you launch it intentionally. Unit tests for eval scoring remain
deterministic and do not call OpenAI.
