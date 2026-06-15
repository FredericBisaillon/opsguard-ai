"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  API_BASE_URL,
  ApiError,
  answerQuestion,
  chunkDocument,
  clearStoredApiKey,
  dismissReviewTask,
  embedDocument,
  extractDocumentText,
  getHealth,
  getStoredApiKey,
  listAuditEvents,
  listDocuments,
  listReviewTasks,
  saveStoredApiKey,
  suggestReviewTask,
  uploadDocument,
  type AnswerResponse,
  type AuditEventRead,
  type DocumentRead,
  type ReviewTaskRead,
  type ReviewTaskStatus,
  type ReviewTaskSuggestionResponse,
} from "@/lib/api";

type LoadState = "idle" | "loading" | "success" | "error";
type DocumentAction = "extract" | "chunk" | "embed";

const REVIEW_TASK_STATUSES: Array<{
  label: string;
  value: ReviewTaskStatus | "";
}> = [
  { label: "All statuses", value: "" },
  { label: "Open", value: "open" },
  { label: "In progress", value: "in_progress" },
  { label: "Resolved", value: "resolved" },
  { label: "Dismissed", value: "dismissed" },
];

const DOCUMENT_ACTION_LABELS: Record<DocumentAction, string> = {
  extract: "Extract text",
  chunk: "Chunk",
  embed: "Embed",
};

