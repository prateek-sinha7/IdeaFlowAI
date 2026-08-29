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
  WorkflowManifest,
  WorkflowRun,
  WorkflowType,
} from "@/types/index";
import { ENV } from "@/lib/env";
import { routes } from "@/lib/routes";

const BASE_URL = ENV.API_URL;

const TOKEN_KEY = "auth_token";

// --- Token management ---

export function getToken(): string | null {
  // Guard on localStorage itself, not on `window`. They are not the same test:
  // Node test runners and some SSR shims define a partial `window` with no
  // localStorage, so the window check passed and this threw
  // "Cannot read properties of undefined (reading 'getItem')".
  if (typeof localStorage === "undefined") return null;
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
 * useHandoffSocket.ts, which legitimately clears the token via
 * handleSessionExpiry() without calling this function — the token is
 * already invalid, so /logout would just 401.)
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

/**
 * ISS-224/ISS-256 — turn an error body's `detail` into a message safe to show.
 *
 * FastAPI sends a *list* of error objects for a 422, and every entry carries an
 * `input` field holding the ENTIRE rejected value — a PAT, a password. Both of
 * this app's error paths used to fall through to `JSON.stringify(...)` for
 * anything that wasn't a plain string, so that value was rendered back onto the
 * page. Take the human-readable `msg` fields instead, never the raw entry.
 *
 * Returns null for any other shape so the caller keeps its own fallback.
 */
export function errorMessageFromDetail(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (!Array.isArray(detail)) return null;
  const messages = detail
    .map((entry) => (entry as { msg?: unknown } | null)?.msg)
    .filter((msg): msg is string => typeof msg === "string");
  return messages.join("; ") || "The request was rejected as invalid.";
}

class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    const message = errorMessageFromDetail(detail) ?? JSON.stringify(detail);
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/**
 * ISS-374 — "this workflow does not exist" vs "it could not be loaded right
 * now". `ApiError` has carried `status` all along but is not exported, so every
 * `.catch()` in the app treated a genuine 404 and a transient network/timeout
 * blip identically. The two want different copy (a 404 has no useful retry, a
 * transient failure does), so the distinction lives here, once, rather than
 * being re-derived per call site.
 */
export function isNotFoundError(e: unknown): boolean {
  return e instanceof ApiError && e.status === 404;
}

// BUG-013 Part B — fail-fast timeout for the REST client. When the browser's
// ~6-connections-per-origin pool is saturated (per-run SSE streams), a call can
// hang forever with no free socket → a silent idle screen. Wrap every request in
// an AbortController that aborts after REQUEST_TIMEOUT_MS so a starved/hung call
// rejects with a typed, catchable ApiError instead of hanging. Generous (~30s) so
// it never aborts a legitimately-slow brief ingest / large-deliverable fetch.
const REQUEST_TIMEOUT_MS = 30_000;

/** Path of the refresh endpoint — never itself retried (see `fetchWithAuth`). */
const REFRESH_PATH = "/api/auth/refresh";

// FR-015 — paths where a 401 means "your credentials were rejected", not
// "your session expired": the caller already shows that inline (login/page.tsx;
// AccountSettings.tsx for a wrong current password). Redirecting on these would
// bounce straight back to /login, or silently log a user out for mistyping their
// current password instead of showing the inline error.
// Exported so store/api/http.ts's axios interceptor (a second shared request
// path — see its own 401 handling) can reuse the exact same exemption list
// instead of drifting out of sync with a duplicate.
export const SESSION_EXPIRY_EXEMPT_PATHS = new Set([
  "/api/auth/login",
  "/api/auth/change-password",
]);

/**
 * Normalize either a bare path (`/api/auth/login?x=1`) or an absolute URL
 * (`https://api.example.com/api/auth/login`) down to just its pathname, so the
 * exempt-set lookup is the same test no matter which of the request paths
 * (fetchWithAuth, authedFetch, the axios interceptor) is asking.
 */
function requestPathname(pathOrUrl: string): string {
  try {
    return new URL(pathOrUrl, "http://localhost").pathname;
  } catch {
    return pathOrUrl;
  }
}

/** The ONE predicate behind FR-015's "don't redirect on this 401" carve-out. */
export function isSessionExpiryExempt(pathOrUrl: string): boolean {
  return SESSION_EXPIRY_EXEMPT_PATHS.has(requestPathname(pathOrUrl));
}

