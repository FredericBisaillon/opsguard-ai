# Security Notes

This document summarizes the current security posture of OpsGuard AI. It is not a production security program yet; it records the guardrails that exist in this portfolio-stage backend.

## Current Guardrails

- Uploaded files are saved under a configured local upload directory using server-generated names.
- Text extraction only reads paths already associated with persisted documents.
- Chunk embeddings are stored in PostgreSQL/pgvector but are not returned by API responses.
- RAG context is bounded by `ANSWER_CONTEXT_MAX_CHARS` and `ANSWER_SOURCE_MAX_CHARS`.
- Retrieved source content is treated as untrusted data and wrapped in explicit source delimiters.
- Prompt-injection signals are detected heuristically and exposed to the LLM as warnings, not instructions.
- Obvious secrets in retrieved source excerpts are redacted before they are sent to the LLM or returned as citation excerpts.
- AI review tool calls are validated by backend Pydantic schemas before any database write.
- Invalid AI tool calls are rejected and traced in `audit_events`.

## Audit Events

The `audit_events` table provides the first traceability layer for security-relevant actions:

- manual review task creation;
- review task dismissal;
- validated AI review task suggestion;
- AI-created review task through `auto_create = true`;
- rejected AI tool call;
- no AI suggestion;
- prompt-injection signals detected in RAG or AI review flows.

Audit events are written by internal services. There is no public `POST /audit-events` endpoint. The public API only exposes read endpoints:

- `GET /audit-events`;
- `GET /audit-events/{event_id}`.

## Data Not Stored In Audit Metadata

Audit metadata is intentionally short and defensive. The audit service drops sensitive keys such as:

- `embedding`;
- `api_key`;
- `token`;
- `secret`;
- `password`;
- `credential`;
- `prompt`;
- `context_text`.

The audit log should not store full prompts, full retrieved contexts, raw document contents, embeddings, API keys, environment variables or provider credentials. Metadata should prefer IDs, counts, model names, short validation errors, signal names and bounded status information.

## Current Limits

- There is no authentication yet, so `actor_id` is usually `null`.
- There are no roles, tenant isolation or permission checks yet.
- Audit events are readable through the local API without an auth layer.
- Audit pagination is limited to a bounded `limit` parameter, not cursor pagination.
- There is no SIEM integration, alerting pipeline or production retention policy.

Future security work should add users, roles, tenant boundaries, actor attribution, stronger audit retention rules, approval workflows for AI-suggested tasks and production monitoring.
