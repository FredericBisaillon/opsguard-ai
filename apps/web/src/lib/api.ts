export const API_KEY_STORAGE_KEY = "opsguard.apiKey";

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
).replace(/\/+$/, "");

export type DocumentStatus =
  | "uploaded"
  | "extracting"
  | "text_extracted"
  | "extraction_failed"
  | "chunking"
  | "chunked"
  | "chunking_failed"
  | "embedding"
  | "embedded"
  | "embedding_failed"
  | "pending"
  | "processed"
  | "failed";

export type ReviewTaskSeverity = "low" | "medium" | "high" | "critical";
export type ReviewTaskStatus =
  | "open"
  | "in_progress"
  | "resolved"
  | "dismissed";
export type ReviewTaskSource = "manual" | "ai_suggested";
export type AuditEventStatus = "success" | "rejected" | "failed" | "info";
export type AuditEventSource = "manual" | "ai" | "api" | "system";

export type HealthResponse = {
  status: string;
};

export type DocumentRead = {
  id: number;
  title: string;
  source_type: string;
  source_path: string;
  status: DocumentStatus;
  created_at: string;
  updated_at: string;
};

export type DocumentExtractionRead = {
  document_id: number;
  status: DocumentStatus;
  extracted_text_path: string;
  character_count: number;
  message: string;
};

export type DocumentChunkingRead = {
  document_id: number;
  status: DocumentStatus;
  chunk_count: number;
  chunk_max_chars: number;
  chunk_overlap_chars: number;
  message: string;
};

export type DocumentEmbeddingRead = {
  document_id: number;
  status: DocumentStatus;
  embedding_model: string;
  embedding_dimensions: number;
  embedded_chunk_count: number;
  message: string;
};

export type AnswerCitation = {
  source_id: string;
  document_id: number;
  document_title: string;
  chunk_id: number;
  chunk_index: number;
  section_title: string | null;
  excerpt: string;
  similarity_score: number;
};

export type AnswerResponse = {
  query: string;
  answer: string;
  is_answered: boolean;
  citations: AnswerCitation[];
  retrieved_chunk_count: number;
  security_warnings?: string[];
};

export type ReviewTaskRead = {
  id: number;
  document_id: number;
  chunk_id: number | null;
  title: string;
  description: string | null;
  severity: ReviewTaskSeverity;
  status: ReviewTaskStatus;
  source: ReviewTaskSource;
  created_at: string;
  updated_at: string;
};

export type ReviewTaskSuggestion = {
  document_id: number;
  chunk_id: number | null;
  title: string;
  description: string | null;
  severity: ReviewTaskSeverity;
  evidence: string;
  reason: string;
};

export type ReviewTaskSuggestionCitation = AnswerCitation;

export type ReviewTaskSuggestionResponse = {
  suggested: boolean;
  created: boolean;
  suggestion: ReviewTaskSuggestion | null;
  review_task: ReviewTaskRead | null;
  citations: ReviewTaskSuggestionCitation[];
  message: string;
  model: string;
};

export type AuditEventRead = {
  id: number;
  event_type: string;
  actor_type: string;
  actor_id: string | null;
  document_id: number | null;
  review_task_id: number | null;
  source: AuditEventSource;
  status: AuditEventStatus;
  summary: string;
  metadata: Record<string, unknown> | null;
  created_at: string;
};

type QueryValue = string | number | boolean | null | undefined;

type ApiRequestOptions = {
  method?: "GET" | "POST" | "PATCH";
  apiKey?: string;
  body?: unknown;
  query?: Record<string, QueryValue>;
};

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, message: string, detail: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export function getStoredApiKey(): string {
  if (typeof window === "undefined") {
    return "";
  }

  return window.localStorage.getItem(API_KEY_STORAGE_KEY) ?? "";
}

export function saveStoredApiKey(apiKey: string): void {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.setItem(API_KEY_STORAGE_KEY, apiKey);
}

export function clearStoredApiKey(): void {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.removeItem(API_KEY_STORAGE_KEY);
}

export async function getHealth(): Promise<HealthResponse> {
  return apiRequest<HealthResponse>("/health");
}

export async function listDocuments(apiKey: string): Promise<DocumentRead[]> {
  return apiRequest<DocumentRead[]>("/documents", { apiKey });
}

export async function uploadDocument({
  apiKey,
  file,
  title,
}: {
  apiKey: string;
  file: File;
  title?: string;
}): Promise<DocumentRead> {
  const formData = new FormData();
  formData.append("file", file);

  if (title?.trim()) {
    formData.append("title", title.trim());
  }

  return apiRequest<DocumentRead>("/documents/upload", {
    method: "POST",
    apiKey,
    body: formData,
  });
}

