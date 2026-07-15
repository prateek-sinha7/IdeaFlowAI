/**
 * Environment configuration for the frontend application.
 * Uses NEXT_PUBLIC_ prefixed variables for client-side access.
 *
 * NEXT_PUBLIC_* values are inlined into the JS bundle at BUILD time. The
 * production image is built with them EMPTY on purpose (see frontend/Dockerfile)
 * so a single, environment-agnostic image can be promoted dev -> stage -> prod.
 * When empty, we must resolve to SAME-ORIGIN URLs so the nginx that fronts the
 * app can proxy `/api` and `/ws/chat` to the backend. Emitting an absolute
 * `http://localhost:8000` here (the old fallback) breaks every deployed browser:
 * it points at the visitor's own machine and is rejected by the page's
 * `connect-src` Content Security Policy.
 *
 * Resolution order (both REST and WS):
 *   1. Explicit NEXT_PUBLIC_* value            -> use it verbatim.
 *   2. Browser on a non-local host             -> same-origin (relative REST,
 *                                                  ws(s)://<host>/ws/chat).
 *   3. Otherwise (local dev without .env.local,
 *      or server-side render)                  -> localhost:8000 defaults.
 *
 * The run transport is SSE + REST only (44-06 hard cutoff): there is no
 * transport feature flag. `WS_URL` survives solely for the legacy `/ws/chat`
 * client until its deletion completes; the `/ws/handoff` survivor derives its
 * own URL from `API_URL` in useHandoffSocket.
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

/** Resolve the WebSocket base URL, deriving scheme/host from the page origin. */
function resolveWsUrl(): string {
  const explicit = process.env.NEXT_PUBLIC_WS_URL;
  if (explicit) return explicit;
  if (typeof window !== "undefined" && !isLocalHost(window.location.hostname)) {
    const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${scheme}//${window.location.host}/ws/chat`;
  }
  return "ws://localhost:8000/ws/chat";
}

export const ENV = {
  /** Base URL for REST API calls. "" means same-origin (relative). */
  API_URL: resolveApiUrl(),
  /** Base URL for WebSocket connections (legacy `/ws/chat` client only). */
  WS_URL: resolveWsUrl(),
} as const;
