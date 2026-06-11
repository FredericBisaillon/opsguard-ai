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
- `GET /documents/{document_id}/chunks` lists persisted chunks for a document.