/**
 * FR-015's one "session expired" side effect: clear the stored token and
 * send the browser to routes.login({ expired: true }). Shared by the three
 * places a session can expire from — this file's own fetchWithAuth 401
 * branch, store/api/http.ts's axios response interceptor (Library's
 * agent/skill/hook fetches and the rest of store/api/), and
 * useHandoffSocket.ts's JWT-expired (4001) WebSocket close handler — so the
 * clear+redirect pair can't drift out of sync across the three copies.
 *
 * Post-Cognito-merge: this is now the SECOND half of the 401 ladder. A 401 on
 * an authenticated request first attempts one silent token refresh
 * (`refreshOnce` below); only when that fails does the session count as
 * genuinely expired and this fire.
 */
export function handleSessionExpiry(): void {
  clearToken();
  if (typeof window !== "undefined") {
    // ISS-322: carry the route the user was on (path + its own query string) as
    // the `redirect` param, so re-login returns there instead of /dashboard —
    // the same ?redirect= contract the signed-out guard already uses, validated
    // on arrival by login/page.tsx's resolveRedirectTarget.
    const { pathname, search } = window.location;
    window.location.href = routes.login({ expired: true, redirect: `${pathname}${search}` });
  }
}

/**
 * Cognito migration (Phase 4): swap the stored access token for a fresh one.
 *
 * Sends the CURRENT access token; the backend holds the Cognito refresh token
 * server-side (migration 0032) so the browser only ever carries one bearer
 * value — the `getToken()`/`setToken()` seam stays intact (Decision 3).
 *
 * Never throws: a failed refresh is a normal outcome (local/break-glass users
 * get a 501, an aged-out refresh token gets a 401). Callers treat `null` as
 * "could not refresh" and surface the original error instead.
 */
export async function refreshAccessToken(): Promise<string | null> {
  const current = getToken();
  if (!current) return null;
  try {
    const res = await fetch(`${BASE_URL}${REFRESH_PATH}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${current}` },
    });
    if (!res.ok) return null;
    const body = (await res.json().catch(() => null)) as { token?: string } | null;
    if (!body?.token) return null;
    setToken(body.token);
    return body.token;
  } catch {
    return null;
  }
}

/**
 * Single-flight guard for `refreshAccessToken()`.
 *
 * A screen typically fires several requests at once, so an expired token
 * produces a burst of simultaneous 401s. Without this, each one would mint its
 * own refresh call and the losers would install a token that a later refresh
 * had already superseded. The first caller performs the refresh; the rest await
 * the same promise and reuse its result.
 */
let inFlightRefresh: Promise<string | null> | null = null;

function refreshOnce(): Promise<string | null> {
  if (!inFlightRefresh) {
    inFlightRefresh = refreshAccessToken().finally(() => {
      inFlightRefresh = null;
    });
  }
  return inFlightRefresh;
}

/** Replace the Authorization header on a copy of the outgoing init. */
function withBearer(options: RequestInit, token: string): RequestInit {
  const headers = new Headers(options.headers as HeadersInit | undefined);
  headers.set("Authorization", `Bearer ${token}`);
  return { ...options, headers };
}

function hasAuthorization(options: RequestInit): boolean {
  return new Headers(options.headers as HeadersInit | undefined).has("Authorization");
}

/**
 * FR-015 — the guarded escape hatch for call sites that CANNOT go through
 * request()/fetchWithAuth below: they need the raw Response (a Blob download),
 * an incrementally-read body (NDJSON / SSE), or a non-JSON error shape. Those
 * sites hand-roll `fetch(url, { headers: { Authorization: ... } })`, and every
 * one of them is a place FR-015's redirect silently goes missing — this spec
 * found nine such sites one at a time before this helper existed.
 *
 * `authedFetch` is a drop-in for global `fetch` (same arguments, same Response,
 * same throw-on-network-failure behavior) that adds exactly one thing: the 401
 * session-expiry side effect, using the same exempt list as every other request
 * path. Prefer request()/fetchWithAuth; reach for this only when you need the
 * raw Response. A hand-written authenticated `fetch(` anywhere in `src/` that
 * is NOT this function, fetchWithAuth, or a site with its own documented
 * handleSessionExpiry() call is an FR-015 defect.
 *
 * Deliberately NOT routed through here: `logout()` above (a 401 means the token
 * is already dead — redirecting mid-logout is noise) and useRunStream's
 * `/api/auth/refresh` probe (a failed refresh must fall back to its own
 * try-refresh-then-expire ladder, not log the user out mid-run). It also does
 * NOT attempt the silent refresh that fetchWithAuth does: these callers stream
 * or download, so replaying the request is not always safe.
 */
export async function authedFetch(
  input: string,
  init?: RequestInit
): Promise<Response> {
  const response = await fetch(input, init);
  if (response.status === 401 && !isSessionExpiryExempt(input)) {
    handleSessionExpiry();
  }
  return response;
}

