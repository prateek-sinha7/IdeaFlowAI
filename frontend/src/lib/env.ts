/**
 * Environment configuration for the frontend application.
 * Uses NEXT_PUBLIC_ prefixed variables for client-side access.
 *
 * NEXT_PUBLIC_* values are inlined into the JS bundle at BUILD time. The
 * production image is built with them EMPTY on purpose (see frontend/Dockerfile)
 * so a single, environment-agnostic image can be promoted dev -> stage -> prod.
 * When empty, we must resolve to SAME-ORIGIN URLs so the nginx that fronts the
 * app can proxy `/api` to the backend. Emitting an absolute
 * `http://localhost:8000` here (the old fallback) breaks every deployed browser:
 * it points at the visitor's own machine and is rejected by the page's
 * `connect-src` Content Security Policy.
 *
 * Resolution order (REST):
 *   1. Explicit NEXT_PUBLIC_API_URL value       -> use it verbatim.
 *   2. Browser on a non-local host              -> same-origin (relative REST).
 *   3. Otherwise (local dev without .env.local,
 *      or server-side render)                   -> localhost:8000 default.
 *
 * The run transport is SSE + REST only (44-06 hard cutoff): there is no
 * WebSocket run URL and no transport feature flag. The surviving `/ws/handoff`
 * socket derives its own URL from `API_URL` in useHandoffSocket.
 */

function isLocalHost(hostname: string): boolean {
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "[::1]";
}

/** Resolve the REST API base URL. Empty string => same-origin relative calls. */
function resolveApiUrl(): string {
  const explicit = process.env.NEXT_PUBLIC_API_URL;
  if (explicit) return explicit;
  if (typeof window !== "undefined" && !isLocalHost(window.location.hostname)) {
    // Same-origin: `${API_URL}/api/...` becomes `/api/...`, which nginx proxies.
    return "";
  }
  return "http://localhost:8000";
}

export const ENV = {
  /** Base URL for REST API calls. "" means same-origin (relative). */
  API_URL: resolveApiUrl(),
} as const;