export function ReviewConsole() {
  const [apiKey, setApiKey] = useState("");
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [apiKeyLoaded, setApiKeyLoaded] = useState(false);

  const [healthState, setHealthState] = useState<LoadState>("idle");
  const [healthError, setHealthError] = useState("");

  const [documents, setDocuments] = useState<DocumentRead[]>([]);
  const [documentsState, setDocumentsState] = useState<LoadState>("idle");
  const [documentsError, setDocumentsError] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadTitle, setUploadTitle] = useState("");
  const [uploadState, setUploadState] = useState<LoadState>("idle");
  const [uploadError, setUploadError] = useState("");
  const [uploadMessage, setUploadMessage] = useState("");
  const [uploadInputKey, setUploadInputKey] = useState(0);
  const [documentActionKey, setDocumentActionKey] = useState("");
  const [documentActionError, setDocumentActionError] = useState("");
  const [documentActionMessage, setDocumentActionMessage] = useState("");

  const [answerQuery, setAnswerQuery] = useState("");
  const [answerDocumentId, setAnswerDocumentId] = useState("");
  const [answerTopK, setAnswerTopK] = useState("5");
  const [answerState, setAnswerState] = useState<LoadState>("idle");
  const [answerError, setAnswerError] = useState("");
  const [answerResult, setAnswerResult] = useState<AnswerResponse | null>(null);

  const [reviewQuery, setReviewQuery] = useState("");
  const [reviewDocumentId, setReviewDocumentId] = useState("");
  const [reviewTopK, setReviewTopK] = useState("5");
  const [reviewAutoCreate, setReviewAutoCreate] = useState(false);
  const [reviewState, setReviewState] = useState<LoadState>("idle");
  const [reviewError, setReviewError] = useState("");
  const [reviewResult, setReviewResult] =
    useState<ReviewTaskSuggestionResponse | null>(null);

  const [taskDocumentFilter, setTaskDocumentFilter] = useState("");
  const [taskStatusFilter, setTaskStatusFilter] =
    useState<ReviewTaskStatus | "">("open");
  const [tasks, setTasks] = useState<ReviewTaskRead[]>([]);
  const [tasksState, setTasksState] = useState<LoadState>("idle");
  const [tasksError, setTasksError] = useState("");
  const [dismissingTaskId, setDismissingTaskId] = useState<number | null>(null);

  const [auditEvents, setAuditEvents] = useState<AuditEventRead[]>([]);
  const [auditState, setAuditState] = useState<LoadState>("idle");
  const [auditError, setAuditError] = useState("");

  const hasApiKey = useMemo(() => apiKey.trim().length > 0, [apiKey]);

  const loadHealth = useCallback(async () => {
    setHealthState("loading");
    setHealthError("");

    try {
      await getHealth();
      setHealthState("success");
    } catch (error) {
      setHealthState("error");
      setHealthError(getErrorMessage(error));
    }
  }, []);

  const loadDocuments = useCallback(async (key = apiKey) => {
    if (!key.trim()) {
      setDocuments([]);
      setDocumentsState("idle");
      return;
    }

    setDocumentsState("loading");
    setDocumentsError("");

    try {
      setDocuments(await listDocuments(key));
      setDocumentsState("success");
    } catch (error) {
      setDocumentsState("error");
      setDocumentsError(getErrorMessage(error));
    }
  }, [apiKey]);

  const loadTasks = useCallback(async (key = apiKey) => {
    if (!key.trim()) {
      setTasks([]);
      setTasksState("idle");
      return;
    }

    setTasksState("loading");
    setTasksError("");

    try {
      setTasks(
        await listReviewTasks({
          apiKey: key,
          documentId: parseOptionalPositiveInt(taskDocumentFilter),
          status: taskStatusFilter || undefined,
        }),
      );
      setTasksState("success");
    } catch (error) {
      setTasksState("error");
      setTasksError(getErrorMessage(error));
    }
  }, [apiKey, taskDocumentFilter, taskStatusFilter]);

  const loadAuditEvents = useCallback(async (key = apiKey) => {
    if (!key.trim()) {
      setAuditEvents([]);
      setAuditState("idle");
      return;
    }

    setAuditState("loading");
    setAuditError("");

    try {
      setAuditEvents(await listAuditEvents({ apiKey: key, limit: 20 }));
      setAuditState("success");
    } catch (error) {
      setAuditState("error");
      setAuditError(getErrorMessage(error));
    }
  }, [apiKey]);

  const refreshProtectedData = useCallback(async (key = apiKey) => {
    await Promise.all([
      loadDocuments(key),
      loadTasks(key),
      loadAuditEvents(key),
    ]);
  }, [apiKey, loadAuditEvents, loadDocuments, loadTasks]);

  useEffect(() => {
    queueMicrotask(() => {
      setApiKey(getStoredApiKey());
      setApiKeyLoaded(true);
      void loadHealth();
    });
  }, [loadHealth]);

  useEffect(() => {
    queueMicrotask(() => {
      if (!apiKeyLoaded) {
        return;
      }

      if (hasApiKey) {
        void refreshProtectedData(apiKey);
        return;
      }

      setDocuments([]);
      setTasks([]);
      setAuditEvents([]);
      setDocumentsState("idle");
      setTasksState("idle");
      setAuditState("idle");
    });
  }, [apiKey, apiKeyLoaded, hasApiKey, refreshProtectedData]);

  useEffect(() => {
    queueMicrotask(() => {
      if (documents.length === 0) {
        setReviewDocumentId("");
        return;
      }

      setReviewDocumentId((current) => current || String(documents[0].id));
    });
  }, [documents]);

  const handleSaveApiKey = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const trimmedApiKey = apiKeyInput.trim();

    if (!trimmedApiKey) {
      clearStoredApiKey();
      setApiKey("");
      setApiKeyInput("");
      return;
    }

    saveStoredApiKey(trimmedApiKey);
    setApiKey(trimmedApiKey);
    setApiKeyInput("");
  };

  const handleClearApiKey = () => {
    clearStoredApiKey();
    setApiKey("");
    setApiKeyInput("");
    setUploadMessage("");
    setDocumentActionMessage("");
  };

  const handleUpload = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!apiKey.trim()) {
      setUploadError("Save an API key before uploading a document.");
      setUploadState("error");
      return;
    }

    if (!uploadFile) {
      setUploadError("Choose a PDF, Markdown, or text file first.");
      setUploadState("error");
      return;
    }

    setUploadState("loading");
    setUploadError("");
    setUploadMessage("");

    try {
      const document = await uploadDocument({
        apiKey,
        file: uploadFile,
        title: uploadTitle,
      });
      setUploadState("success");
      setUploadMessage(`Uploaded document #${document.id}: ${document.title}`);
      setUploadFile(null);
      setUploadTitle("");
      setUploadInputKey((current) => current + 1);
      await refreshProtectedData(apiKey);
    } catch (error) {
      setUploadState("error");
      setUploadError(getErrorMessage(error));
    }
  };

  const handleDocumentAction = async (
    documentId: number,
    action: DocumentAction,
  ) => {
    if (!apiKey.trim()) {
      setDocumentActionError("Save an API key before processing documents.");
      return;
    }

    const actionKey = `${documentId}:${action}`;
    setDocumentActionKey(actionKey);
    setDocumentActionError("");
    setDocumentActionMessage("");

    try {
      const result = await runDocumentAction(apiKey, documentId, action);
      setDocumentActionMessage(result.message);
      await Promise.all([loadDocuments(apiKey), loadAuditEvents(apiKey)]);
    } catch (error) {
      setDocumentActionError(getErrorMessage(error));
    } finally {
      setDocumentActionKey("");
    }
  };

  const handleAnswerSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!apiKey.trim()) {
      setAnswerState("error");
      setAnswerError("Save an API key before asking the API.");
      return;
    }

    if (!answerQuery.trim()) {
      setAnswerState("error");
      setAnswerError("Enter a question first.");
      return;
    }

    setAnswerState("loading");
    setAnswerError("");
    setAnswerResult(null);

    try {
      setAnswerResult(
        await answerQuestion({
          apiKey,
          query: answerQuery.trim(),
          documentId: parseOptionalPositiveInt(answerDocumentId),
          topK: parseOptionalPositiveInt(answerTopK),
        }),
      );
      setAnswerState("success");
      await loadAuditEvents(apiKey);
    } catch (error) {
      setAnswerState("error");
      setAnswerError(getErrorMessage(error));
    }
  };

  const handleReviewSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const documentId = parseOptionalPositiveInt(reviewDocumentId);

    if (!apiKey.trim()) {
      setReviewState("error");
      setReviewError("Save an API key before asking for a review suggestion.");
      return;
    }

    if (!documentId) {
      setReviewState("error");
      setReviewError("Select a document for the AI review suggestion.");
      return;
    }

    if (!reviewQuery.trim()) {
      setReviewState("error");
      setReviewError("Enter a review query first.");
      return;
    }

    setReviewState("loading");
    setReviewError("");
    setReviewResult(null);

    try {
      setReviewResult(
        await suggestReviewTask({
          apiKey,
          query: reviewQuery.trim(),
          documentId,
          topK: parseOptionalPositiveInt(reviewTopK),
          autoCreate: reviewAutoCreate,
        }),
      );
      setReviewState("success");
      await Promise.all([loadTasks(apiKey), loadAuditEvents(apiKey)]);
    } catch (error) {
      setReviewState("error");
      setReviewError(getErrorMessage(error));
    }
  };

  const handleDismissTask = async (taskId: number) => {
    if (!apiKey.trim()) {
      return;
    }

    setDismissingTaskId(taskId);
    setTasksError("");

    try {
      await dismissReviewTask(apiKey, taskId);
      await Promise.all([loadTasks(apiKey), loadAuditEvents(apiKey)]);
    } catch (error) {
      setTasksError(getErrorMessage(error));
    } finally {
      setDismissingTaskId(null);
    }
  };

  return (
    <main className="min-h-screen bg-zinc-100 text-zinc-950">
      <div className="mx-auto flex w-full max-w-[1500px] flex-col gap-4 px-4 py-4 sm:px-6 lg:px-8">
        <header className="flex flex-col gap-3 border-b border-zinc-300 pb-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald-700">
              Secure AI Document Review Platform
            </p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight">
              OpsGuard AI
            </h1>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-sm">
            <StatusPill
              label={healthState === "success" ? "API online" : "API offline"}
              tone={healthState === "success" ? "green" : "amber"}
            />
            <StatusPill
              label={hasApiKey ? "API key configured" : "API key missing"}
              tone={hasApiKey ? "green" : "red"}
            />
            <button
              type="button"
              className={secondaryButtonClass}
              onClick={() => void loadHealth()}
              disabled={healthState === "loading"}
            >
              {healthState === "loading" ? "Checking..." : "Check API"}
            </button>
          </div>
        </header>

        <section className="grid gap-3 rounded-lg border border-zinc-300 bg-white p-4 shadow-sm lg:grid-cols-[1fr_auto] lg:items-end">
          <div>
            <div className="flex flex-wrap items-baseline gap-3">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-700">
                Local API key
              </h2>
              <span className="text-xs text-zinc-500">
                Demo/dev only. Stored in this browser, never displayed after
                save.
              </span>
            </div>
            <form
              className="mt-3 flex flex-col gap-2 sm:flex-row"
              onSubmit={handleSaveApiKey}
            >
              <input
                className={inputClass}
                type="password"
                value={apiKeyInput}
                placeholder={
                  hasApiKey
                    ? "Configured - enter a replacement key"
                    : "Enter X-API-Key"
                }
                autoComplete="off"
                onChange={(event) => setApiKeyInput(event.target.value)}
              />
              <div className="flex gap-2">
                <button type="submit" className={primaryButtonClass}>
                  Save key
                </button>
                <button
                  type="button"
                  className={secondaryButtonClass}
                  onClick={handleClearApiKey}
                  disabled={!hasApiKey && !apiKeyInput}
                >
                  Clear
                </button>
              </div>
            </form>
          </div>
          <div className="text-xs text-zinc-500 lg:text-right">
            <div>Backend URL</div>
            <code className="font-mono text-zinc-800">{API_BASE_URL}</code>
          </div>
        </section>

        {healthError ? (
          <InlineAlert tone="amber" message={`Health check: ${healthError}`} />
        ) : null}

        <section className="grid gap-4 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.2fr)_minmax(0,1fr)]">
          <Panel
            title="Documents"
            action={
              <button
                type="button"
                className={secondaryButtonClass}
                onClick={() => void loadDocuments(apiKey)}
                disabled={!hasApiKey || documentsState === "loading"}
              >
                Refresh
              </button>
            }
          >
            <form className="grid gap-2" onSubmit={handleUpload}>
              <input
                key={uploadInputKey}
                className={fileInputClass}
                type="file"
                accept=".pdf,.md,.markdown,.txt,text/plain,application/pdf"
                disabled={!hasApiKey || uploadState === "loading"}
                onChange={(event) =>
                  setUploadFile(event.target.files?.[0] ?? null)
                }
              />
              <input
                className={inputClass}
                type="text"
                value={uploadTitle}
                placeholder="Optional title"
                disabled={!hasApiKey || uploadState === "loading"}
                onChange={(event) => setUploadTitle(event.target.value)}
              />
              <button
                type="submit"
                className={primaryButtonClass}
                disabled={!hasApiKey || uploadState === "loading"}
              >
                {uploadState === "loading" ? "Uploading..." : "Upload document"}
              </button>
            </form>

            <SectionMessages
              disabled={!hasApiKey}
              disabledMessage="Save an API key to load and upload documents."
              error={uploadError || documentsError || documentActionError}
              message={uploadMessage || documentActionMessage}
            />

            <ListState state={documentsState} itemCount={documents.length}>
              <div className="divide-y divide-zinc-200">
                {documents.map((document) => (
                  <article key={document.id} className="py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="truncate text-sm font-semibold">
                            #{document.id} {document.title}
                          </h3>
                          <StatusPill
                            label={document.status}
                            tone={documentStatusTone(document.status)}
                          />
                        </div>
                        <p className="mt-1 truncate text-xs text-zinc-500">
                          {document.source_type} · {document.source_path}
                        </p>
                        <p className="mt-1 text-xs text-zinc-500">
                          Updated {formatDate(document.updated_at)}
                        </p>
                      </div>
                    </div>

                    <div className="mt-3 flex flex-wrap gap-2">
                      {(["extract", "chunk", "embed"] as DocumentAction[]).map(
                        (action) => {
                          const actionKey = `${document.id}:${action}`;

                          return (
                            <button
                              key={action}
                              type="button"
                              className={miniButtonClass}
                              disabled={
                                !hasApiKey || documentActionKey === actionKey
                              }
                              onClick={() =>
                                void handleDocumentAction(document.id, action)
                              }
                            >
                              {documentActionKey === actionKey
                                ? "Running..."
                                : DOCUMENT_ACTION_LABELS[action]}
                            </button>
                          );
                        },
                      )}
                    </div>
                  </article>
                ))}
              </div>
            </ListState>
          </Panel>

          <Panel title="Ask / Review">
            <form className="grid gap-3" onSubmit={handleAnswerSubmit}>
              <div>
                <label className={labelClass} htmlFor="answer-query">
                  RAG question
                </label>
                <textarea
                  id="answer-query"
                  className={textareaClass}
                  value={answerQuery}
                  placeholder="Ask a question about embedded documents..."
                  disabled={!hasApiKey || answerState === "loading"}
                  onChange={(event) => setAnswerQuery(event.target.value)}
                />
              </div>
              <div className="grid gap-2 sm:grid-cols-[1fr_100px]">
                <select
                  className={inputClass}
                  value={answerDocumentId}
                  disabled={!hasApiKey || answerState === "loading"}
                  onChange={(event) => setAnswerDocumentId(event.target.value)}
                >
                  <option value="">All documents</option>
                  {documents.map((document) => (
                    <option key={document.id} value={document.id}>
                      #{document.id} {document.title}
                    </option>
                  ))}
                </select>
                <input
                  className={inputClass}
                  type="number"
                  min={1}
                  value={answerTopK}
                  disabled={!hasApiKey || answerState === "loading"}
                  onChange={(event) => setAnswerTopK(event.target.value)}
                  aria-label="Answer top K"
                />
              </div>
              <button
                type="submit"
                className={primaryButtonClass}
                disabled={!hasApiKey || answerState === "loading"}
              >
                {answerState === "loading" ? "Asking..." : "Ask RAG"}
              </button>
            </form>

            <ResultBlock
              state={answerState}
              error={answerError}
              emptyMessage="Answers with citations will appear here."
            >
              {answerResult ? <AnswerResult result={answerResult} /> : null}
            </ResultBlock>

            <div className="my-4 border-t border-zinc-200" />

            <form className="grid gap-3" onSubmit={handleReviewSubmit}>
              <div>
                <label className={labelClass} htmlFor="review-query">
                  AI review suggestion
                </label>
                <textarea
                  id="review-query"
                  className={textareaClass}
                  value={reviewQuery}
                  placeholder="Ask for a risk, control, compliance, or review task..."
                  disabled={!hasApiKey || reviewState === "loading"}
                  onChange={(event) => setReviewQuery(event.target.value)}
                />
              </div>
              <div className="grid gap-2 sm:grid-cols-[1fr_100px]">
                <select
                  className={inputClass}
                  value={reviewDocumentId}
                  disabled={!hasApiKey || reviewState === "loading"}
                  onChange={(event) => setReviewDocumentId(event.target.value)}
                >
                  <option value="">Select document</option>
                  {documents.map((document) => (
                    <option key={document.id} value={document.id}>
                      #{document.id} {document.title}
                    </option>
                  ))}
                </select>
                <input
                  className={inputClass}
                  type="number"
                  min={1}
                  value={reviewTopK}
                  disabled={!hasApiKey || reviewState === "loading"}
                  onChange={(event) => setReviewTopK(event.target.value)}
                  aria-label="Review top K"
                />
              </div>
              <label className="flex items-center gap-2 text-sm text-zinc-700">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-zinc-300"
                  checked={reviewAutoCreate}
                  disabled={!hasApiKey || reviewState === "loading"}
                  onChange={(event) =>
                    setReviewAutoCreate(event.target.checked)
                  }
                />
                Auto-create task if the backend validates the suggestion
              </label>
              <button
                type="submit"
                className={primaryButtonClass}
                disabled={!hasApiKey || reviewState === "loading"}
              >
                {reviewState === "loading" ? "Reviewing..." : "Suggest task"}
              </button>
            </form>

            <ResultBlock
              state={reviewState}
              error={reviewError}
              emptyMessage="Validated AI review suggestions will appear here."
            >
              {reviewResult ? <ReviewResult result={reviewResult} /> : null}
            </ResultBlock>
          </Panel>

          <Panel
            title="Tasks / Audit"
            action={
              <button
                type="button"
                className={secondaryButtonClass}
                onClick={() =>
                  void Promise.all([loadTasks(apiKey), loadAuditEvents(apiKey)])
                }
                disabled={!hasApiKey || tasksState === "loading"}
              >
                Refresh
              </button>
            }
          >
            <div className="grid gap-2 sm:grid-cols-2">
              <select
                className={inputClass}
                value={taskDocumentFilter}
                disabled={!hasApiKey}
                onChange={(event) => setTaskDocumentFilter(event.target.value)}
              >
                <option value="">All documents</option>
                {documents.map((document) => (
                  <option key={document.id} value={document.id}>
                    #{document.id} {document.title}
                  </option>
                ))}
              </select>
              <select
                className={inputClass}
                value={taskStatusFilter}
                disabled={!hasApiKey}
                onChange={(event) =>
                  setTaskStatusFilter(event.target.value as ReviewTaskStatus | "")
                }
              >
                {REVIEW_TASK_STATUSES.map((status) => (
                  <option key={status.value || "all"} value={status.value}>
                    {status.label}
                  </option>
                ))}
              </select>
            </div>

            <SectionMessages
              disabled={!hasApiKey}
              disabledMessage="Save an API key to load review tasks."
              error={tasksError}
            />

            <ListState state={tasksState} itemCount={tasks.length}>
              <div className="divide-y divide-zinc-200">
                {tasks.map((task) => (
                  <article key={task.id} className="py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="text-sm font-semibold">
                            #{task.id} {task.title}
                          </h3>
                          <StatusPill
                            label={task.severity}
                            tone={severityTone(task.severity)}
                          />
                          <StatusPill
                            label={task.status}
                            tone={
                              task.status === "dismissed" ? "zinc" : "blue"
                            }
                          />
                        </div>
                        {task.description ? (
                          <p className="mt-1 line-clamp-3 text-sm text-zinc-600">
                            {task.description}
                          </p>
                        ) : null}
                        <p className="mt-1 text-xs text-zinc-500">
                          Document #{task.document_id}
                          {task.chunk_id ? ` · Chunk #${task.chunk_id}` : ""}
                          {" · "}
                          {task.source}
                        </p>
                      </div>
                      <button
                        type="button"
                        className={miniButtonClass}
                        disabled={
                          !hasApiKey ||
                          task.status === "dismissed" ||
                          dismissingTaskId === task.id
                        }
                        onClick={() => void handleDismissTask(task.id)}
                      >
                        {dismissingTaskId === task.id ? "Dismissing..." : "Dismiss"}
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            </ListState>

            <div className="my-4 border-t border-zinc-200" />

            <div className="flex items-center justify-between gap-2">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-zinc-700">
                Recent audit events
              </h3>
              <span className="text-xs text-zinc-500">limit 20</span>
            </div>

            <SectionMessages error={auditError} />

            <ListState state={auditState} itemCount={auditEvents.length}>
              <div className="divide-y divide-zinc-200">
                {auditEvents.map((event) => (
                  <article key={event.id} className="py-3 text-sm">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold">{event.event_type}</span>
                      <StatusPill
                        label={event.status}
                        tone={auditTone(event.status)}
                      />
                    </div>
                    <p className="mt-1 text-zinc-600">{event.summary}</p>
                    <p className="mt-1 text-xs text-zinc-500">
                      {formatDate(event.created_at)}
                      {event.document_id
                        ? ` · Document #${event.document_id}`
                        : ""}
                      {event.review_task_id
                        ? ` · Task #${event.review_task_id}`
                        : ""}
                    </p>
                  </article>
                ))}
              </div>
            </ListState>
          </Panel>
        </section>
      </div>
    </main>
  );
}

function Panel({
  title,
  action,
  children,
}: {
  title: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-lg border border-zinc-300 bg-white p-4 shadow-sm">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-700">
          {title}
        </h2>
        {action}
      </div>
      <div className="grid gap-4">{children}</div>
    </section>
  );
}

function StatusPill({
  label,
  tone,
}: {
  label: string;
  tone: "amber" | "blue" | "green" | "red" | "zinc";
}) {
  const toneClass = {
    amber: "border-amber-200 bg-amber-50 text-amber-800",
    blue: "border-blue-200 bg-blue-50 text-blue-800",
    green: "border-emerald-200 bg-emerald-50 text-emerald-800",
    red: "border-red-200 bg-red-50 text-red-800",
    zinc: "border-zinc-200 bg-zinc-100 text-zinc-700",
  }[tone];

  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-1 text-xs font-medium ${toneClass}`}
    >
      {label}
    </span>
  );
}

function SectionMessages({
  disabled,
  disabledMessage,
  error,
  message,
}: {
  disabled?: boolean;
  disabledMessage?: string;
  error?: string;
  message?: string;
}) {
  if (disabled && disabledMessage) {
    return <InlineAlert tone="zinc" message={disabledMessage} />;
  }

  if (error) {
    return <InlineAlert tone="red" message={error} />;
  }

  if (message) {
    return <InlineAlert tone="green" message={message} />;
  }

  return null;
}

function InlineAlert({
  message,
  tone,
}: {
  message: string;
  tone: "amber" | "green" | "red" | "zinc";
}) {
  const toneClass = {
    amber: "border-amber-200 bg-amber-50 text-amber-800",
    green: "border-emerald-200 bg-emerald-50 text-emerald-800",
    red: "border-red-200 bg-red-50 text-red-800",
    zinc: "border-zinc-200 bg-zinc-50 text-zinc-700",
  }[tone];

  return (
    <div className={`rounded-md border px-3 py-2 text-sm ${toneClass}`}>
      {message}
    </div>
  );
}

function ListState({
  state,
  itemCount,
  children,
}: {
  state: LoadState;
  itemCount: number;
  children: ReactNode;
}) {
  if (state === "loading") {
    return <p className="text-sm text-zinc-500">Loading...</p>;
  }

  if (state === "success" && itemCount === 0) {
    return <p className="text-sm text-zinc-500">No records yet.</p>;
  }

  if (state === "idle") {
    return <p className="text-sm text-zinc-500">Waiting for API key.</p>;
  }

  if (state === "error") {
    return null;
  }

  return <>{children}</>;
}

function ResultBlock({
  state,
  error,
  emptyMessage,
  children,
}: {
  state: LoadState;
  error: string;
  emptyMessage: string;
  children: ReactNode;
}) {
  if (state === "loading") {
    return <p className="text-sm text-zinc-500">Working...</p>;
  }

  if (state === "error") {
    return <InlineAlert tone="red" message={error} />;
  }

  if (state === "success") {
    return <div className="rounded-md border border-zinc-200 p-3">{children}</div>;
  }

  return <p className="text-sm text-zinc-500">{emptyMessage}</p>;
}

function AnswerResult({ result }: { result: AnswerResponse }) {
  return (
    <div className="grid gap-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <StatusPill
          label={result.is_answered ? "answered" : "abstained"}
          tone={result.is_answered ? "green" : "amber"}
        />
        <span className="text-xs text-zinc-500">
          {result.retrieved_chunk_count} chunks retrieved
        </span>
      </div>
      <p className="whitespace-pre-wrap text-zinc-800">{result.answer}</p>

      {result.security_warnings?.length ? (
        <InlineAlert
          tone="amber"
          message={`Security warning: ${result.security_warnings.join("; ")}`}
        />
      ) : null}

      <CitationList citations={result.citations} />
    </div>
  );
}

function ReviewResult({ result }: { result: ReviewTaskSuggestionResponse }) {
  return (
    <div className="grid gap-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <StatusPill
          label={result.suggested ? "suggested" : "no suggestion"}
          tone={result.suggested ? "green" : "amber"}
        />
        <StatusPill
          label={result.created ? "created" : "not created"}
          tone={result.created ? "green" : "zinc"}
        />
        <span className="text-xs text-zinc-500">{result.model}</span>
      </div>

      <p className="text-zinc-700">{result.message}</p>

      {result.suggestion ? (
        <div className="grid gap-2 border-l-2 border-emerald-500 pl-3">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-semibold">{result.suggestion.title}</h3>
            <StatusPill
              label={result.suggestion.severity}
              tone={severityTone(result.suggestion.severity)}
            />
          </div>
          {result.suggestion.description ? (
            <p className="text-zinc-700">{result.suggestion.description}</p>
          ) : null}
          <p className="text-zinc-600">
            <span className="font-medium">Evidence:</span>{" "}
            {result.suggestion.evidence}
          </p>
          <p className="text-zinc-600">
            <span className="font-medium">Reason:</span>{" "}
            {result.suggestion.reason}
          </p>
        </div>
      ) : null}

      {result.review_task ? (
        <InlineAlert
          tone="green"
          message={`Created review task #${result.review_task.id}`}
        />
      ) : null}

      <CitationList citations={result.citations} />
    </div>
  );
}

