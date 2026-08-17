/**
 * API client utility for communicating with the backend.
 * Uses the fetch API with JWT-based authentication.
 */

import type {
  AuthResponse,
  ChatMessage,
  ChatSession,
  FamilyMember,
  RunFamily,
  User,
  WorkflowRun,
  WorkflowType,
} from "@/types/index";
import { ENV } from "@/lib/env";

const BASE_URL = ENV.API_URL;

const TOKEN_KEY = "auth_token";

// --- Token management ---

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

/**
 * Log the current user out: ask the backend to revoke the JWT, then drop it
 * locally. Network failure or an already-revoked token must not block the
 * client-side clear — the user is logging out either way, so we swallow
 * errors and always run clearToken() in the finally block. Pair this with a
 * post-logout redirect at the call site (the dashboard's handleLogout does so).
 *
 * Pass an empty string when no token is available; the request will 401 and
 * the catch will swallow it. (See the JWT-expired close handler in
 * useHandoffSocket.ts which legitimately calls clearToken() directly — the
 * token is already invalid, so /logout would just 401.)
 */
export async function logout(token: string): Promise<void> {
  try {
    await fetch(`${BASE_URL}/api/auth/logout`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });
  } catch {
    // best-effort — see the docstring
  } finally {
    clearToken();
  }
}

// --- HTTP helpers ---

class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    const message =
      typeof detail === "string" ? detail : JSON.stringify(detail);
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