/** Raw fetch + abort-on-timeout. No auth semantics — see fetchWithAuth. */
async function fetchWithTimeout(
  url: string,
  options: RequestInit,
  timeoutMs: number = REQUEST_TIMEOUT_MS
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    // No current caller passes its own signal, so a direct assignment is safe.
    return await fetch(url, { ...options, signal: controller.signal });
  } catch (err) {
    // On abort the fetch throws a DOMException AbortError — translate it to a
    // typed, catchable ApiError (status 0) so callers surface a clear timeout
    // instead of an opaque hang (matches the reopen catch at page.tsx).
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(0, `Request timeout after ${timeoutMs}ms (aborted)`);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Shared fetch path for every REST call. Returns the raw Response on success
 * (2xx) so callers that need response headers (e.g. getWorkflows'
 * X-Total-Count) aren't forced through request()'s JSON-only return.
 *
 * The 401 ladder is the merge of two independently-developed halves, and the
 * ORDER matters:
 *
 *   401 ──► can we refresh?  (Cognito Phase 4)
 *            │ yes → replay once with the fresh bearer, retryOn401 = false
 *            │ no  → the session really is over (FR-015)
 *            └────► handleSessionExpiry(), unless the path is exempt
 *
 * Refreshing FIRST is what makes the two compose: Cognito access tokens are
 * short-lived (60 min), so a mid-session 401 is usually just an aged token, not
 * an ended session. Firing handleSessionExpiry() on that first 401 — as the
 * FR-015 half did alone — would log users out roughly hourly.
 *
 * Three deliberate bounds keep the retry from becoming a storm:
 *
 * 1. **At most one retry per request.** The replay is issued with `retryOn401`
 *    off, so a second 401 propagates to the caller. There is no recursion.
 * 2. **Only for requests that actually sent a bearer.** An unauthenticated 401
 *    (e.g. wrong password on `/login`) is a real answer, not an expiry — the
 *    login form depends on receiving it.
 * 3. **Never for the refresh endpoint itself**, which would be circular.
 */
async function fetchWithAuth(
  path: string,
  options: RequestInit = {},
  timeoutMs: number = REQUEST_TIMEOUT_MS,
  retryOn401 = true
): Promise<Response> {
  const url = `${BASE_URL}${path}`;
  const response = await fetchWithTimeout(url, options, timeoutMs);

  if (!response.ok) {
    if (
      response.status === 401 &&
      retryOn401 &&
      path !== REFRESH_PATH &&
      hasAuthorization(options)
    ) {
      const fresh = await refreshOnce();
      if (fresh) {
        return fetchWithAuth(path, withBearer(options, fresh), timeoutMs, false);
      }
    }
    const body = await response.json().catch(() => ({
      detail: response.statusText,
    }));
    if (response.status === 401 && !isSessionExpiryExempt(path)) {
      handleSessionExpiry();
    }
    throw new ApiError(response.status, body.detail ?? body);
  }

  return response;
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  timeoutMs?: number
): Promise<T> {
  const response = await fetchWithAuth(path, options, timeoutMs);
  // DELETE endpoints (chats/runs/user-workflows/admin users) return 204 No
  // Content — no body to parse.
  if (response.status === 204) return undefined as T;
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

// Cognito migration (Phase 3/4): returned instead of AuthResponse when Cognito
// needs another auth step before a token can be issued. Detected by the presence
// of a `challenge` field — every real AuthResponse carries a `token` instead.
export interface AuthChallengeResponse {
  challenge:
    | "NEW_PASSWORD_REQUIRED"
    | "SOFTWARE_TOKEN_MFA"
    // Email one-time code. Cognito has already sent it by the time this
    // response arrives.
    | "EMAIL_OTP"
    // Several factors active with no preference set. Should not occur — the
    // backend always names a preferred factor — but handled rather than
    // dead-ended.
    | "SELECT_MFA_TYPE"
    // Pool-wide required MFA with no factor enrolled. The backend answers 501
    // for this; it cannot be completed from the login screen.
    | "MFA_SETUP";
  session: string;
  /**
   * Masked destination Cognito sent the code to (e.g. "j***@e***.com"), for
   * delivered-code challenges like EMAIL_OTP. Already masked by AWS. Telling the
   * user WHICH mailbox to check avoids the common "no code arrived" confusion
   * when the address on file isn't the one they expected.
   */
  delivery?: string | null;
  /** Selectable factors on a SELECT_MFA_TYPE challenge. */
  available_factors?: string[] | null;
}

/** A Cognito MFA factor id as it appears in `MfaStatus.factors`. */
export type MfaFactor = "SOFTWARE_TOKEN_MFA" | "EMAIL_OTP";

export interface MfaStatus {
  enabled: boolean;
  factors: MfaFactor[];
  /** Email OTP is configured on the pool. When false, the UI must not offer it. */
  email_available: boolean;
  totp_available: boolean;
  /** This user's role requires a factor, so it cannot be removed. */
  required: boolean;
  /** False for non-Cognito (break-glass) accounts, where MFA does not apply. */
  supported: boolean;
}

export function isAuthChallenge(
  data: AuthResponse | AuthChallengeResponse
): data is AuthChallengeResponse {
  return "challenge" in data;
}

export async function login(
  email: string,
  password: string
): Promise<AuthResponse | AuthChallengeResponse> {
  const data = await request<AuthResponse | AuthChallengeResponse>(
    "/api/auth/login",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    }
  );
  if (!isAuthChallenge(data)) {
    setToken(data.token);
  }
  return data;
}

/**
 * Complete a Cognito auth challenge started by login() (Phase 3/4). Pass
 * `newPassword` for NEW_PASSWORD_REQUIRED, `mfaCode` for SOFTWARE_TOKEN_MFA /
 * EMAIL_OTP, `selectedFactor` for SELECT_MFA_TYPE.
 *
 * Response is either a fresh challenge or a real AuthResponse. Chaining is
 * ordinary, not exotic: a first login with a temporary password produces
 * NEW_PASSWORD_REQUIRED and then an MFA prompt for a user who holds a factor.
 */
export async function respondToLoginChallenge(
  email: string,
  session: string,
  challenge: AuthChallengeResponse["challenge"],
  opts: { newPassword?: string; mfaCode?: string; selectedFactor?: string }
): Promise<AuthResponse | AuthChallengeResponse> {
  const data = await request<AuthResponse | AuthChallengeResponse>(
    "/api/auth/login/challenge",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email,
        session,
        challenge,
        new_password: opts.newPassword,
        mfa_code: opts.mfaCode,
        selected_factor: opts.selectedFactor,
      }),
    }
  );
  if (!isAuthChallenge(data)) {
    setToken(data.token);
  }
  return data;
}