function CitationList({
  citations,
}: {
  citations: Array<{
    source_id: string;
    document_id: number;
    document_title: string;
    chunk_id: number;
    chunk_index: number;
    section_title: string | null;
    excerpt: string;
    similarity_score: number;
  }>;
}) {
  if (citations.length === 0) {
    return <p className="text-xs text-zinc-500">No citations returned.</p>;
  }

  return (
    <div className="grid gap-2">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
        Citations
      </h4>
      {citations.map((citation) => (
        <div
          key={`${citation.source_id}:${citation.chunk_id}`}
          className="rounded-md bg-zinc-50 p-2 text-xs text-zinc-700"
        >
          <div className="font-medium text-zinc-900">
            {citation.source_id} · {citation.document_title} · chunk{" "}
            {citation.chunk_index}
          </div>
          {citation.section_title ? (
            <div className="mt-1 text-zinc-500">{citation.section_title}</div>
          ) : null}
          <p className="mt-1 line-clamp-4">{citation.excerpt}</p>
          <div className="mt-1 text-zinc-500">
            similarity {citation.similarity_score.toFixed(3)}
          </div>
        </div>
      ))}
    </div>
  );
}

async function runDocumentAction(
  apiKey: string,
  documentId: number,
  action: DocumentAction,
): Promise<{ message: string }> {
  if (action === "extract") {
    return extractDocumentText(apiKey, documentId);
  }

  if (action === "chunk") {
    return chunkDocument(apiKey, documentId);
  }

  return embedDocument(apiKey, documentId);
}

