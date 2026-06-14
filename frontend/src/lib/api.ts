/**
 * API client utility for communicating with the backend.
 * Uses the fetch API with JWT-based authentication.
 */

import type {
  AuthResponse,
  ChatMessage,
  ChatSession,
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
 * the catch will swallow it. (See the WS-expired close handler in
 * useWebSocket.ts which legitimately calls clearToken() directly — the token
 * is already invalid, so /logout would just 401.)
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

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${BASE_URL}${path}`;
  const response = await fetch(url, options);

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
    agentCount: raw.agent_count,
    duration: raw.duration ?? undefined,
    error: raw.error ?? undefined,
    createdAt: ensureUTC(raw.created_at),
    completedAt: raw.completed_at ? ensureUTC(raw.completed_at) : undefined,
  };
}

export async function getWorkflows(
  token: string,
  options?: { type?: WorkflowType; limit?: number }
): Promise<WorkflowRun[]> {
  let path = "/api/runs";
  const params = new URLSearchParams();
  if (options?.type) params.set("type", options.type);
  if (options?.limit) params.set("limit", String(options.limit));
  const qs = params.toString();
  if (qs) path += `?${qs}`;

  const raw = await request<RawWorkflowRun[]>(path, {
    method: "GET",
    headers: authHeaders(token),
  });
  return raw.map(normalizeWorkflowRun);
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
 * catalog metadata for the data-driven WorkflowCatalog.
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
 * (JWT); the data-driven WorkflowCatalog renders its rows from this list —
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
  created_at?: string;
  updated_at?: string;
}

/**
 * List the caller's saved workflows (owner-scoped server-side). GET analog of
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
