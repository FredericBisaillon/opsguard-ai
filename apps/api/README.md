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
- `POST /review-tasks`, `GET /review-tasks`, `GET /review-tasks/{task_id}`, `PATCH /review-tasks/{task_id}`, and `POST /review-tasks/{task_id}/dismiss` manage review tasks.
- `POST /ai/review-tasks/suggest` asks the LLM for a validated review task suggestion.
- `GET /audit-events` and `GET /audit-events/{event_id}` read structured audit events.
- `GET /documents/{document_id}/chunks` lists persisted chunks for a document.
- `python -m opsguard_api.evals.run_rag_evals` runs the local RAG eval harness against a JSONL dataset and writes reports under `reports/evals`.

All API endpoints except `GET /health` are protected by the `X-API-Key` header when `REQUIRE_API_KEY=true`.

## API key auth

Local configuration is read from the repository-level `.env` file:

```env
REQUIRE_API_KEY=true
OPS_GUARD_API_KEY=replace-with-local-dev-api-key
```

Call protected endpoints with:

```bash
curl -H "X-API-Key: $OPS_GUARD_API_KEY" http://127.0.0.1:8000/documents
```

Missing, invalid, or unconfigured keys in strict mode return:

```json
{"detail": "Invalid or missing API key"}
```

with HTTP `401`. This is intentionally minimal API key protection, not full user auth, JWT, RBAC, sessions, or multi-tenant isolation.

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