// --- MFA (account security) ---

/** Read the caller's second-factor state and what this deployment offers. */
export async function getMfaStatus(token: string): Promise<MfaStatus> {
  return request<MfaStatus>("/api/auth/mfa", {
    method: "GET",
    headers: authHeaders(token),
  });
}

/**
 * Turn email one-time codes on as a second factor.
 *
 * Unlike TOTP there is no enrolment ceremony: the mailbox is already the pool's
 * sign-in identifier and is verified, so there is no secret to provision and
 * nothing to scan. Returns the resulting factor list from the server rather than
 * assuming the write landed.
 */
export async function enableEmailMfa(
  token: string
): Promise<{ message: string; factors: MfaFactor[] }> {
  return request<{ message: string; factors: MfaFactor[] }>(
    "/api/auth/mfa/email/enable",
    { method: "POST", headers: authHeaders(token) }
  );
}

/**
 * Turn email one-time codes off.
 *
 * The backend refuses with 409 when this would leave an account whose role
 * requires a factor without one — surface that message rather than treating it
 * as an unexpected failure.
 */
export async function disableEmailMfa(
  token: string
): Promise<{ message: string; factors: MfaFactor[] }> {
  return request<{ message: string; factors: MfaFactor[] }>(
    "/api/auth/mfa/email/disable",
    { method: "POST", headers: authHeaders(token) }
  );
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
  await request<void>(`/api/chats/${chatId}`, {
    method: "DELETE",
    headers: authHeaders(token),
  });
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
  // R-20 (014-conditional-gates, T41/T42): the step id a divert fired from.
  // Optional so legacy raw rows without it still parse.
  diverted_at_step_id?: string | null;
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
    // R-20 (014-conditional-gates, T41/T42): the step a divert fired from.
    divertedAtStepId: raw.diverted_at_step_id ?? null,
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

  // Routed through fetchWithAuth (not request()) — this caller needs the raw
  // Response to read the X-Total-Count header, which request<T>() discards.
  const res = await fetchWithAuth(path, {
    method: "GET",
    headers: authHeaders(token),
  });

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
  /** ISS-034 — the same window priced as-if prompt caching had been OFF. */
  spend_full: number;
  /** How many runs in the window carry the counterfactual (pre-ISS-034 rows do not). */
  metered_runs: number;
  token_totals: AnalyticsTokenTotals;
  type_avg_duration_sec: Record<string, number>;
}

