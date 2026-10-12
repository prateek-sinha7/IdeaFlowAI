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

const BASE_URL = ENV.API_URL;

const TOKEN_KEY = "auth_token";

/** Refresh the browser token one minute before its Cognito expiry. */
export const SESSION_REFRESH_SKEW_MS = 60_000;

type TokenChangeListener = () => void;
type SessionExpiryListener = () => void;

const tokenChangeListeners = new Set<TokenChangeListener>();
const sessionExpiryListeners = new Set<SessionExpiryListener>();
let sessionHasExpired = false;

function notifyTokenChange(): void {
  for (const listener of tokenChangeListeners) {
    try {
      listener();
    } catch {
      // A subscriber must never prevent login, logout, or a token refresh.
    }
  }
}

// --- Token management ---

export function getToken(): string | null {
  // Guard on localStorage itself, not on `window`. They are not the same test:
  // Node test runners and some SSR shims define a partial `window` with no
  // localStorage, so the window check passed and this threw
  // "Cannot read properties of undefined (reading 'getItem')".
  if (typeof localStorage === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

/** Decode a Cognito JWT's expiry into milliseconds, or null when unavailable. */
export function getTokenExpiryMs(token: string | null): number | null {
  if (!token) return null;

  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const decoded = JSON.parse(
      atob(payload.replace(/-/g, "+").replace(/_/g, "/")),
    ) as { exp?: unknown };
    return typeof decoded.exp === "number" ? decoded.exp * 1000 : null;
  } catch {
    return null;
  }
}

/** Subscribe to updates made through the shared browser-token seam. */
export function onTokenChanged(listener: TokenChangeListener): () => void {
  tokenChangeListeners.add(listener);
  return () => {
    tokenChangeListeners.delete(listener);
  };
}

/** Subscribe to a confirmed terminal Cognito-session failure. */
export function onSessionExpired(listener: SessionExpiryListener): () => void {
  sessionExpiryListeners.add(listener);

  if (sessionHasExpired) {
    try {
      listener();
    } catch {
      // A late subscriber must not break the request that expired the session.
    }
  }

  return () => {
    sessionExpiryListeners.delete(listener);
  };
}

export function setToken(token: string): void {
  sessionHasExpired = false;
  localStorage.setItem(TOKEN_KEY, token);
  notifyTokenChange();
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
  notifyTokenChange();
}

/**
 * End the local browser session after a terminal bearer-auth failure.
 *
 * The app-wide AuthSessionProvider owns navigation so API helpers remain
 * transport-focused. Retaining this state means a provider that mounts after
 * an early failure still receives the redirect signal.
 */
export function expireSession(): void {
  if (sessionHasExpired) return;

  sessionHasExpired = true;
  clearToken();

  for (const listener of sessionExpiryListeners) {
    try {
      listener();
    } catch {
      // Session cleanup must proceed even if a UI subscriber has failed.
    }
  }
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

// specs/014 — host capacity admission gate. The backend's structured 503
// rejection body (`_reject("host_capacity_exhausted", ..., signals=[...])` in
// run_commands.py / the inline twin in handoff.py). Declared once here so
// every caller and the ServiceBusyProvider share one shape instead of each
// re-deriving it from a loosely-typed `unknown`.
export interface CapacitySignal {
  name: string;
  value: number;
  threshold: number;
}

export interface CapacityRejectionDetail {
  error: string;
  code: "host_capacity_exhausted";
  recoverable: true;
  retry_after_seconds: number;
  signals: CapacitySignal[];
}

function isCapacityRejectionDetail(
  detail: unknown,
): detail is CapacityRejectionDetail {
  return (
    typeof detail === "object" &&
    detail !== null &&
    (detail as { code?: unknown }).code === "host_capacity_exhausted"
  );
}

type CapacityRejectionListener = (detail: CapacityRejectionDetail) => void;

// Every 503 host_capacity_exhausted rejection reaches the UI through an
// `ApiError` — every REST call site in this module, and the launch branch of
// `RunConnectionProvider.sendCommand` (which imports this same class), throw
// one on a non-ok response. Hooking the detection into the constructor is
// therefore a SINGLE seam that catches every current and future call site,
// rather than re-instrumenting each fetch individually. `ServiceBusyProvider`
// is the sole subscriber; nothing else needs to know a rejection happened.
const _capacityRejectionListeners = new Set<CapacityRejectionListener>();

/**
 * Subscribe to every capacity-gate rejection ANY `ApiError` construction
 * surfaces, anywhere in the app. Returns an unsubscribe function (the same
 * pattern `RunConnectionProvider.subscribe` uses).
 */
export function onCapacityRejected(
  listener: CapacityRejectionListener,
): () => void {
  _capacityRejectionListeners.add(listener);
  return () => {
    _capacityRejectionListeners.delete(listener);
  };
}

// Admin MFA gate. `admin.py::require_admin` refuses an admin whose CURRENT
// SESSION carries no second-factor proof, and answers with a machine-readable
// body rather than a bare "Admin access required." The distinction matters:
// a plain 403 is indistinguishable from "you are not an admin", which has
// nothing the user can do about it, whereas this one has an exact remedy and
// the server names the path to it.
export interface AdminMfaRequiredDetail {
  code: "admin_mfa_required";
  /** Server-named enrolment endpoint. Never hardcode the route from this. */
  enroll_path: string;
}

function isAdminMfaRequiredDetail(
  detail: unknown,
): detail is AdminMfaRequiredDetail {
  return (
    typeof detail === "object" &&
    detail !== null &&
    (detail as { code?: unknown }).code === "admin_mfa_required"
  );
}

type AdminMfaRequiredListener = (detail: AdminMfaRequiredDetail) => void;

const _adminMfaRequiredListeners = new Set<AdminMfaRequiredListener>();

/**
 * Subscribe to every admin-MFA refusal ANY `ApiError` construction surfaces.
 *
 * Detection lives in the `ApiError` constructor for the same reason the
 * capacity gate above does: it is one seam that covers every existing and
 * future `/api/admin/*` call site. That is not merely tidy here — several admin
 * call sites swallow their error with a bare `catch {}` to render a generic
 * "could not load" state, so a per-call-site handler would miss exactly the
 * requests most likely to hit this gate.
 */
export function onAdminMfaRequired(
  listener: AdminMfaRequiredListener,
): () => void {
  _adminMfaRequiredListeners.add(listener);
  return () => {
    _adminMfaRequiredListeners.delete(listener);
  };
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

    if (status === 503 && isCapacityRejectionDetail(detail)) {
      for (const listener of _capacityRejectionListeners) {
        // A subscriber's own bug must never break the request that reported
        // the rejection — swallow and move on, matching the fire-and-forget
        // fan-out RunConnectionProvider.subscribe already uses.
        try {
          listener(detail);
        } catch {
          /* non-fatal — see comment above */
        }
      }
    }

    if (status === 403 && isAdminMfaRequiredDetail(detail)) {
      for (const listener of _adminMfaRequiredListeners) {
        try {
          listener(detail);
        } catch {
          /* non-fatal — see the capacity fan-out above */
        }
      }
    }
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
  // One owner for session expiry: expireSession() clears the token and signals
  // AuthSessionProvider, which performs the (single, latched) login redirect.
  expireSession();
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

export function refreshOnce(): Promise<string | null> {
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

function hasBearerAuthorization(options: RequestInit): boolean {
  const authorization = new Headers(
    options.headers as HeadersInit | undefined,
  ).get("Authorization");
  return authorization?.startsWith("Bearer ") ?? false;
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
  dropAccountReadsOnWrite(init?.method);
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
 *    off, so a second 401 terminates the session without recursion.
 * 2. **Only for requests that actually sent a bearer.** An unauthenticated 401
 *    (e.g. wrong password on `/login`) is a real answer, not an expiry.
 * 3. **Never for the refresh endpoint itself**, which would be circular.
 */
async function fetchWithAuth(
  path: string,
  options: RequestInit = {},
  timeoutMs: number = REQUEST_TIMEOUT_MS,
  retryOn401 = true
): Promise<Response> {
  dropAccountReadsOnWrite(options.method);
  const url = `${BASE_URL}${path}`;
  const response = await fetchWithTimeout(url, options, timeoutMs);

  if (!response.ok) {
    if (
      response.status === 401 &&
      retryOn401 &&
      path !== REFRESH_PATH &&
      hasBearerAuthorization(options)
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

// --- Shared read-only GET cache (ISS-782 / ISS-796) ------------------------
//
// The capability catalog, the user's preferences and the analytics summary are
// SHARED page data: several independently-mounted components each fetch them
// for themselves, and no component owns the result. A React hook cannot fix
// that — `useAgentCapabilities` (AgentsPopup.tsx) was written to be the shared
// source and still fires one request per CALL SITE, because a hook's state is
// per-call-site, not per-app. So the sharing has to live below the components,
// here, keyed by URL + token.
//
// Kept for a short TTL rather than in-flight only: the duplicate callers do NOT
// all mount together. CanvasView fetches the catalog when the canvas opens and
// its own child CanvasConfigRail asks again seconds later when the agent-config
// tab is clicked (ISS-796), by which time an in-flight-only dedupe has already
// resolved and forgotten. The TTL is what also absorbs React StrictMode's
// mount→unmount→remount double-invoke in dev (ISS-782).
//
// Only idempotent catalog/summary GETs go through here, and a mutation of the
// same resource evicts its entry (see updatePreferences). Run/workflow lists
// deliberately do NOT: their callers refetch precisely to observe a change
// (a cancel clearing the header's "N Running" pill, a gate flipping a status).
//
// ISS-800 / ISS-829 (QA-PS-048): a run's four audit projections (gate-events,
// validation-results, exec-runs, hook-runs) do go through here. The Audit tab
// and the Steps tab's gate strip read the same gate-events one tab switch
// apart, which an in-flight-only guard cannot join. They are append-only logs,
// so the cost is bounded: on a still-live run a reopened tab can lag by up to
// the TTL, and any write drops the lot (dropAccountReadsOnWrite).
const SHARED_GET_TTL_MS = 30_000;
// ISS-833: 30 s is shorter than the gap this cache exists to bridge for the
// composer. CanvasView fetches the palette when the canvas mounts; its child
// CanvasConfigRail asks again only when the user opens an agent's config tab —
// naming a workflow, dragging agents in and reading their descriptions is a
// multi-MINUTE task, so the entry had expired and the second call refetched
// 27 KB for a byte-identical answer. `GET /api/capabilities` is a live
// enumeration of the backend's capability registry plus the model catalog
// (backend/app/api/capabilities.py — auth-gated, but the body carries no
// per-user or per-run data), so it cannot change without a backend restart,
// and a page load starts this Map empty. A long entry is therefore stale only
// across a deploy the user has not reloaded through.
const CATALOG_GET_TTL_MS = 30 * 60_000;
const sharedGetCache = new Map<string, { at: number; promise: Promise<unknown> }>();

function ttlFor(path: string): number {
  return path.startsWith("/api/capabilities") ? CATALOG_GET_TTL_MS : SHARED_GET_TTL_MS;
}

function cachedGet<T>(path: string, token: string): Promise<T> {
  // Token in the key, so an account switch can never be served the previous
  // account's catalog or preferences out of this cache.
  const key = `${token}\u0000${path}`;
  const hit = sharedGetCache.get(key);
  if (hit && Date.now() - hit.at < ttlFor(path)) return hit.promise as Promise<T>;
  const promise = request<T>(path, {
    method: "GET",
    headers: authHeaders(token),
  }).catch((e) => {
    // A failure is never cached — the next caller retries for real.
    if (sharedGetCache.get(key)?.promise === promise) sharedGetCache.delete(key);
    throw e;
  });
  sharedGetCache.set(key, { at: Date.now(), promise });
  return promise;
}

/** Drop every cached copy of `path` (all tokens) after it has been mutated. */
function invalidateCachedGet(path: string): void {
  for (const key of [...sharedGetCache.keys()]) {
    if (key.endsWith(`\u0000${path}`)) sharedGetCache.delete(key);
  }
}

/**
 * ISS-799 — the same eviction, for the mutations that never name a path here.
 * `updatePreferences` can call `invalidateCachedGet` because its PUT sits in
 * this file next to the GET it shadows; the constitution editor's PUT/DELETE
 * (`AccountSettings.tsx`, via `authedFetch`) and the MFA enable/disable POSTs
 * do not, and a cached read that outlives its own write is a wrong answer, not
 * a slow one. Every non-GET through either shared path drops the whole cache —
 * the entries are cheap to refill and nothing in here is worth a stale read.
 */
function dropAccountReadsOnWrite(method: string | undefined): void {
  if ((method ?? "GET").toUpperCase() !== "GET") sharedGetCache.clear();
}

/**
 * ISS-830 / ISS-831 (QA-PS-048) — `cachedGet()`'s in-flight-only sibling, for
 * the run reads whose callers refetch to watch a live run move on: the run
 * record (`getWorkflow`, 8+ call sites), its revision family and its workspace
 * listing. Callers asking for the same path while a request is open share it —
 * StrictMode's doubled mount effects, PreviewPanel's deliverable resolver
 * racing the Workspace tab — and the entry is dropped the moment it settles,
 * so a later call still goes to the network. Same shape as
 * `inFlightWorkflowDetail` below.
 */
const inFlightGets = new Map<string, Promise<unknown>>();

function singleFlightGet<T>(path: string, token: string): Promise<T> {
  const key = `${token}\u0000${path}`;
  const pending = inFlightGets.get(key);
  if (pending) return pending as Promise<T>;
  const started = request<T>(path, {
    method: "GET",
    headers: authHeaders(token),
  }).finally(() => {
    inFlightGets.delete(key);
  });
  inFlightGets.set(key, started);
  return started;
}

// --- Auth API ---

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

// --- Self-service password reset (Phase 6 item 3, Decision 10) ---

/**
 * Start a self-service password reset. Backend ALWAYS returns 202 with a
 * generic message, whether or not the address exists (Cognito's own
 * `prevent_user_existence_errors` does the same for login) -- do not treat a
 * 202 as proof the account exists, and do not surface a different message for
 * one branch vs another.
 *
 * A 409 means self-service reset is unavailable in this deployment (email is
 * configured as an MFA factor, which disqualifies it as a recovery channel
 * too -- an AWS constraint, not a bug). Callers should show that 409's own
 * `detail` message rather than a generic error, so the user knows to contact
 * an administrator instead of retrying.
 */
export async function forgotPassword(email: string): Promise<{ message: string }> {
  return request<{ message: string }>("/api/auth/forgot-password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
}

/** Complete a self-service password reset with the code Cognito emailed. */
export async function confirmForgotPassword(
  email: string,
  code: string,
  newPassword: string
): Promise<{ message: string }> {
  return request<{ message: string }>("/api/auth/forgot-password/confirm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, code, new_password: newPassword }),
  });
}

// --- MFA (account security) ---

/** Read the caller's second-factor state and what this deployment offers. */
export async function getMfaStatus(token: string): Promise<MfaStatus> {
  // ISS-799: shared-GET cached — SecuritySection's mount effect is the only
  // call site, and it is double-invoked by `next dev`.
  return cachedGet<MfaStatus>("/api/auth/mfa", token);
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

/** Server response to the first step of the TOTP enrolment ceremony. */
export interface TotpAssociation {
  /** Shared secret, returned ONCE and never stored server-side. */
  secret: string;
  issuer: string;
  account: string;
  /** Standard `otpauth://` URI, ready to render as a QR code. */
  otpauth_uri: string;
}

/**
 * Begin TOTP enrolment: provision a shared secret for an authenticator app.
 *
 * Requires only an authenticated caller — deliberately NOT admin-gated, because
 * this is the way OUT of the admin-MFA 403. Gating it behind `require_admin`
 * would make the only escape from that refusal pass through the same refusal.
 *
 * The secret is shown once. Enrolment is not complete, and no factor exists,
 * until `verifyTotp` proves possession.
 */
export async function associateTotp(token: string): Promise<TotpAssociation> {
  return request<TotpAssociation>("/api/auth/mfa/totp/associate", {
    method: "POST",
    headers: authHeaders(token),
  });
}

/**
 * Complete TOTP enrolment by proving possession of the secret.
 *
 * A wrong or stale code is a 400 with a message worth showing verbatim — the
 * usual cause is a code that scrolled over between typing and submitting, which
 * the user fixes by reading the next one.
 *
 * Note for callers: succeeding here enrols the factor but does NOT satisfy the
 * admin gate for the CURRENT session. That gate compares the bearer's `iat`
 * against `mfa_verified_at`, and the token in hand was minted before this
 * enrolment, so it can never carry the proof. Signing out and back in is
 * required, and the UI must say so rather than bouncing the user back to a 403.
 */
export async function verifyTotp(
  token: string,
  code: string,
  deviceName?: string
): Promise<{ message: string }> {
  return request<{ message: string }>("/api/auth/mfa/totp/verify", {
    method: "POST",
    headers: { ...authHeaders(token), "Content-Type": "application/json" },
    body: JSON.stringify({ code, device_name: deviceName }),
  });
}

export async function getMe(token: string): Promise<User> {
  // ISS-801: shared-GET cached — `[...view]/page.tsx`, `AccountSettings`,
  // `admin/page.tsx` and `LaunchWizard` each fetch the profile for themselves,
  // and no two of them mount in the same tick, so an in-flight-only guard would
  // not catch them.
  return cachedGet<User>("/api/auth/me", token);
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
  // A14 — non-fatal cap/degrade messages (e.g. a review-loop cap absorbed with
  // a resolved deliverable) that did NOT flip the run to "degraded". Optional:
  // absent on every raw row until the read endpoint is taught to surface it
  // (backend A14 proposal, not yet wired) — parses to undefined either way.
  warnings?: string[] | null;
  // SGV2 task 11.3: chain-source projection — present only when the run was
  // launched via exact-ref chaining (v2). All fields optional so legacy rows parse.
  chain_source_run_id?: string | null;
  chain_source_short_id?: string | null;
  chain_source_workflow_id?: string | null;
  chain_source_published_status?: string | null;
  chain_source_visible_tag?: string | null;
  // SGV2 task 11.3: finalization / payload-chainability fields.
  payload_chainable?: boolean | null;
  non_chainable_reason?: string | null;
  chain_context_installed?: boolean | null;
  chain_unavailable_reason?: string | null;
  finalization_reason?: string | null;
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
    // A14 — additive; absent (not null/[]) when no warning fired, mirroring
    // the `pipeline_complete` event's own presence convention.
    warnings: raw.warnings && raw.warnings.length > 0 ? raw.warnings : undefined,
    // SGV2 task 11.3: chain-source projection (v2 exact-ref chaining).
    // Absent on legacy runs where none of the source fields are set.
    chainSource: raw.chain_source_run_id
      ? {
          id: raw.chain_source_run_id,
          shortId: raw.chain_source_short_id ?? raw.chain_source_run_id.slice(0, 8),
          workflowId: raw.chain_source_workflow_id ?? "",
          publishedStatus: raw.chain_source_published_status ?? "",
          visibleTag: raw.chain_source_visible_tag ?? null,
        }
      : undefined,
    // SGV2 task 11.3: finalization / payload-chainability fields.
    chainContextInstalled: raw.chain_context_installed ?? undefined,
    payloadChainable: raw.payload_chainable ?? undefined,
    nonChainableReason: raw.non_chainable_reason ?? undefined,
    chainUnavailableReason: raw.chain_unavailable_reason ?? undefined,
    finalizationReason: raw.finalization_reason ?? undefined,
    agentCount: raw.agent_count,
    duration: raw.duration ?? undefined,
    error: raw.error ?? undefined,
    createdAt: ensureUTC(raw.created_at),
    completedAt: raw.completed_at ? ensureUTC(raw.completed_at) : undefined,
  };
}

async function fetchWorkflowPage(
  path: string,
  token: string
): Promise<{ runs: WorkflowRun[]; total: number }> {
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

/**
 * Single-flight guard for `getWorkflows()` — ISS-783 (QA-PS-037).
 *
 * A cold `/runs` load asks for this exact page from three independent places —
 * WorkflowHistory's `[filterType]` and `[recentRuns]` effects, page.tsx's own
 * mount effect and RunConnectionProvider's app-wide boot effect — each doubled
 * again by StrictMode in dev, so the same 37 KB run list came back 5-6 times.
 * Callers asking for the SAME query while a request is still open now share
 * that one request, exactly like `refreshOnce()` above does for token refresh;
 * a double-click on the history Refresh button coalesces the same way
 * (ISS-795).
 *
 * The entry is dropped the moment the request settles, so this de-duplicates
 * and does NOT cache: a refetch started after the previous one finished — the
 * post-mutation refetches in page.tsx, the auto-refresh timer — still goes to
 * the network.
 */
const inFlightWorkflows = new Map<string, Promise<{ runs: WorkflowRun[]; total: number }>>();

export function getWorkflows(
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

  // Keyed by token too: two identities must never share a run list.
  const key = `${token}\n${path}`;
  const pending = inFlightWorkflows.get(key);
  if (pending) return pending;

  const started = fetchWorkflowPage(path, token).finally(() => {
    inFlightWorkflows.delete(key);
  });
  inFlightWorkflows.set(key, started);
  return started;
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

/** RFN-002 — per-agent token breakdown derived from agent_outputs.
 *  Numbers only (T-38-Leak): agent_name is the display name stored in
 *  agent_outputs[].name — already surfaced by _SUMMARY_SAFE_AGENT_KEYS.
 *  No output / prompt / thinking text. */
export interface AnalyticsAgentRollup {
  agent_id: string;
  agent_name: string;
  count: number;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  cost: number;
  /** ISS-643 — sorted list of distinct pipeline type(s) this agent ran under
   *  in the query window. Derived server-side from WorkflowRun.type — no schema
   *  change required. Multi-pipeline agents (ADR-0023) will have >1 entry. */
  pipeline_types: string[];
}

export interface AnalyticsSummary {
  kpis: AnalyticsKpis;
  daily: AnalyticsDailyBucket[];
  pipelines: AnalyticsPipelineRollup[];
  models: AnalyticsModelRollup[];
  /** RFN-002 — per-agent token breakdown. Empty array on accounts with no
   *  completed runs or legacy runs whose agent_outputs predate ISS-165. */
  agents: AnalyticsAgentRollup[];
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
  // ISS-782: shared-GET cached, keyed on the fully-qualified query string — a
  // filter change is a different key and still re-queries the server.
  return cachedGet<AnalyticsSummary>(
    `/api/analytics/summary?${params.toString()}`,
    token
  );
}

export async function getWorkflow(
  token: string,
  workflowId: string
): Promise<WorkflowRun> {
  const raw = await singleFlightGet<RawWorkflowRun>(`/api/runs/${workflowId}`, token);
  return normalizeWorkflowRun(raw);
}

/** Fetch the revision family (root + ordered members) for a run.
 *  Returns the raw wire shape (unnormalized snake_case) like getChainContext. */
export async function getRunFamily(
  token: string,
  runId: string
): Promise<RunFamily> {
  return singleFlightGet<RunFamily>(`/api/runs/${runId}/family`, token);
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
  // RFN-001 — already in _SUMMARY_SAFE_AGENT_KEYS and persisted in agent_outputs;
  // adding the field here so TS consumers can read it without a cast.
  model_id?: string;
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
  // SGV2 task 11.4: chain-source projection for the run being summarised —
  // mirrors FamilyMember's chain_source_* fields. Present only for v2-chained
  // runs; absent on legacy / non-chained rows. NEVER carries an internal ref
  // name; chain_source_visible_tag is null for untagged sources.
  chain_context_installed?: boolean | null;
  chain_source_run_id?: string | null;
  chain_source_short_id?: string | null;
  chain_source_workflow_id?: string | null;
  chain_source_published_status?: string | null;
  chain_source_visible_tag?: string | null;
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
  // ISS-871 / FIX-647: use singleFlightGet so concurrent identical calls
  // (e.g. handleSelectWorkflowRun firing once pre-remount and again from the
  // cold-mount T11 effect post-remount) share one in-flight request rather
  // than launching a second 2+ MB fetch.  The key includes the afterSeq
  // fragment so a cursor-advancing call (afterSeq > 0) never coalesces with
  // the full-history call (afterSeq == 0).  Mirrors getRunFamily/getWorkflow.
  const res = await singleFlightGet<RunEventsResponse>(
    `/api/runs/${encodeURIComponent(runId)}/events?after=${afterSeq}`,
    token,
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
  ref?: string,
): Promise<SandboxListing> {
  const url = ref
    ? `/api/runs/${runId}/sandbox?ref=${encodeURIComponent(ref)}`
    : `/api/runs/${runId}/sandbox`;
  return singleFlightGet<SandboxListing>(url, token);
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
  const at = (p: string) => listing.files.find((f) => f.path === p);
  // ISS-768/ISS-774 — for the NOMINAL-name strategies (`streamed_text`,
  // `serialized_sandbox`, `ppt`) the declared basename is never a root file:
  // `build_flat_payload` materializes it only into `.chain/<name>` (engine.py),
  // which `_payload_allowlist` then stages. Matching root alone returned null on
  // every such run — permanently disabling the header Download button on all of
  // `user_stories`, `user_stories_revision` and `custom`. Root still wins
  // OUTRIGHT: the `.chain/` pass runs only after every root candidate has missed,
  // so nothing that resolves today resolves differently (ppt_v2's root `.pptx`
  // still beats a chained `.html`). `.chain/` is listed and served like every
  // reserved subtree (only git metadata is hidden), and both callers already take
  // the basename of the returned path for display and for the download filename.
  return candidates.map(at).find(Boolean)
    ?? candidates.map((c) => at(`.chain/${c}`)).find(Boolean)
    ?? null;
}

/** The URL a workspace file's bytes are served from.
 *
 *  NEVER navigate a browser to this (an `<a href>`, `window.open`): auth here is
 *  a bearer token held in JS, not a cookie, so a navigation arrives anonymous and
 *  the API answers `{"detail":"Not authenticated"}` — which the browser renders
 *  instead of saving anything. Both readers below send the header. */
export function runSandboxFileUrl(runId: string, path: string, ref?: string): string {
  const base = `${ENV.API_URL}/api/runs/${runId}/sandbox/file?path=${encodeURIComponent(path)}`;
  return ref ? `${base}&ref=${encodeURIComponent(ref)}` : base;
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
  ref?: string,
): Promise<string> {
  const res = await authedFetch(runSandboxFileUrl(runId, path, ref), {
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
  ref?: string,
): Promise<Blob> {
  const res = await authedFetch(runSandboxFileUrl(runId, path, ref), {
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
export async function getRunSandboxZip(token: string, runId: string, ref?: string): Promise<Blob> {
  const url = ref
    ? `${ENV.API_URL}/api/runs/${runId}/sandbox/zip?ref=${encodeURIComponent(ref)}`
    : `${ENV.API_URL}/api/runs/${runId}/sandbox/zip`;
  const res = await authedFetch(url, {
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

/** List the git version tags available for this run's sandbox.
 *
 *  Returns the tag names (e.g. ["v1", "v2"]) as an array.  Empty when the
 *  run has not completed or the sandbox has no git history yet.
 *
 *  Requirement 17 AC1 / Requirement 19 AC2. */
export async function getRunSandboxRefs(
  token: string,
  runId: string,
): Promise<string[]> {
  const data = await request<{ run_id: string; refs: string[] }>(
    `/api/runs/${runId}/sandbox/refs`,
    { method: "GET", headers: authHeaders(token) },
  );
  return data.refs ?? [];
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
  /** ISS-430: true when the current account's tier may select this model. */
  allowed?: boolean;
}

export interface UserPreferences {
  preferred_model: string | null;
  available_models: ModelOption[];
}

export async function getPreferences(token: string): Promise<UserPreferences> {
  // ISS-782: shared-GET cached — AnalyticsPage and AccountSettings each fetch
  // this for themselves.
  return cachedGet<UserPreferences>("/api/settings/preferences", token);
}

/**
 * ISS-799 — the Constitution tab's mount read. It used to hand-roll
 * `authedFetch` at the call site, where a second mount invocation had nothing
 * to share; routed through the shared cache it is fetched once, and the PUT and
 * DELETE next to it drop that entry via `dropAccountReadsOnWrite`.
 */
export async function getConstitution(
  token: string
): Promise<{ content?: string | null }> {
  return cachedGet<{ content?: string | null }>("/api/settings/constitution", token);
}

export async function updatePreferences(
  token: string,
  preferred_model: string | null
): Promise<UserPreferences> {
  // The PUT makes any cached GET of the same path stale — evict before the
  // write so a concurrent reader cannot re-cache the pre-write value.
  invalidateCachedGet("/api/settings/preferences");
  const updated = await request<UserPreferences>("/api/settings/preferences", {
    method: "PUT",
    headers: authHeaders(token),
    body: JSON.stringify({ preferred_model }),
  });
  invalidateCachedGet("/api/settings/preferences");
  return updated;
}

// --- Admin API ---

export interface AdminUser {
  id: string;
  email: string;
  tier: "basic" | "pro" | "enterprise" | "hexaware";
  is_admin: boolean;
  status: "active" | "disabled";
  created_at: string;
  workflow_run_count: number;
}

/**
 * Single-flight guard for `adminListUsers()` — ISS-789 / ISS-816 (QA-PS-042).
 *
 * `admin/page.tsx`'s boot effect has no in-flight guard of its own, so a
 * client-side navigation into `/admin` — where React StrictMode double-invokes
 * the mount in dev — fetched the same user list twice. Callers asking while a
 * request is still open share that one request, exactly like
 * `inFlightWorkflows` above does for the run list.
 *
 * De-duplicates, does NOT cache: the entry is dropped the moment the request
 * settles, so any later refetch still goes to the network. That matters here —
 * this list is mutated from the same page (create/delete/tier/role), and a
 * cached read that outlives its own write would be a wrong answer, which is
 * why `cachedGet()`'s TTL is the wrong tool for it.
 */
const inFlightAdminUsers = new Map<string, Promise<AdminUser[]>>();

export function adminListUsers(token: string): Promise<AdminUser[]> {
  // Keyed by token: two identities must never share a user list.
  const pending = inFlightAdminUsers.get(token);
  if (pending) return pending;

  const started = request<AdminUser[]>("/api/admin/users", {
    method: "GET",
    headers: authHeaders(token),
  }).finally(() => {
    inFlightAdminUsers.delete(token);
  });
  inFlightAdminUsers.set(token, started);
  return started;
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
 * The backend generates the temporary password and never returns it to the
 * administrator. Sending an empty JSON object preserves the strict API
 * boundary that rejects password-bearing input, while the recipient is forced
 * through Cognito's NEW_PASSWORD_REQUIRED challenge on their next sign-in.
 */
export type AdminPasswordResetResponse = {
  status: "temporary_password_set";
};

export async function adminResetUserPassword(
  token: string,
  userId: string,
): Promise<AdminPasswordResetResponse> {
  return request<AdminPasswordResetResponse>(
    `/api/admin/users/${userId}/reset-password`,
    {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify({}),
    }
  );
}

/**
 * Create a user by INVITATION (Cognito migration Phase 3, Decision 6). No
 * password parameter -- the backend's `CreateUserRequest` is `extra=forbid`
 * and no longer accepts one at all. Cognito generates a temporary password
 * and emails it directly to the new account; this app never sees it, so
 * there is nothing here for an admin to type or store.
 */
export async function adminCreateUser(
  token: string,
  email: string,
  tier: string,
  is_admin: boolean
): Promise<AdminUser> {
  return request<AdminUser>("/api/admin/users", {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ email, tier, is_admin }),
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

/**
 * Disable a user account (Cognito migration Phase 3, Decision 6). Reversible
 * via `adminEnableUser`, unlike delete -- revokes API keys and the stored
 * refresh token, disables sign-in at Cognito, and signs out every existing
 * session server-side.
 */
export async function adminDisableUser(
  token: string,
  userId: string
): Promise<AdminUser> {
  return request<AdminUser>(`/api/admin/users/${userId}/disable`, {
    method: "POST",
    headers: authHeaders(token),
  });
}

/**
 * Re-enable a disabled user account. Does NOT restore API keys or the
 * refresh token revoked on disable -- the user re-authenticates normally.
 */
export async function adminEnableUser(
  token: string,
  userId: string
): Promise<AdminUser> {
  return request<AdminUser>(`/api/admin/users/${userId}/enable`, {
    method: "POST",
    headers: authHeaders(token),
  });
}

// --- Admin capacity matrix API (specs/014) ---

/** One EC2 instance's row, mirroring admin_capacity.py's InstanceCapacityResponse. */
export interface AdminCapacityInstance {
  instance_id: string;
  instance_type: string | null;
  is_self: boolean;
  cpu_used_percent: number | null;
  mem_used_percent: number | null;
  cpu_user_percent: number | null;
  cpu_system_percent: number | null;
  cpu_iowait_percent: number | null;
  reading_age_seconds: number | null;
  stale: boolean;
}

/** The admission-gate's current state, mirroring CapacityGateResponse. */
export interface AdminCapacityGate {
  enabled: boolean;
  state: "allowing" | "blocking" | "blind";
  blind_reason: string | null;
  cpu_threshold_percent: number;
  mem_threshold_percent: number;
  signals: CapacitySignal[];
  engaged_at: string | null;
  evaluated_at: string;
}

/** `GET /api/admin/capacity`'s full response, mirroring CapacityMatrixResponse. */
export interface AdminCapacityMatrix {
  collected_at: string;
  self_instance_id: string | null;
  instance_source: "override" | "discovery" | "none";
  instances: AdminCapacityInstance[];
  gate: AdminCapacityGate;
}

/**
 * Admin-only host capacity matrix (specs/014). Read-only over the backend's
 * process-local snapshot — never triggers an AWS call itself. Reuses the same
 * `require_admin` guard every other `/api/admin/*` route does, so a non-admin
 * gets the SAME 403 as `adminListUsers`.
 */
export async function adminListCapacity(
  token: string,
): Promise<AdminCapacityMatrix> {
  return request<AdminCapacityMatrix>("/api/admin/capacity", {
    method: "GET",
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
  /** Code steps only, when the backend declares them: the files it reads and
   *  writes by default (a folder ends in "/") and one plain line on what it
   *  does in between. The rail's Reads / Process / Writes card prefers the
   *  step's own consumes/produces and falls back to these. */
  reads?: string[];
  process?: string;
  writes?: string[];
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
  /** RFN-002b — pricing rates in USD per 1 M tokens, from the catalog Pricing
   *  dataclass (scaled × 1e6).  Absent on older API responses → 0 (safe default).
   *  Use these for display only; actual billed cost lives in token_usage.estimated_cost_usd. */
  input_rate_per_1m?: number;
  output_rate_per_1m?: number;
  cache_read_rate_per_1m?: number;
  cache_write_5m_rate_per_1m?: number;
  /** How this model does reasoning, from the catalog capability (spec 020).
   *  `reasoning_levels` is what the composer's Effort dropdown renders — an
   *  empty list means the model offers no effort control at all. Replaces the
   *  old `thinking_supported` bool, which was derived from an id-substring
   *  tuple that had drifted from its backend counterpart. */
  reasoning_mode?: "effort" | "adaptive" | "budget" | "none";
  reasoning_levels?: string[];
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
  // ISS-782/ISS-796: shared-GET cached. This is the 23 KB payload with the most
  // independent callers (AnalyticsPage, AccountSettings, AgentModelPicker,
  // WorkflowDialog, and every `useAgentCapabilities` call site) — they all get
  // the same fetch now instead of one request each.
  return cachedGet<CapabilitiesPalette>("/api/capabilities", token);
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
  /** Declared capability signal (SC-001: name-free gating) — a launch surface
   *  offers the OpenDesign template/design-system picker for ANY workflow
   *  whose manifest declares `context_providers: [opendesign]`. */
  context_providers?: string[];
  /** Manifest `design_mode` ("web" | "deck") — which OpenDesign catalog the
   *  picker should list. */
  design_mode?: string | null;
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
  // ISS-854 (QA-PS-048): single-flight, like getWorkflow — StrictMode's doubled
  // Steps-tab effect asked for the same 30 KB catalog twice at once. In-flight
  // only, so a newly saved workflow still shows on the next read.
  return singleFlightGet<WorkflowSummary[]>("/api/workflows", token);
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
 * Single-flight guard for `getWorkflowDetail()` — ISS-819 (QA-PS-043) and its
 * siblings ISS-820/821/822.
 *
 * Every surface that shows a workflow's compiled plan seeds itself from a mount
 * effect that guards only its own state update with a `cancelled` flag, never
 * the fetch — IdeaInputPage, LaunchWizard, WorkflowDialog, ComposerPage and
 * page.tsx's built-in canvas alike. React StrictMode double-invokes those
 * effects in dev, so a cold `/create/user-stories` fired the same
 * `GET /api/workflows/user_stories` twice. Callers asking for the SAME workflow
 * while a request is still open now share that one request, exactly like
 * `inFlightWorkflows` and `inFlightAdminUsers` above.
 *
 * De-duplicates, does NOT cache: the entry is dropped the moment the request
 * settles, so the post-mutation read-backs in `handleToggleOverride` — which
 * await `setWorkflowOverrideEnabled` first — still go to the network and still
 * see the row they just wrote.
 */
const inFlightWorkflowDetail = new Map<string, Promise<WorkflowDetail>>();

/**
 * Fetch the full compiled definition for a known workflow id (API-01 / SURF-03).
 * Auth-gated (JWT). Named `getWorkflowDetail` because `getWorkflow` is already
 * taken by the run-history fetcher (`/api/runs/{id}`) and `getWorkflowDefinitions`
 * by the catalog listing. An unknown id raises 404 server-side (the caller treats
 * that as "nothing declared" — the SURF-03 strip simply does not render).
 */
export function getWorkflowDetail(
  token: string,
  workflowId: string,
  opts?: { original?: boolean }
): Promise<WorkflowDetail> {
  // `original` forces the SYSTEM version even when this caller has an enabled
  // override — the read-only "compare with original" view (spec 016). It must
  // never decide which plan RUNS; that is `override_enabled` on the row.
  const qs = opts?.original ? "?original=true" : "";
  const path = `/api/workflows/${encodeURIComponent(workflowId)}${qs}`;

  // Keyed by token AND the resolved path: two identities must never share a
  // plan, and `?original=true` must never be served the override payload.
  const key = `${token}\n${path}`;
  const pending = inFlightWorkflowDetail.get(key);
  if (pending) return pending;

  const started = request<WorkflowDetail>(path, {
    method: "GET",
    headers: authHeaders(token),
  }).finally(() => {
    inFlightWorkflowDetail.delete(key);
  });
  inFlightWorkflowDetail.set(key, started);
  return started;
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
const inFlightUserWorkflows = new Map<string, Promise<UserWorkflowSummary[]>>();

export function getUserWorkflows(
  token: string
): Promise<UserWorkflowSummary[]> {
  // Single-flight guard — ISS-788 (QA-PS-041). `SavedWorkflowsPage`'s mount
  // effect is the only caller, yet `/workflows` fetched this list twice on a
  // cold load and four times on a client-side nav: React StrictMode's dev
  // double-invoke re-runs that effect, and an SPA route change mounts the page
  // on top of the shell that is already up. Callers asking while a request is
  // open share it, exactly like `getWorkflows()` and `refreshOnce()` above.
  //
  // The entry is dropped the moment the request settles, so this de-duplicates
  // and does NOT cache: the list is mutated in place (rename/duplicate/delete)
  // and a later mount must still see the server's copy.
  //
  // Keyed by token: two identities must never share an owner-scoped list.
  const pending = inFlightUserWorkflows.get(token);
  if (pending) return pending;

  const started = request<UserWorkflowSummary[]>("/api/user-workflows", {
    method: "GET",
    headers: authHeaders(token),
  }).finally(() => {
    inFlightUserWorkflows.delete(token);
  });
  inFlightUserWorkflows.set(token, started);
  return started;
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

/**
 * Stage a raw document server-side for a not-yet-launched run (UPLD-05).
 * The returned stage_id rides the POST /api/runs body as `staged_upload_ids`;
 * the backend moves the bytes into the new run's `.uploads/` before the first
 * agent starts, so document agents see the real file, not just extracted text.
 */
export async function stageRunFile(
  token: string,
  file: File,
): Promise<{ stage_id: string; files: string[] }> {
  const form = new FormData();
  form.append("files", file);
  return request<{ stage_id: string; files: string[] }>("/api/runs/uploads/stage", {
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
  return cachedGet<HookRunsResponse>(`/api/runs/${encodeURIComponent(workflowId)}/hook-runs`, token);
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
    return await cachedGet<GateEventsResponse>(
      `/api/runs/${encodeURIComponent(workflowId)}/gate-events`,
      token,
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
    return await cachedGet<ValidationResultsResponse>(
      `/api/runs/${encodeURIComponent(workflowId)}/validation-results`,
      token,
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
    return await cachedGet<ExecRunsResponse>(
      `/api/runs/${encodeURIComponent(workflowId)}/exec-runs`,
      token,
    );
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      return { workflow_id: workflowId, exec_runs: [] };
    }
    throw err;
  }
}

// --- Share API (Option B — public deliverable sharing) ---

export interface ShareRunResult {
  share_token: string;
  /** Relative path: /s/{token} — prepend window.location.origin on the FE. */
  share_url: string;
  expires_at?: string | null;
}

/**
 * Mint (or refresh) a public share token for the run's deliverable.
 * Owner-gated (JWT). Returns the token + the /s/{token} path.
 * Only completed runs with a deliverable can be shared.
 */
export async function postShareRun(
  token: string,
  runId: string,
): Promise<ShareRunResult> {
  return request<ShareRunResult>(
    `/api/runs/${encodeURIComponent(runId)}/share`,
    { method: "POST", headers: authHeaders(token) },
  );
}

/**
 * Revoke the public share for a run (clear share_token). Idempotent.
 * Owner-gated (JWT).
 */
export async function deleteShareRun(
  token: string,
  runId: string,
): Promise<void> {
  await request<void>(
    `/api/runs/${encodeURIComponent(runId)}/share`,
    { method: "DELETE", headers: authHeaders(token) },
  );
}
