# OpsGuard AI API

Minimal FastAPI backend for OpsGuard AI.

## Current endpoints

- `GET /health` returns `{"status": "ok"}`.
- `POST /documents` creates a document row.
- `GET /documents` lists document rows.
- `POST /documents/upload` accepts a PDF or Markdown file, stores it locally, and creates a document row with status `uploaded`.
