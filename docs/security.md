# Security Notes

This document summarizes the current security posture of OpsGuard AI. It is not a production security program yet; it records the guardrails that exist in this portfolio-stage backend.

## Current Guardrails

- Uploaded files are saved under a configured local upload directory using server-generated names.
- All application endpoints except `GET /health` are protected by a minimal server-side API key when `REQUIRE_API_KEY=true`.
- Text extraction only reads paths already associated with persisted documents.
- Chunk embeddings are stored in PostgreSQL/pgvector but are not returned by API responses.
- RAG context is bounded by `ANSWER_CONTEXT_MAX_CHARS` and `ANSWER_SOURCE_MAX_CHARS`.
- Retrieved source content is treated as untrusted data and wrapped in explicit source delimiters.
- Prompt-injection signals are detected heuristically and exposed to the LLM as warnings, not instructions.
- Obvious secrets in retrieved source excerpts are redacted before they are sent to the LLM or returned as citation excerpts.
- AI review tool calls are validated by backend Pydantic schemas before any database write.
- Invalid AI tool calls are rejected and traced in `audit_events`.
- Local browser calls are limited by configured CORS origins for the Next.js Review Console.

## API Key Authentication

OpsGuard AI uses a minimal API key guard before full user authentication exists.

Configuration:

```env
REQUIRE_API_KEY=true
OPS_GUARD_API_KEY=replace-with-local-dev-api-key
```

Protected requests must send:

```text
X-API-Key: <configured key>
```

`GET /health` is public. Every other current HTTP endpoint is protected, including document ingestion and processing, semantic search, RAG answers, AI review task suggestions, review task reads/writes and audit event reads.

If the key is missing, invalid, or not configured while strict mode is enabled, the API returns HTTP `401`:

```json
{"detail": "Invalid or missing API key"}
```

The backend stores the expected key as a secret setting, compares values with `secrets.compare_digest`, does not log the header, and does not include either the configured key or the provided key in error responses.

## Frontend API Key Handling

The Next.js Review Console can store the API key in browser `localStorage` for
local development and portfolio demos. After the key is saved, the UI only shows
that a key is configured; it does not render the full value.

This is not production authentication. A browser-stored shared API key is
exposed to any script running on that origin and should be replaced later by
real user authentication, sessions, roles, tenant boundaries and key rotation.

The frontend must not log the key, put it in URLs, or include it in displayed
error messages.

## CORS

The API uses `CORS_ALLOWED_ORIGINS` to allow the local Review Console to call
protected endpoints with `X-API-Key`:

```env
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

Keep this list narrow. Do not use wildcard origins for authenticated browser
flows.

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

- API key auth identifies access to the backend, not a real user; `actor_id` is still usually `null`.
- There are no roles, tenant isolation or permission checks yet.
- There is no login, password management, JWT, session handling or OAuth.
- There is no key rotation, per-client key registry or rate limiting yet.
- The Review Console stores the shared demo API key in browser `localStorage`.
- Audit pagination is limited to a bounded `limit` parameter, not cursor pagination.
- There is no SIEM integration, alerting pipeline or production retention policy.

Future security work should add users, roles, tenant boundaries, actor attribution, stronger audit retention rules, approval workflows for AI-suggested tasks and production monitoring.