/**
 * Fetch the owner-scoped, date/pipeline/model-scoped analytics summary (38-01).
 * Changing ANY of the three re-queries the server (SC-1 recompute) — no
 * client-side rollup of raw runs. `range` is a UI enum: today|3d|7d|30d|90d|all;
 * `pipeline` is a run `type` and `model` a `model_id`, both omitted when the
 * filter is "all" (ISS-229/288/289 — the server scopes every figure, not just
 * the two breakdown arrays a caller could narrow in memory).
 */
export async function getAnalyticsSummary(
  token: string,
  range: string,
  pipeline?: string,
  model?: string
): Promise<AnalyticsSummary> {
  const params = new URLSearchParams({ range });
  if (pipeline) params.set("pipeline", pipeline);
  if (model) params.set("model", model);
  return request<AnalyticsSummary>(
    `/api/analytics/summary?${params.toString()}`,
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
  /** ISS-358: the durable row's own write time (runs.py get_run_events), UTC-aware.
   *  Optional so a legacy/mock envelope without it still type-checks. */
  created_at?: string | null;
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
    // ISS-358: the row's `created_at` COLUMN rides as a FALLBACK — merged FIRST so a
    // payload-embedded timestamp still wins (FIX-354 stamps the RUN's created_at on
    // `pipeline_start`, which a resumed run's row write time would otherwise clobber).
    // The app-layer chat rows carry no payload timestamp at all, so for them this is
    // the only real send time and it is what stops a replay re-dating the turn to now.
    data: {
      created_at: row.created_at,
      ...(row.payload_json ?? {}),
      event_id: row.event_id,
      seq: row.seq,
    },
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

// ─── Run workspace (spec 017 phase 2) ────────────────────────────────────────

export interface SandboxFile {
  /** POSIX path relative to the run sandbox root. */
  path: string;
  size: number;
  /** Epoch seconds. */
  modified: number;
  /** True when the viewer can render this file's bytes as text. */
  text: boolean;
  /** How the viewer should present it. `text` is `kind === "text"`. */
  kind?: "text" | "image" | "pdf" | "binary";
  /** Part of what the run DELIVERED, as opposed to how it worked.
   *
   *  Computed server-side by `is_deliverable_relpath` — the same predicate the
   *  deliverable walk applies — so the workspace can group Deliverables without
   *  a copy of `_DELIVERABLE_EXCLUDE` here that drifts from the backend's.
   *  Absent on a listing that predates the field. */
  deliverable?: boolean;
}

export interface SandboxListing {
  run_id: string;
  /** The run dir is gone — TTL-swept. Distinct from "the run wrote nothing". */
  expired: boolean;
  /** The listing hit a server-side cap; some files are not shown. */
  truncated: boolean;
  files: SandboxFile[];
}

export async function getRunSandbox(
  token: string,
  runId: string,
): Promise<SandboxListing> {
  return request<SandboxListing>(`/api/runs/${runId}/sandbox`, {
    method: "GET",
    headers: authHeaders(token),
  });
}

/** The run's primary deliverable, as a file that ACTUALLY EXISTS in its workspace.
 *
 *  ISS-199 — every surface that names the deliverable used to guess it from
 *  whatever text the panel happened to be holding (`run.output` is
 *  `ctx.last_streamed`, the LAST agent's stream, which for `ppt_v2` is neither
 *  the deck nor the .pptx). One resolver, so the Files tab, its base-version
 *  section and the header Download cannot answer the question differently.
 *
 *  `declared` is the workflow's own `deliverable_filename` (the engine emits it
 *  on `pipeline_complete` and persists it to the run row); omit it and the run
 *  row is read for it. The sibling preference is keyed on the declared
 *  EXTENSION, never a workflow name (SC-001):
 *
 *    declared .html → `<stem>.pptx`, else the declared file
 *                     (ppt_v2: the PowerPoint, falling back to the deck when
 *                     the render step did not run)
 *    declared .pptx → the declared file, else `<stem>.html`
 *    anything else  → the declared file alone (user_stories.md considers none)
 *
 *  Presence is the gate: null when nothing is declared, nothing is listed, or
 *  neither candidate is on disk — the honest state, since we cannot name a file
 *  we have not seen. */
export async function resolveRunDeliverable(
  token: string,
  runId: string,
  declared?: string | null,
): Promise<SandboxFile | null> {
  const name = declared ?? (await getWorkflow(token, runId)).deliverableFilename ?? null;
  if (!name) return null;
  const dot = name.lastIndexOf(".");
  const stem = dot > 0 ? name.slice(0, dot) : name;
  const ext = dot > 0 ? name.slice(dot + 1).toLowerCase() : "";
  const candidates = [...new Set(
    ext === "html" ? [`${stem}.pptx`, name]
    : ext === "pptx" ? [name, `${stem}.html`]
    : [name],
  )];
  const listing = await getRunSandbox(token, runId);
  return candidates.map((c) => listing.files.find((f) => f.path === c)).find(Boolean) ?? null;
}

/** The URL a workspace file's bytes are served from.
 *
 *  NEVER navigate a browser to this (an `<a href>`, `window.open`): auth here is
 *  a bearer token held in JS, not a cookie, so a navigation arrives anonymous and
 *  the API answers `{"detail":"Not authenticated"}` — which the browser renders
 *  instead of saving anything. Both readers below send the header. */
export function runSandboxFileUrl(runId: string, path: string): string {
  return `${ENV.API_URL}/api/runs/${runId}/sandbox/file?path=${encodeURIComponent(path)}`;
}

/** One workspace file's bytes as text.
 *
 *  Read through `fetch`, never navigated to: the endpoint serves everything
 *  outside its narrow text whitelist as an octet-stream attachment precisely so
 *  a browser cannot be pointed at agent-authored HTML. Reading the body here is
 *  unaffected by that header, and the string lands in a <pre>, never in HTML. */
export async function getRunSandboxFile(
  token: string,
  runId: string,
  path: string,
): Promise<string> {
  const res = await authedFetch(runSandboxFileUrl(runId, path), {
    headers: authHeaders(token),
  });
  if (!res.ok) {
    throw new Error(`${res.status}: could not read ${path}`);
  }
  return res.text();
}

/** One workspace file's raw bytes, for saving to disk.
 *
 *  Same endpoint as the text reader above, taken as a Blob so a binary
 *  (`presentation.pptx`) survives the trip — `res.text()` would mangle it. The
 *  caller hands the object URL to `downloadBlob`. */
export async function getRunSandboxFileBlob(
  token: string,
  runId: string,
  path: string,
): Promise<Blob> {
  const res = await authedFetch(runSandboxFileUrl(runId, path), {
    headers: authHeaders(token),
  });
  if (!res.ok) {
    throw new Error(`${res.status}: could not download ${path}`);
  }
  return res.blob();
}

/** The whole run workspace as one zip.
 *
 *  Server-built (stdlib `zipfile`): the alternative is one download per file,
 *  which every browser blocks after a handful — and a ppt_v2 workspace is 36
 *  files. Same authed `fetch` as every other read here, for the same reason
 *  (BUG-031). */
export async function getRunSandboxZip(token: string, runId: string): Promise<Blob> {
  const res = await authedFetch(`${ENV.API_URL}/api/runs/${runId}/sandbox/zip`, {
    headers: authHeaders(token),
  });
  if (!res.ok) {
    throw new Error(
      res.status === 413
        ? "This workspace is too large to archive"
        : `${res.status}: could not archive the workspace`,
    );
  }
  return res.blob();
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
  await request<void>(`/api/runs/${workflowId}`, {
    method: "DELETE",
    headers: authHeaders(token),
  });
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
 *
 * ISS-084 — the response is an ACCEPTANCE, never a confirmation. `accepted: true`
 * (`status: "stopping"`) means a live driver was signalled; the run's terminal
 * arrives on the event stream as `pipeline_cancelled`, which is the ONLY thing that
 * proves it stopped. Do not branch on `cancelled` — it is retained for wire
 * compatibility and is never `true` here (it used to be `true` in exactly the case
 * where cancelling was impossible).
 */
export async function postCancel(
  token: string,
  runId: string,
): Promise<{
  ok: boolean;
  run_id: string;
  accepted?: boolean;
  status?: "stopping" | "not_running";
  cancelled?: boolean;
}> {
  return request<{
    ok: boolean;
    run_id: string;
    accepted?: boolean;
    status?: "stopping" | "not_running";
    cancelled?: boolean;
  }>(
    `/api/runs/${encodeURIComponent(runId)}/cancel`,
    {
      method: "POST",
      headers: authHeaders(token),
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
  // Use a longer timeout for resume — the backend stamps a marker and reads
  // durable events before returning, which can take several seconds on
  // SQLite / under load. 60s is generous vs the default 30s used by other calls.
  return request<{ run_id: string }>(
    `/api/runs/${encodeURIComponent(runId)}/resume`,
    { method: "POST", headers: authHeaders(token) },
    60_000,
  );
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
  // /api/auth/change-password is in SESSION_EXPIRY_EXEMPT_PATHS: a 401 here
  // means "current password is incorrect" (raised by the endpoint body),
  // which AccountSettings.tsx shows inline — not an expired session.
  return request<{ message: string }>("/api/auth/change-password", {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
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
  // Cognito migration (Phase 3): "local" | "cognito". Optional so the type
  // still matches a pre-migration backend response shape.
  auth_provider?: "local" | "cognito";
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

/**
 * Cognito migration Phase 3: PATCH /api/admin/users/{id}/role. First real
 * settable-role endpoint — a role change now also revokes the target's
 * outstanding Cognito access tokens server-side (AdminUserGlobalSignOut) so
 * it takes effect on their very next request. The target user is signed out
 * of their current session as a result — this is expected, not a bug.
 */
export async function adminUpdateRole(
  token: string,
  userId: string,
  isAdmin: boolean
): Promise<AdminUser> {
  return request<AdminUser>(`/api/admin/users/${userId}/role`, {
    method: "PATCH",
    headers: authHeaders(token),
    body: JSON.stringify({ is_admin: isAdmin }),
  });
}

/**
 * Reset another user's password (admin only).
 *
 * This is the ONLY reset path when the pool uses email MFA: AWS disqualifies
 * email as an account-recovery channel whenever it is a second factor, so
 * /api/auth/forgot-password correctly refuses in that configuration.
 *
 * `permanent` defaults to false, which issues a TEMPORARY password — the user is
 * forced to choose their own at next sign-in, so the admin never ends up knowing
 * a live credential for someone else's account. The target's existing sessions
 * are revoked either way.
 */
export async function adminResetUserPassword(
  token: string,
  userId: string,
  newPassword: string,
  permanent = false
): Promise<{ message: string; requires_new_password_at_next_login: boolean }> {
  return request<{ message: string; requires_new_password_at_next_login: boolean }>(
    `/api/admin/users/${userId}/reset-password`,
    {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify({ new_password: newPassword, permanent }),
    }
  );
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
  await request<void>(`/api/admin/users/${userId}`, {
    method: "DELETE",
    headers: authHeaders(token),
  });
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
  /** Authored short label ("PPT"). Sent by the API (workflows.py) but was never
   *  declared here, so callers could not use it. */
  short_name?: string | null;
  /** Manifest `is_beta` — rendered "Coming Soon" in the catalog. Also sent by
   *  the API without ever being declared here. */
  is_beta?: boolean;
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
  /** Per-step skill ids (spec 012, R-01). */
  skills?: string[];
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
  /** The manifest's raw step dicts, verbatim. `steps` above is the COMPILED
   *  projection — fine for display, but lossy: no prompt, tools, instance_id,
   *  depends_on or route. This is the authoring shape, so a caller can render a
   *  step's conditional-gate branches (which workflow/step each outcome hands off
   *  to) and reconstruct an editable composition. Null when the manifest could
   *  not be read. */
  manifest_steps?: import("@/types/index").ManifestStep[] | null;
  /** Spec 016 — this caller's override of this built-in.
   *  `is_overridden`: an override exists AND is switched on, so `steps` /
   *    `manifest_steps` above are ITS steps and a run will execute them.
   *  `has_override`: a row exists at all, on or off — the UI needs this to render
   *    the checkbox unticked rather than losing the way back on.
   *  `showing_original`: this payload is the SYSTEM version even though an
   *    override is enabled, because `?original=true` was passed.
   *  All false/absent for every user who has never saved one. */
  is_overridden?: boolean;
  has_override?: boolean;
  override_id?: string | null;
  showing_original?: boolean;
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
  workflowId: string,
  opts?: { original?: boolean }
): Promise<WorkflowDetail> {
  // `original` forces the SYSTEM version even when this caller has an enabled
  // override — the read-only "compare with original" view (spec 016). It must
  // never decide which plan RUNS; that is `override_enabled` on the row.
  const qs = opts?.original ? "?original=true" : "";
  return request<WorkflowDetail>(
    `/api/workflows/${encodeURIComponent(workflowId)}${qs}`,
    { method: "GET", headers: authHeaders(token) }
  );
}

/**
 * Switch this user's workflow override on or off (spec 016).
 *
 * ONE persisted flag drives both what the screens show and what a run executes,
 * so they cannot disagree — a view-only toggle would let the page display the
 * system version while the launch used the override.
 */
export async function setWorkflowOverrideEnabled(
  token: string,
  overrideId: string,
  enabled: boolean
): Promise<UserWorkflowSummary> {
  return request<UserWorkflowSummary>(
    `/api/user-workflows/${encodeURIComponent(overrideId)}`,
    {
      method: "PATCH",
      headers: { ...authHeaders(token), "Content-Type": "application/json" },
      body: JSON.stringify({ override_enabled: enabled }),
    }
  );
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
  // Spec 012 (R-27/R-29) — the full `{"steps": [...]}` manifest, present once
  // the composition uses a per-node skill, custom prompt, or sub-agent tree.
  // Mutually exclusive with `selections` (the backend `_project` splits the
  // reused `manifest_json` column across these two fields). ComposerPage's
  // `initialManifestSteps` reads `manifest?.steps` from this on reload.
  manifest?: WorkflowManifest | null;
  // Persisted UI-attached skills/hooks — same shape sent to the launch path
  // (`attached_skills`/`attached_hooks` in useWorkflow.ts's startPipeline
  // payload). NULL/absent ⇒ none attached.
  attached_skills?: Array<Record<string, unknown>> | null;
  attached_hooks?: Array<Record<string, unknown>> | null;
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
    // Same shape as useWorkflow.ts's startPipeline `attached_skills`/
    // `attached_hooks` payload. Omitted when empty (payload stays byte-identical
    // for saves with no skills/hooks attached — INV-3).
    attached_skills?: Array<Record<string, unknown>>;
    attached_hooks?: Array<Record<string, unknown>>;
    /**
     * Spec 012 (T36) — the full step-based manifest `{steps: [...]}` the canvas
     * produces. A SIBLING of `selections`, not a widening of it: both write the
     * same `manifest_json` column but are different shapes with different
     * validators, so sending BOTH is a 422.
     */
    manifest?: Record<string, unknown>;
    /**
     * Spec 016 — the BUILT-IN id this save overrides for its owner ("ppt").
     * Absent for an ordinary save. When present the POST UPSERTS on
     * (user_id, overrides_pipeline_type), so a second save updates the same row
     * instead of 409ing on the name — "save once, or overwrite always".
     *
     * Pair it with `manifest`, never `selections`: the override resolve reads
     * `manifest_json["steps"]`, so a selections-shaped row stores fine and then
     * silently never applies.
     */
    overrides_pipeline_type?: string;
    /** The base manifest's `version` at save time, for a later
     *  "the original has changed since you customised it" notice. */
    base_version?: number;
  }
): Promise<UserWorkflowSummary> {
  return request<UserWorkflowSummary>("/api/user-workflows", {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify(body),
  });
}

/**
 * Update an existing saved workflow in place (PATCH analog of
 * `createUserWorkflow`). Every field is optional — an absent field leaves the
 * stored value untouched. `agent_ids`/`base_pipeline_type` are NOT accepted
 * (composition is immutable after creation — see backend
 * `UpdateUserWorkflowRequest`); this only renames/updates description,
 * model_overrides, selections, and attached skills/hooks on the existing row.
 */
export async function updateUserWorkflow(
  token: string,
  workflowId: string,
  body: {
    name?: string;
    description?: string;
    model_overrides?: Record<string, string>;
    selections?: Record<string, Record<string, unknown>>;
    attached_skills?: Array<Record<string, unknown>>;
    attached_hooks?: Array<Record<string, unknown>>;
  }
): Promise<UserWorkflowSummary> {
  return request<UserWorkflowSummary>(`/api/user-workflows/${workflowId}`, {
    method: "PATCH",
    headers: authHeaders(token),
    body: JSON.stringify(body),
  });
}

/**
 * Save a workflow — the ONE create-vs-update dispatch point (ISS-167). Every
 * "Save workflow" surface (Composer, the prototype/ppt LaunchWizard, ...) calls
 * this instead of each re-implementing `userWorkflowId ? update : create`.
 * `base_pipeline_type`/`agent_ids` are required in `body` because `createUserWorkflow`
 * needs them; when `userWorkflowId` is set they're simply not forwarded — PATCH
 * doesn't accept them (composition is immutable post-create).
 */
export async function saveUserWorkflow(
  token: string,
  userWorkflowId: string | undefined,
  body: {
    name: string;
    description?: string;
    base_pipeline_type: string;
    agent_ids: string[];
    model_overrides?: Record<string, string>;
    selections?: Record<string, Record<string, unknown>>;
    attached_skills?: Array<Record<string, unknown>>;
    attached_hooks?: Array<Record<string, unknown>>;
  }
): Promise<UserWorkflowSummary> {
  if (userWorkflowId) {
    const { base_pipeline_type: _bpt, agent_ids: _aids, ...updateBody } = body;
    void _bpt;
    void _aids;
    return updateUserWorkflow(token, userWorkflowId, updateBody);
  }
  return createUserWorkflow(token, body);
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
  await request<void>(`/api/user-workflows/${id}`, {
    method: "DELETE",
    headers: authHeaders(token),
  });
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
  return request<ExtractTextResponse>("/api/files/extract-text", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
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