function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 404) {
    return "Endpoint unavailable on this backend.";
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "Unexpected error.";
}

function parseOptionalPositiveInt(value: string): number | undefined {
  const trimmedValue = value.trim();

  if (!trimmedValue) {
    return undefined;
  }

  const parsedValue = Number.parseInt(trimmedValue, 10);
  return Number.isFinite(parsedValue) && parsedValue > 0
    ? parsedValue
    : undefined;
}

function formatDate(value: string): string {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function documentStatusTone(status: string): "amber" | "blue" | "green" | "red" {
  if (status.includes("failed")) {
    return "red";
  }

  if (status === "embedded" || status === "processed") {
    return "green";
  }

  if (
    status === "extracting" ||
    status === "chunking" ||
    status === "embedding"
  ) {
    return "blue";
  }

  return "amber";
}

function severityTone(
  severity: string,
): "amber" | "blue" | "green" | "red" | "zinc" {
  if (severity === "critical" || severity === "high") {
    return "red";
  }

  if (severity === "medium") {
    return "amber";
  }

  return "green";
}

function auditTone(status: string): "amber" | "blue" | "green" | "red" | "zinc" {
  if (status === "success") {
    return "green";
  }

  if (status === "failed" || status === "rejected") {
    return "red";
  }

  return "zinc";
}

const primaryButtonClass =
  "inline-flex min-h-10 items-center justify-center rounded-md bg-zinc-950 px-3 py-2 text-sm font-medium text-white transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:bg-zinc-300 disabled:text-zinc-500";

const secondaryButtonClass =
  "inline-flex min-h-10 items-center justify-center rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm font-medium text-zinc-800 transition hover:bg-zinc-50 disabled:cursor-not-allowed disabled:text-zinc-400";

const miniButtonClass =
  "inline-flex min-h-8 items-center justify-center rounded-md border border-zinc-300 bg-white px-2.5 py-1.5 text-xs font-medium text-zinc-800 transition hover:bg-zinc-50 disabled:cursor-not-allowed disabled:text-zinc-400";

const inputClass =
  "min-h-10 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-950 outline-none transition placeholder:text-zinc-400 focus:border-emerald-600 focus:ring-2 focus:ring-emerald-100 disabled:cursor-not-allowed disabled:bg-zinc-100 disabled:text-zinc-500";

const fileInputClass =
  "block w-full rounded-md border border-zinc-300 bg-white text-sm text-zinc-700 file:mr-3 file:min-h-10 file:border-0 file:bg-zinc-950 file:px-3 file:text-sm file:font-medium file:text-white disabled:cursor-not-allowed disabled:bg-zinc-100 disabled:text-zinc-500";

const textareaClass =
  "min-h-24 w-full resize-y rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-950 outline-none transition placeholder:text-zinc-400 focus:border-emerald-600 focus:ring-2 focus:ring-emerald-100 disabled:cursor-not-allowed disabled:bg-zinc-100 disabled:text-zinc-500";

const labelClass = "mb-1 block text-sm font-medium text-zinc-700";