export async function extractDocumentText(
  apiKey: string,
  documentId: number,
): Promise<DocumentExtractionRead> {
  return apiRequest<DocumentExtractionRead>(
    `/documents/${documentId}/extract-text`,
    {
      method: "POST",
      apiKey,
    },
  );
}

export async function chunkDocument(
  apiKey: string,
  documentId: number,
): Promise<DocumentChunkingRead> {
  return apiRequest<DocumentChunkingRead>(`/documents/${documentId}/chunk`, {
    method: "POST",
    apiKey,
  });
}

export async function embedDocument(
  apiKey: string,
  documentId: number,
): Promise<DocumentEmbeddingRead> {
  return apiRequest<DocumentEmbeddingRead>(`/documents/${documentId}/embed`, {
    method: "POST",
    apiKey,
  });
}

export async function answerQuestion({
  apiKey,
  query,
  documentId,
  topK,
}: {
  apiKey: string;
  query: string;
  documentId?: number;
  topK?: number;
}): Promise<AnswerResponse> {
  return apiRequest<AnswerResponse>("/answer", {
    method: "POST",
    apiKey,
    body: {
      query,
      document_id: documentId,
      top_k: topK,
    },
  });
}

export async function suggestReviewTask({
  apiKey,
  query,
  documentId,
  topK,
  autoCreate,
}: {
  apiKey: string;
  query: string;
  documentId: number;
  topK?: number;
  autoCreate: boolean;
}): Promise<ReviewTaskSuggestionResponse> {
  return apiRequest<ReviewTaskSuggestionResponse>("/ai/review-tasks/suggest", {
    method: "POST",
    apiKey,
    body: {
      query,
      document_id: documentId,
      top_k: topK,
      auto_create: autoCreate,
    },
  });
}

export async function listReviewTasks({
  apiKey,
  documentId,
  status,
}: {
  apiKey: string;
  documentId?: number;
  status?: ReviewTaskStatus;
}): Promise<ReviewTaskRead[]> {
  return apiRequest<ReviewTaskRead[]>("/review-tasks", {
    apiKey,
    query: {
      document_id: documentId,
      status,
    },
  });
}

export async function dismissReviewTask(
  apiKey: string,
  taskId: number,
): Promise<ReviewTaskRead> {
  return apiRequest<ReviewTaskRead>(`/review-tasks/${taskId}/dismiss`, {
    method: "POST",
    apiKey,
  });
}

export async function listAuditEvents({
  apiKey,
  limit = 20,
}: {
  apiKey: string;
  limit?: number;
}): Promise<AuditEventRead[]> {
  return apiRequest<AuditEventRead[]>("/audit-events", {
    apiKey,
    query: { limit },
  });
}

async function apiRequest<T>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  const url = buildUrl(path, options.query);
  const headers: HeadersInit = {};
  let body: BodyInit | undefined;

  if (options.apiKey?.trim()) {
    headers["X-API-Key"] = options.apiKey.trim();
  }

  if (options.body instanceof FormData) {
    body = options.body;
  } else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }

  const response = await fetch(url, {
    method: options.method ?? "GET",
    headers,
    body,
    cache: "no-store",
  });

  const responseBody = await parseResponseBody(response);

  if (!response.ok) {
    throw new ApiError(
      response.status,
      formatApiDetail(response.status, responseBody),
      responseBody,
    );
  }

  return responseBody as T;
}

function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const url = new URL(`${API_BASE_URL}${normalizedPath}`);

  if (query) {
    Object.entries(query).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        url.searchParams.set(key, String(value));
      }
    });
  }

  return url.toString();
}

async function parseResponseBody(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") ?? "";

  if (!contentType.includes("application/json")) {
    const text = await response.text();
    return text || null;
  }

  return response.json();
}

function formatApiDetail(status: number, detail: unknown): string {
  if (isObjectWithDetail(detail)) {
    return formatApiDetail(status, detail.detail);
  }

  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }

  if (Array.isArray(detail)) {
    return detail
      .map((item) =>
        typeof item === "string" ? item : JSON.stringify(item, null, 0),
      )
      .join("; ");
  }

  if (detail && typeof detail === "object") {
    return JSON.stringify(detail);
  }

  return `Request failed with HTTP ${status}.`;
}

function isObjectWithDetail(value: unknown): value is { detail: unknown } {
  return Boolean(value && typeof value === "object" && "detail" in value);
}