// BUG-013 Part B — fail-fast timeout for the REST client. When the browser's
// ~6-connections-per-origin pool is saturated (per-run SSE streams), a call can
// hang forever with no free socket → a silent idle screen. Wrap every request in
// an AbortController that aborts after REQUEST_TIMEOUT_MS so a starved/hung call
// rejects with a typed, catchable ApiError instead of hanging. Generous (~30s) so
// it never aborts a legitimately-slow brief ingest / large-deliverable fetch.
const REQUEST_TIMEOUT_MS = 30_000;

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${BASE_URL}${path}`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  let response: Response;
  try {
    // No current request() caller passes its own signal, so a direct assignment
    // is safe.
    response = await fetch(url, { ...options, signal: controller.signal });
  } catch (err) {
    // On abort the fetch throws a DOMException AbortError — translate it to a
    // typed, catchable ApiError (status 0) so callers surface a clear timeout
    // instead of an opaque hang (matches the reopen catch at page.tsx).
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(0, `Request timeout after ${REQUEST_TIMEOUT_MS}ms (aborted)`);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }

  if (!response.ok) {
    const body = await response.json().catch(() => ({
      detail: response.statusText,
    }));
    throw new ApiError(response.status, body.detail ?? body);
  }

  return response.json() as Promise<T>;
}

function authHeaders(token: string): HeadersInit {
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
}

// --- Auth API ---

export async function register(
  email: string,
  password: string
): Promise<AuthResponse> {
  const data = await request<AuthResponse>("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  setToken(data.token);
  return data;
}

export async function login(
  email: string,
  password: string
): Promise<AuthResponse> {
  const data = await request<AuthResponse>("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  setToken(data.token);
  return data;
}

export async function getMe(token: string): Promise<User> {
  return request<User>("/api/auth/me", {
    method: "GET",
    headers: authHeaders(token),
  });
}

// --- Chat API ---

/** Raw chat session shape from the backend (snake_case fields) */
interface RawChatSession {
  id: string;
  title: string;
  last_activity: string;
  created_at: string;
}

/** Ensure a timestamp string is treated as UTC (append Z if missing) */
function ensureUTC(timestamp: string): string {
  if (!timestamp) return timestamp;
  // If it already has timezone info (Z or +/-offset), leave it
  if (/Z$|[+-]\d{2}:\d{2}$/.test(timestamp)) return timestamp;
  // Otherwise append Z to indicate UTC
  return timestamp + "Z";
}

/** Normalize a backend chat session (snake_case) to frontend format (camelCase) */
function normalizeChatSession(raw: RawChatSession): ChatSession {
  return {
    id: raw.id,
    title: raw.title,
    lastActivity: ensureUTC(raw.last_activity),
    createdAt: ensureUTC(raw.created_at),
  };
}

/** Raw message shape from the backend (snake_case fields) */
export interface RawMessageResponse {
  id: string;
  chat_session_id: string;
  role: string;
  content: string;
  created_at: string;
}

export interface ChatDetailResponse {
  id: string;
  title: string;
  last_activity: string;
  created_at: string;
  messages: RawMessageResponse[];
  final_output: string | null;
}

export async function createChat(
  token: string,
  title?: string
): Promise<ChatSession> {
  const raw = await request<RawChatSession>("/api/chats", {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ title: title ?? null }),
  });
  return normalizeChatSession(raw);
}

export async function getChats(token: string): Promise<ChatSession[]> {
  const raw = await request<RawChatSession[]>("/api/chats", {
    method: "GET",
    headers: authHeaders(token),
  });
  return raw.map(normalizeChatSession);
}

export async function getChat(
  token: string,
  id: string
): Promise<ChatDetailResponse> {
  return request<ChatDetailResponse>(`/api/chats/${id}`, {
    method: "GET",
    headers: authHeaders(token),
  });
}

export async function addMessage(
  token: string,
  chatId: string,
  content: string,
  role: string = "user"
): Promise<ChatMessage> {
  return request<ChatMessage>(`/api/chats/${chatId}/messages`, {
    method: "PUT",
    headers: authHeaders(token),
    body: JSON.stringify({ content, role }),
  });
}

export async function deleteChat(
  token: string,
  chatId: string
): Promise<void> {
  const url = `${BASE_URL}/api/chats/${chatId}`;
  const response = await fetch(url, {
    method: "DELETE",
    headers: authHeaders(token),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({
      detail: response.statusText,
    }));
    throw new ApiError(response.status, body.detail ?? body);
  }
}

export { ApiError };


// --- Workflow API ---

/** Raw workflow run shape from the backend (snake_case fields) */
interface RawWorkflowRun {
  id: string;
  title: string;
  type: string;
  status: string;
  input: string;
  output: string | null;
  agent_outputs: string | null;
  agent_count: number;
  duration: number | null;
  error: string | null;
  token_usage: string | null;
  model_id: string | null;
  // UXFIX-02 (22-03 / D-19): persisted declared/resolved deliverable shape.
  deliverable_mimetype?: string | null;
  deliverable_filename?: string | null;
  // Revision Families (B1 / D1-D2-D7): optional so legacy raw rows still parse.
  parent_run_id?: string | null;
  root_run_id?: string;
  // KAN-130: chaining indicator — set when a run was launched from a prior run's
  // output (chain into). Optional so legacy rows without it still parse.
  source_run_id?: string | null;
  created_at: string;
  completed_at: string | null;
}

/** Normalize a backend workflow run (snake_case) to frontend format (camelCase) */
function normalizeWorkflowRun(raw: RawWorkflowRun): WorkflowRun {
  let agentOutputs: WorkflowRun["agentOutputs"] = undefined;
  if (raw.agent_outputs) {
    try {
      agentOutputs = JSON.parse(raw.agent_outputs);
    } catch { /* ignore parse errors */ }
  }

  let tokenUsage: WorkflowRun["tokenUsage"] = undefined;
  if (raw.token_usage) {
    try {
      tokenUsage = JSON.parse(raw.token_usage);
    } catch { /* ignore parse errors */ }
  }

  return {
    id: raw.id,
    title: raw.title,
    type: raw.type as WorkflowType,
    status: raw.status as WorkflowRun["status"],
    input: raw.input,
    output: raw.output ?? undefined,
    agentOutputs,
    tokenUsage,
    modelId: raw.model_id ?? undefined,
    deliverableMimetype: raw.deliverable_mimetype ?? undefined,
    deliverableFilename: raw.deliverable_filename ?? undefined,
    // Revision Families (B1): a standalone/legacy run with no root is its own
    // root — matches the backend's "standalone run → own id" semantics.
    parentRunId: raw.parent_run_id ?? null,
    rootRunId: raw.root_run_id ?? raw.id,
    // KAN-130: chaining indicator — non-null when launched by chaining from another run.
    sourceRunId: raw.source_run_id ?? null,
    agentCount: raw.agent_count,
    duration: raw.duration ?? undefined,
    error: raw.error ?? undefined,
    createdAt: ensureUTC(raw.created_at),
    completedAt: raw.completed_at ? ensureUTC(raw.completed_at) : undefined,
  };
}

export async function getWorkflows(
  token: string,
  options?: { type?: WorkflowType; limit?: number; offset?: number }
): Promise<{ runs: WorkflowRun[]; total: number }> {
  let path = "/api/runs";
  const params = new URLSearchParams();
  if (options?.type) params.set("type", options.type);
  if (options?.limit) params.set("limit", String(options.limit));
  if (options?.offset) params.set("offset", String(options.offset));
  const qs = params.toString();
  if (qs) path += `?${qs}`;

  const res = await fetch(`${ENV.API_URL}${path}`, {
    method: "GET",
    headers: authHeaders(token),
  });

  if (!res.ok) throw new Error(`Failed to fetch runs: ${res.status}`);

  const raw = (await res.json()) as RawWorkflowRun[];
  const total = parseInt(res.headers.get("X-Total-Count") ?? "0", 10);
  
  return {
    runs: raw.map(normalizeWorkflowRun),
    total,
  };
}

// --- Analytics API (SC-1) ---
//
// Structural mirror of the backend `AnalyticsSummary` Pydantic model
// (backend/app/api/analytics.py) — field-for-field, generic type/model keys
// (SC-001/INV-1: no workflow-name branch). Numbers only.

export interface AnalyticsKpis {
  total: number;
  completed: number;
  failed: number;
  success_rate: number;
}

export interface AnalyticsTokenTotals {
  input: number;
  output: number;
  cache_read: number;
  cache_write: number;
  total: number;
}

export interface AnalyticsDailyBucket {
  date: string;
  total: number;
  completed: number;
  failed: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
}

export interface AnalyticsPipelineRollup {
  type: string;
  count: number;
  total_tokens: number;
  cost: number;
  avg_duration: number;
}

export interface AnalyticsModelRollup {
  model_id: string;
  count: number;
  total_tokens: number;
  cost: number;
}

export interface AnalyticsSummary {
  kpis: AnalyticsKpis;
  daily: AnalyticsDailyBucket[];
  pipelines: AnalyticsPipelineRollup[];
  models: AnalyticsModelRollup[];
  spend: number;
  token_totals: AnalyticsTokenTotals;
  type_avg_duration_sec: Record<string, number>;
}

/**
 * Fetch the owner-scoped, date-scoped analytics summary (38-01). Changing
 * `range` re-queries the server (SC-1 recompute) — no client-side rollup of
 * raw runs. `range` is a UI enum: today|3d|7d|30d|90d|all.
 */
export async function getAnalyticsSummary(
  token: string,
  range: string
): Promise<AnalyticsSummary> {
  return request<AnalyticsSummary>(
    `/api/analytics/summary?range=${encodeURIComponent(range)}`,
    { method: "GET", headers: authHeaders(token) }
  );
}

export async function getWorkflow(
  token: string,
  workflowId: string
): Promise<WorkflowRun> {
  const raw = await request<RawWorkflowRun>(`/api/runs/${workflowId}`, {
    method: "GET",
    headers: authHeaders(token),
  });
  return normalizeWorkflowRun(raw);
}

/** Fetch the revision family (root + ordered members) for a run.
 *  Returns the raw wire shape (unnormalized snake_case) like getChainContext. */
export async function getRunFamily(
  token: string,
  runId: string
): Promise<RunFamily> {
  return request<RunFamily>(`/api/runs/${runId}/family`, {
    method: "GET",
    headers: authHeaders(token),
  });
}

/** One agent's summary-safe telemetry from GET /api/runs/{id}/summary.
 *  Mirrors the backend `_SUMMARY_SAFE_AGENT_KEYS` projection field-for-field
 *  (runs.py) — identity + KPI ONLY; the raw output / input_prompt /
 *  thinking_text / tool_calls are NEVER echoed (V7 leak guard). Every field is
 *  optional because the server projects only the keys present on each stored
 *  agent record. */
export interface RunSummaryAgent {
  agent_id?: string;
  name?: string;
  role?: string;
  icon?: string;
  duration?: number | null;
  error?: string | null;
  input_tokens?: number;
  output_tokens?: number;
  total_tokens?: number;
  cache_read_tokens?: number;
  cache_write_tokens?: number;
}

/** The aggregated, read-only summary of an owned run — the data spine for the
 *  Run-detail page (SHELL-03). Mirrors the backend `RunSummaryResponse`
 *  field-for-field (runs.py): every key maps 1:1 to an existing `WorkflowRun`
 *  column or the owned family walk (no invented fields). Raw wire shape
 *  (snake_case), unnormalized, like getRunFamily/getChainContext. `members`
 *  reuses the family-member type so `{ root_id, members }` slots straight into
 *  the shared `VersionTimeline` as a `RunFamily`. */
export interface RunSummary {
  id: string;
  title: string;
  type: string;
  status: string;
  /** The owner's own top-level brief (run.input) — feeds the revision-instruction
   *  preview in the detail version timeline. Never child-agent output/secrets. */
  input?: string | null;
  duration: number | null;
  agent_count: number;
  token_usage: {
    total_input_tokens?: number;
    total_output_tokens?: number;
    total_tokens?: number;
  };
  error: string | null;
  agents: RunSummaryAgent[];
  root_id: string;
  members: FamilyMember[];
}

/** Fetch the aggregated run summary (KPI stats + per-agent breakdown + failure
 *  banner data + revision-family timeline) for an owned run. Owner-gated (JWT).
 *  Returns the raw wire shape (unnormalized snake_case) like getRunFamily. */
export async function getRunSummary(
  token: string,
  runId: string
): Promise<RunSummary> {
  return request<RunSummary>(`/api/runs/${runId}/summary`, {
    method: "GET",
    headers: authHeaders(token),
  });
}

/** One durable run_events row from GET /api/runs/{id}/events (mirrors the
 *  backend projection, runs.py:897-908): the SAME rows the SSE replays, in the
 *  raw unnormalized wire shape (snake_case). `payload_json` is the event's data
 *  bag — passed downstream verbatim (no normalization; consumers dedup on
 *  `event_id`). */
export interface RunEventRow {
  seq: number;
  event_id: string;
  type: string;
  payload_json: Record<string, unknown>;
}

/** The GET /api/runs/{id}/events envelope (runs.py:897-909). */
export interface RunEventsResponse {
  workflow_id: string;
  after: number;
  events: RunEventRow[];
}

/** A durable event frame shaped like the WS/SSE `{ type, data }` envelope the
 *  page router + useRunChat already consume. */
export interface DurableFrame {
  type: string;
  data: Record<string, unknown>;
}

/**
 * Fetch a run's durable `run_events` rows (DEF-44-12-4). Owner-scoped (JWT);
 * hits the read-only endpoint `GET /api/runs/{id}/events?after=N` — the SAME
 * rows the SSE stream replays. A fresh fetch at `after=0` returns the full
 * history; idempotency is guaranteed downstream by `event_id` dedup (the page's
 * `seenEventIdsRef` / the hook's `seenRef`), so replaying a full fetch over an
 * already-attached live tail double-counts nothing.
 *
 * Returns each row mapped to a `{ type, data }` frame (data = `payload_json`).
 * DEFENSIVELY tolerates a missing/empty `events` array (a mock catch-all `{}`
 * or a legacy shape yields `[]` rather than throwing). Does NOT normalize the
 * payload — consumers key on the snake_case `event_id`/`seq` inside it.
 */
export async function getRunEvents(
  token: string,
  runId: string,
  afterSeq = 0,
): Promise<DurableFrame[]> {
  const res = await request<RunEventsResponse>(
    `/api/runs/${encodeURIComponent(runId)}/events?after=${afterSeq}`,
    { method: "GET", headers: authHeaders(token) },
  );
  return (res?.events ?? []).map((row) => ({
    type: row.type,
    // Merge the row's authoritative `event_id` + `seq` COLUMNS over payload_json
    // (BUG-018): a durable Concierge chat_reply carries its DISTINCT event_id
    // ("chat-reply:{message_id}") only in the column, so surfacing it lets
    // upsertNarratorMessage key the reply distinctly and APPEND it below the
    // paired user question instead of overwriting it. The column is
    // authoritative, so it wins over any same-named payload key.
    data: { ...(row.payload_json ?? {}), event_id: row.event_id, seq: row.seq },
  }));
}

/** A single artifact node from GET /api/runs/{id}/artifacts (mirrors the
 *  backend node shape, runs.py:590-608). `content` is present ONLY when the
 *  request was made with include=content. NOTE: nodes carry NO created_at. */
export interface ArtifactNode {
  id: string;
  kind: string;
  producer_step: string;
  producer_agent: string;
  task_id: string;
  content_hash: string;
  version: number;
  visibility: string;
  location: string;
  parents: string[];
  derived_from: string[];
  children: string[];
  content?: string;
}

export interface RunArtifactsResponse {
  workflow_id: string;
  artifacts: ArtifactNode[];
}

/** Fetch a run's artifact tree. Workstream C1 (POR §6.6) — the first FE
 *  consumer of Workstream-A's `?kind=` filter. Returns the raw wire shape
 *  verbatim (unnormalized) like getRunFamily/getChainContext. */
export async function getRunArtifacts(
  token: string,
  runId: string,
  opts?: { kind?: string; includeContent?: boolean }
): Promise<RunArtifactsResponse> {
  let path = `/api/runs/${runId}/artifacts`;
  const params = new URLSearchParams();
  if (opts?.kind) params.set("kind", opts.kind);
  if (opts?.includeContent) params.set("include", "content");
  const qs = params.toString();
  if (qs) path += `?${qs}`;

  return request<RunArtifactsResponse>(path, {
    method: "GET",
    headers: authHeaders(token),
  });
}

export interface ChainContext {
  workflow_id: string;
  pipeline_type: string;
  title: string;
  brief: string;
  structured_summary: string;
  agent_summaries: Array<{ agent: string; summary: string }>;
  context_block: string;
}

/** Fetch structured chain context from a completed workflow run.
 *  Returns the key text content (slide plan, backlog, architecture, etc.)
 *  formatted as a ready-to-inject context block for the next pipeline. */
export async function getChainContext(
  token: string,
  workflowId: string
): Promise<ChainContext> {
  return request<ChainContext>(`/api/runs/${workflowId}/chain-context`, {
    method: "GET",
    headers: authHeaders(token),
  });
}

export async function deleteWorkflow(
  token: string,
  workflowId: string
): Promise<void> {
  const url = `${BASE_URL}/api/runs/${workflowId}`;
  const response = await fetch(url, {
    method: "DELETE",
    headers: authHeaders(token),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({
      detail: response.statusText,
    }));
    throw new ApiError(response.status, body.detail ?? body);
  }
}

// --- Run command API (Phase 44 W2 / CHAT-07 up-channel over REST) ---
//
// Owner-scoped, terminal-fenced HTTP counterparts to the paused-run WS commands
// (backend/app/api/run_commands.py). Each mirrors its Pydantic request body
// verbatim; a cross-owner / missing run resolves to 404 server-side (IDOR→404),
// matching the WS owner fence — surfaced here as an ApiError(404).

/** Body for POST /api/runs/{id}/gate — the four gate actions (GateCommand,
 *  run_commands.py). `action` is the generic discriminator (SC-001 — no
 *  workflow name): approve (optional `edited_content`) / reject / redo
 *  (`instructions`) / update_specs (`analysis_report`). `edited_content`
 *  survives ONLY on /gate (set_review_response) — /messages CHANNEL_GATE
 *  drops it (WR-03), which is why gates route here. */
export interface GatePayload {
  gate_key: string;
  action?: "approve" | "reject" | "redo" | "update_specs";
  approved?: boolean;
  edited_content?: string | null;
  instructions?: string;
  analysis_report?: string;
}

/**
 * Resolve a paused HITL review gate over REST (mirrors WS `approve_review`).
 * Routes to POST /api/runs/{id}/gate — NOT /messages — so `edited_content` is
 * preserved through set_review_response (WR-03). Owner-gated server-side.
 */
export async function postGate(
  token: string,
  runId: string,
  body: GatePayload,
): Promise<{ ok: boolean; action: string; gate_key: string }> {
  return request<{ ok: boolean; action: string; gate_key: string }>(
    `/api/runs/${encodeURIComponent(runId)}/gate`,
    {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify(body),
    },
  );
}

/**
 * Cooperatively cancel a run over REST (mirrors WS `cancel_pipeline`). The WS
 * frame was connection-scoped and carried no id; the REST path threads the run
 * id explicitly. Owner-gated server-side; idempotent when no live run exists.
 */
export async function postCancel(
  token: string,
  runId: string,
): Promise<{ ok: boolean; run_id: string; cancelled?: boolean }> {
  return request<{ ok: boolean; run_id: string; cancelled?: boolean }>(
    `/api/runs/${encodeURIComponent(runId)}/cancel`,
    {
      method: "POST",
      headers: authHeaders(token),
    },
  );
}

/**
 * FIX-116: Silently classify a settled-run user message as revise / chain / ask.
 * The LLM reads the user text + run deliverable summary + available chain targets
 * and returns ONLY a classification — no chat reply is produced.
 * Generic (SC-001/INV-1) — no workflow-name literal.
 */
export async function classifyIntent(
  token: string,
  runId: string,
  text: string,
  chainHints?: { id: string; label: string }[],
): Promise<{ intent: "revise" | "chain" | "ask"; target_id?: string }> {
  return request<{ intent: "revise" | "chain" | "ask"; target_id?: string }>(
    `/api/runs/${encodeURIComponent(runId)}/classify-intent`,
    {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify({ text, chain_hints: chainHints ?? [] }),
    },
  );
}

/**
 * Resume a terminal-failed or cancelled run over REST (KAN-120 / RESUME-18).
 * Targets POST /api/runs/{id}/resume — the backend resumes from the durable
 * checkpoint (Phase 45–49 resume tier), skipping already-completed steps.
 * Returns the same run_id so the caller can attach the SSE stream via
 * runConnection.attachRun(run_id). Owner-gated server-side (404 on mismatch).
 */
export async function postResume(
  token: string,
  runId: string,
): Promise<{ run_id: string }> {
  // Use a longer AbortController timeout for resume — the backend stamps a marker
  // and reads durable events before returning, which can take several seconds on
  // SQLite / under load. 60s is generous vs the default 30s used by other calls.
  const url = `${BASE_URL}/api/runs/${encodeURIComponent(runId)}/resume`;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 60_000);
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: authHeaders(token),
      signal: controller.signal,
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({ detail: response.statusText }));
      throw new ApiError(response.status, (body as Record<string, unknown>).detail ?? body);
    }
    return response.json() as Promise<{ run_id: string }>;
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(0, "Resume request timed out after 60s");
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Submit clarify answers over REST (mirrors WS `submit_questionnaire`). Targets
 * POST /api/runs/{id}/answers (AnswersCommand) — which needs NO `message_id` —
 * closing the R4 422 the /messages (MessageCommand) path raised. Keeps the
 * ISS-027 `skip_clarification` force-proceed passthrough. Owner-gated.
 */
export async function postAnswers(
  token: string,
  runId: string,
  body: {
    responses: Array<{ question_id: string; answer: string }>;
    skip_clarification?: boolean;
  },
): Promise<{ ok: boolean; run_id: string; count: number }> {
  return request<{ ok: boolean; run_id: string; count: number }>(
    `/api/runs/${encodeURIComponent(runId)}/answers`,
    {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify(body),
    },
  );
}

/**
 * Launch a child PPT revision run over REST (mirrors WS `run_revision`, Strategy A).
 * Targets POST /api/runs/{parentRunId}/revisions (RevisionCommand) — the byte-twin
 * of the same server path: _mint_revision_row + _drive_revision_to_queue ->
 * engine._handle_revision. Preserves the server-side artifact seed, the
 * planning-context prepend, and the exact-kind `derived_from` lineage. The parent
 * linkage is the PATH run id (bug (b): no orphan — source_workflow_run_id is set
 * server-side from parent_run_id). Owner-gated on the parent server-side
 * (cross-owner / missing -> 404). Returns the created revision `run_id`, which the
 * caller can attach; the run then streams over SSE like any other (W1).
 */
export async function postRevision(
  token: string,
  parentRunId: string,
  body: { target_artifact_type: string; instruction: string },
): Promise<{ run_id: string }> {
  return request<{ run_id: string }>(
    `/api/runs/${encodeURIComponent(parentRunId)}/revisions`,
    {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify(body),
    },
  );
}

export async function changePassword(
  token: string,
  currentPassword: string,
  newPassword: string
): Promise<{ message: string }> {
  const url = `${BASE_URL}/api/auth/change-password`;
  const response = await fetch(url, {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new ApiError(response.status, body.detail ?? body);
  }

  return response.json();
}

// --- User Preferences API ---

export interface ModelOption {
  id: string;
  name: string;
  description: string;
  tier: "fast" | "balanced" | "powerful";
}

export interface UserPreferences {
  preferred_model: string | null;
  available_models: ModelOption[];
}

export async function getPreferences(token: string): Promise<UserPreferences> {
  return request<UserPreferences>("/api/settings/preferences", {
    method: "GET",
    headers: authHeaders(token),
  });
}

export async function updatePreferences(
  token: string,
  preferred_model: string | null
): Promise<UserPreferences> {
  return request<UserPreferences>("/api/settings/preferences", {
    method: "PUT",
    headers: authHeaders(token),
    body: JSON.stringify({ preferred_model }),
  });
}

// --- Admin API ---

export interface AdminUser {
  id: string;
  email: string;
  tier: "basic" | "pro" | "enterprise";
  is_admin: boolean;
  created_at: string;
  workflow_run_count: number;
}

export async function adminListUsers(token: string): Promise<AdminUser[]> {
  return request<AdminUser[]>("/api/admin/users", {
    method: "GET",
    headers: authHeaders(token),
  });
}

export async function adminUpdateTier(
  token: string,
  userId: string,
  tier: string
): Promise<AdminUser> {
  return request<AdminUser>(`/api/admin/users/${userId}/tier`, {
    method: "PATCH",
    headers: authHeaders(token),
    body: JSON.stringify({ tier }),
  });
}

export async function adminCreateUser(
  token: string,
  email: string,
  password: string,
  tier: string,
  is_admin: boolean
): Promise<AdminUser> {
  return request<AdminUser>("/api/admin/users", {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ email, password, tier, is_admin }),
  });
}

export async function adminDeleteUser(
  token: string,
  userId: string
): Promise<void> {
  const url = `${BASE_URL}/api/admin/users/${userId}`;
  const response = await fetch(url, {
    method: "DELETE",
    headers: authHeaders(token),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new ApiError(response.status, body.detail ?? body);
  }
}

// --- Capabilities API (API-02 / D-11) ---

/**
 * One palette entry from `GET /api/capabilities` — a registered capability
 * `(kind, name)` with its CAP-03 trust flag, a registry-authored `description`,
 * a derived `security_gated` flag (`!user_allowed`), and a populated
 * per-capability `config_schema` (SURF-02). All metadata is registry-sourced
 * (D-08) — the embedded palette renders entirely from this payload (SC-001),
 * never a hardcoded capability-name list.
 */
export interface CapabilityEntry {
  kind: string;
  name: string;
  user_allowed: boolean;
  description: string;
  security_gated: boolean;
  config_schema: Record<string, unknown>;
}

/** One model-picker entry from the capability palette's model catalog. */
export interface CapabilityModelEntry {
  id: string;
  label: string;
  description: string;
  tier: string;
  cost_class: string;
  provider: string;
  context_window: number;
  user_allowed: boolean;
}

/** The full capability-registry payload; the relocated AgentModelPicker
 *  (AgentsPopup Agents tab) renders its `model_catalog`. (The legacy
 *  WorkflowComposer that rendered the full palette was deleted in ISS-014.) */
export interface CapabilitiesPalette {
  capabilities: CapabilityEntry[];
  model_catalog: CapabilityModelEntry[];
}

/**
 * Fetch the live capability-registry palette (API-02). Auth-gated (JWT); the
 * relocated per-agent AgentModelPicker (AgentsPopup Agents tab) renders its
 * model catalog from this — never a hardcoded list. (ISS-014: the legacy
 * CapabilityPalette/WorkflowComposer that also consumed it were deleted.)
 */
export async function getCapabilities(
  token: string
): Promise<CapabilitiesPalette> {
  return request<CapabilitiesPalette>("/api/capabilities", {
    method: "GET",
    headers: authHeaders(token),
  });
}

/**
 * A manifest-derived workflow discovery row from the authenticated
 * `GET /api/workflows` listing (Plan 20-01). Mirrors the BE `WorkflowSummary`
 * shape: `user_launchable` is the DECLARED product-visibility flag (SC-001 —
 * the catalog filters on it, never a hardcoded workflow-name list), and the
 * presentation fields (`display_name`/`icon`/`launch_surface`) are inert
 * catalog metadata for the data-driven HomeLaunchGrid.
 */
export interface WorkflowSummary {
  id: string;
  name: string;
  description: string;
  step_count: number;
  steps: { agent_id: string; name: string; gate: string | null }[];
  user_launchable: boolean;
  display_name?: string | null;
  icon?: string | null;
  launch_surface?: string | null;
}

/**
 * Fetch the live, manifest-derived workflow catalog (Plan 20-02). Auth-gated
 * (JWT); the data-driven HomeLaunchGrid renders its rows from this list —
 * never a hardcoded list (SC-001). Named `getWorkflowDefinitions` because
 * `getWorkflows` is already taken by the run-history fetcher (`/api/runs`).
 */
export async function getWorkflowDefinitions(
  token: string
): Promise<WorkflowSummary[]> {
  return request<WorkflowSummary[]>("/api/workflows", {
    method: "GET",
    headers: authHeaders(token),
  });
}

/**
 * One compiled step of a workflow definition from `GET /api/workflows/{id}`
 * (SURF-03). Mirrors the BE `WorkflowStepDetail` (backend/app/api/workflows.py):
 * the per-step DECLARED capabilities sourced from the compiled `ExecutionPlan`
 * — `strategy`, `gates`, `validators`, optional `compaction`, and the
 * `task_source` kind. All registry/manifest-sourced (SC-001) — never a hardcoded
 * per-step capability list.
 */
export interface WorkflowStepDetail {
  agent_id: string;
  name: string;
  role: string;
  order: number;
  strategy: string;
  gates: string[];
  validators: string[];
  compaction?: string | null;
  task_source?: { kind: string; parser?: string | null; target?: string | null } | null;
  declared_gate?: string | null;
}

/** The compiled deliverable spec for a workflow (BE `WorkflowDeliverable`). */
export interface WorkflowDeliverable {
  strategy?: string | null;
  name?: string | null;
}

/**
 * The full compiled definition for one known workflow id from
 * `GET /api/workflows/{id}` (API-01 / SURF-03). Mirrors the BE `WorkflowDetail`
 * (backend/app/api/workflows.py:108). Auth-gated (JWT); the composer fetches
 * this to surface a launchable workflow's per-step DECLARED capabilities
 * (sourced from the compiled plan) BEFORE composing — never a hardcoded
 * description.
 */
export interface WorkflowDetail {
  id: string;
  name: string;
  description: string;
  planner: string;
  clarify_mode: string;
  clarify_defaults: string[];
  context_providers: string[];
  deliverable: WorkflowDeliverable;
  steps: WorkflowStepDetail[];
}

/**
 * Fetch the full compiled definition for a known workflow id (API-01 / SURF-03).
 * Auth-gated (JWT). Named `getWorkflowDetail` because `getWorkflow` is already
 * taken by the run-history fetcher (`/api/runs/{id}`) and `getWorkflowDefinitions`
 * by the catalog listing. An unknown id raises 404 server-side (the caller treats
 * that as "nothing declared" — the SURF-03 strip simply does not render).
 */
export async function getWorkflowDetail(
  token: string,
  workflowId: string
): Promise<WorkflowDetail> {
  return request<WorkflowDetail>(`/api/workflows/${encodeURIComponent(workflowId)}`, {
    method: "GET",
    headers: authHeaders(token),
  });
}

// --- Saved (user-authored) workflows API (Phase 21) ---

/**
 * A saved, user-authored workflow row from `GET /api/user-workflows`
 * (owner-scoped, `source="user"`). Mirrors the BE `UserWorkflowResponse`
 * (backend/app/api/user_workflows.py): a saved workflow is pure data — the
 * composer triple `{base_pipeline_type, agent_ids, model_overrides}` plus a
 * user-chosen `name`/`description` — so a saved row can never carry something
 * the launch path would reject (the server re-validates with the launch
 * predicates at save time). Type analog: `WorkflowSummary` (above), with the
 * three composition fields added.
 */
export interface UserWorkflowSummary {
  id: string;
  name: string;
  description?: string | null;
  base_pipeline_type: string;
  agent_ids: string[];
  model_overrides?: Record<string, string> | null;
  // WR-01 (EMP-03) — the persisted compact per-step Advanced-lever selections map
  // (the `manifest_json` shape the backend `_project` round-trips). Carried so a
  // launched saved workflow can re-load AND re-send its composed levers. NULL/absent
  // ⇒ no selections (parity with a Phase-21 save that declared none).
  // For PPT/Prototype saved workflows a special `_wizard` key is embedded inside
  // selections carrying { templateId, designSystemId, brief, gateAgentIds, ... }.
  selections?: Record<string, Record<string, unknown>> | null;
  created_at?: string;
  updated_at?: string;
}

/**
 * Fetch the caller's saved workflows (owner-scoped server-side). GET analog of
 * `getWorkflowDefinitions` — there is NO `user_launchable` filter here: every
 * `source="user"` row the user owns is always shown in the "Your workflows"
 * catalog section.
 */
export async function getUserWorkflows(
  token: string
): Promise<UserWorkflowSummary[]> {
  return request<UserWorkflowSummary[]>("/api/user-workflows", {
    method: "GET",
    headers: authHeaders(token),
  });
}

/**
 * Persist a saved workflow from the composer's own state (POST analog of
 * `adminCreateUser`). Body = the composer triple + a name/description; the
 * server re-validates with the launch predicates (save == launch) and
 * owner-stamps the row.
 */
export async function createUserWorkflow(
  token: string,
  body: {
    name: string;
    description?: string;
    base_pipeline_type: string;
    agent_ids: string[];
    model_overrides?: Record<string, string>;
    /**
     * EMP-01/03 (D-05/D-11) — the per-agent Advanced-expander selections map
     * (agentId -> {validators?, gates?, model?, retry?, ...}). The compact shape
     * 22-04 persists verbatim in `manifest_json` and `_apply_selections` overlays
     * onto the file-compiled plan by agent_id. Omitted when empty (the payload
     * stays byte-identical — INV-3). The server re-compiles `trust="user"`
     * before persisting (the authoritative CAP-03 backstop).
     */
    selections?: Record<string, Record<string, unknown>>;
  }
): Promise<UserWorkflowSummary> {
  return request<UserWorkflowSummary>("/api/user-workflows", {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(body),
  });
}

/**
 * Rename / edit a saved workflow (PATCH analog of `adminUpdateTier`). Only the
 * caller's own `source="user"` rows are mutable (server IDOR→404).
 */
export async function renameUserWorkflow(
  token: string,
  id: string,
  body: { name?: string; description?: string }
): Promise<UserWorkflowSummary> {
  return request<UserWorkflowSummary>(`/api/user-workflows/${id}`, {
    method: "PATCH",
    headers: authHeaders(token),
    body: JSON.stringify(body),
  });
}

/**
 * Delete a saved workflow (DELETE analog of `adminDeleteUser` — the manual
 * `fetch` + `ApiError` 204 idiom, since there is no JSON body to parse). Only
 * the caller's own rows are deletable (server IDOR→404).
 */
export async function deleteUserWorkflow(
  token: string,
  id: string
): Promise<void> {
  const url = `${BASE_URL}/api/user-workflows/${id}`;
  const response = await fetch(url, {
    method: "DELETE",
    headers: authHeaders(token),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new ApiError(response.status, body.detail ?? body);
  }
}

// ── Agent prompt endpoints (KAN-76) ──────────────────────────────────────────

export interface AgentPromptData {
  agent_id: string;
  /** The canonical AGENT.md prompt body (read-only base). */
  prompt_body: string;
  /** Per-user override saved via PUT /api/agents/{id}/prompt, or null if not set. */
  override: string | null;
  has_override: boolean;
}

/**
 * Fetch an agent's base prompt body + the caller's saved override.
 * Used by the Library and workflow info panel to display the system prompt (KAN-76).
 */
export async function getAgentPrompt(
  token: string,
  agentId: string,
): Promise<AgentPromptData> {
  return request<AgentPromptData>(`/api/agents/${encodeURIComponent(agentId)}/prompt`, {
    method: "GET",
    headers: authHeaders(token),
  });
}

/**
 * Save (create or replace) a per-user prompt override for an agent.
 * Passing an empty string removes the override (use deleteAgentPromptOverride for explicit deletion).
 */
export async function saveAgentPromptOverride(
  token: string,
  agentId: string,
  content: string,
): Promise<{ status: string; agent_id: string }> {
  return request<{ status: string; agent_id: string }>(
    `/api/agents/${encodeURIComponent(agentId)}/prompt`,
    {
      method: "PUT",
      headers: { ...authHeaders(token), "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    },
  );
}

/**
 * Delete the caller's prompt override for an agent, reverting to the base AGENT.md.
 */
export async function deleteAgentPromptOverride(
  token: string,
  agentId: string,
): Promise<{ status: string; agent_id: string }> {
  return request<{ status: string; agent_id: string }>(
    `/api/agents/${encodeURIComponent(agentId)}/prompt`,
    {
      method: "DELETE",
      headers: authHeaders(token),
    },
  );
}

// ── File text extraction (binary formats: PDF, DOCX, PPTX) ──────────────────

export interface ExtractTextResponse {
  filename: string;
  text: string;
  truncated: boolean;
}

/**
 * Upload a binary file (PDF, DOCX, PPTX) to the backend for text extraction.
 * Returns the extracted plain text (capped at 16,000 chars server-side).
 */
export async function extractFileText(
  token: string,
  file: File,
): Promise<ExtractTextResponse> {
  const form = new FormData();
  form.append("file", file);
  const url = `${BASE_URL}/api/files/extract-text`;
  const response = await fetch(url, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new ApiError(response.status, body.detail ?? body);
  }
  return response.json();
}

// ── Audit / hook-runs endpoint (KAN-73) ─────────────────────────────────────

export interface HookRunsResponse {
  workflow_id: string;
  hook_runs: Array<{
    id: string;
    hook: string;
    event: string;
    outcome: string;
    detail: Record<string, unknown> | null;
    created_at: string | null;
  }>;
}

/**
 * Fetch persisted hook_runs for a completed workflow run (KAN-73).
 * Used by the Audit tab when reopening a run from Workflow History.
 */
export async function getRunHookRuns(
  token: string,
  workflowId: string,
): Promise<HookRunsResponse> {
  return request<HookRunsResponse>(`/api/runs/${encodeURIComponent(workflowId)}/hook-runs`, {
    method: "GET",
    headers: authHeaders(token),
  });
}

// ── Audit-tab read endpoints (SC-3, phase 32 plan 03) ───────────────────────
// The Audit tab reads three owner-scoped, read-only audit projections per run.
// Each endpoint applies a two-layer owner gate server-side and resolves a
// cross-owner / missing run to 404 (never a foreign row). The fetchers below
// map that 404 to an EMPTY typed envelope so the tab renders gracefully and
// NEVER surfaces another owner's data (T-32-09-01). Any other error rethrows.

/** One governance-gate audit row (GET /api/runs/{id}/gate-events). */
export interface GateEventRow {
  id: string;
  run_id: string;
  /** e.g. the step / agent the gate fired on. */
  step: string | null;
  /** gate kind: human | validation | approval | security. */
  gate: string | null;
  /** verdict: pass | block | wait_human. */
  outcome: string | null;
  detail: Record<string, unknown> | null;
  created_at: string | null;
}

export interface GateEventsResponse {
  workflow_id: string;
  gate_events: GateEventRow[];
}

/** One validator-run audit row (GET /api/runs/{id}/validation-results). */
export interface ValidationResultRow {
  id: string;
  run_id: string;
  step: string | null;
  validator: string | null;
  /** severity ladder: CRITICAL | HIGH | MEDIUM | LOW. */
  severity: string | null;
  attempt: number | null;
  /** the validator's issue list (JSON, shape validator-specific). */
  issues: unknown;
  created_at: string | null;
}

export interface ValidationResultsResponse {
  workflow_id: string;
  validation_results: ValidationResultRow[];
}

/** One exec-invocation audit row (GET /api/runs/{id}/exec-runs). */
export interface ExecRunRow {
  id: string;
  run_id: string;
  step: string | null;
  /** the invoked argv (JSON). */
  argv_json: unknown;
  /** disposition: allowed | denied | killed. */
  outcome: string | null;
  exit_code: number | null;
  duration_ms: number | null;
  /** the exec-policy snapshot in force for this invocation (JSON). */
  policy_snapshot_json: unknown;
  /** TRUNCATED output digest only — never raw child output (ASVS V7). */
  output_digest: string | null;
  created_at: string | null;
}

export interface ExecRunsResponse {
  workflow_id: string;
  exec_runs: ExecRunRow[];
}

/**
 * Fetch the run's governance-gate audit rows for the Audit tab (SC-3).
 * A cross-owner / missing run resolves to an empty envelope (404 → []),
 * never a foreign row.
 */
export async function getRunGateEvents(
  token: string,
  workflowId: string,
): Promise<GateEventsResponse> {
  try {
    return await request<GateEventsResponse>(
      `/api/runs/${encodeURIComponent(workflowId)}/gate-events`,
      { method: "GET", headers: authHeaders(token) },
    );
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      return { workflow_id: workflowId, gate_events: [] };
    }
    throw err;
  }
}

/**
 * Fetch the run's validator-run audit rows for the Audit tab (SC-3).
 * A cross-owner / missing run resolves to an empty envelope (404 → []).
 */
export async function getRunValidationResults(
  token: string,
  workflowId: string,
): Promise<ValidationResultsResponse> {
  try {
    return await request<ValidationResultsResponse>(
      `/api/runs/${encodeURIComponent(workflowId)}/validation-results`,
      { method: "GET", headers: authHeaders(token) },
    );
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      return { workflow_id: workflowId, validation_results: [] };
    }
    throw err;
  }
}

/**
 * Fetch the run's exec-invocation audit rows for the Audit tab (SC-3).
 * A cross-owner / missing run resolves to an empty envelope (404 → []).
 * The projection carries only the truncated output_digest (never raw output).
 */
export async function getRunExecRuns(
  token: string,
  workflowId: string,
): Promise<ExecRunsResponse> {
  try {
    return await request<ExecRunsResponse>(
      `/api/runs/${encodeURIComponent(workflowId)}/exec-runs`,
      { method: "GET", headers: authHeaders(token) },
    );
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      return { workflow_id: workflowId, exec_runs: [] };
    }
    throw err;
  }
}
