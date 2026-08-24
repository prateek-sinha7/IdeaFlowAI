/**
 * Post-login redirect helpers.
 *
 * After a successful login every user — including admins — lands on the main
 * application (`/dashboard`) unless they were bounced to `/login` from a
 * specific protected page, in which case they return to that page.
 *
 * The destination travels as a `?redirect=` query param on the `/login` URL.
 * Only internal, same-origin application paths are ever honored — this is
 * the open-redirect guard: a crafted `?redirect=https://evil.com` or
 * `?redirect=//evil.com` value must never be used for navigation.
 */

export const DEFAULT_POST_LOGIN_ROUTE = "/dashboard";

/**
 * True when `path` is safe to redirect to: a same-origin, internal,
 * `/`-rooted path. Rejects absolute URLs, protocol-relative URLs
 * (`//host/...`), backslash tricks some browsers normalize into
 * protocol-relative URLs (`/\host/...`), and paths beginning with control
 * characters.
 */
export function isSafeRedirectPath(path: string | null | undefined): path is string {
  if (!path) return false;
  if (!path.startsWith("/")) return false;
  if (path.startsWith("//") || path.startsWith("/\\")) return false;
  if (/^[\s\u0000-\u001f]/.test(path)) return false;
  return true;
}

/** Resolve a candidate redirect value to a safe target, or the app default. */
export function resolveRedirectTarget(path: string | null | undefined): string {
  return isSafeRedirectPath(path) ? path : DEFAULT_POST_LOGIN_ROUTE;
}

/**
 * Build a `/login?redirect=...` URL carrying the current location (path +
 * query + hash, where supported) as the destination to return to after a
 * successful login. Client-only — reads `window.location`; falls back to a
 * bare `/login` when called outside the browser (SSR) or when the current
 * location is somehow not a safe internal path.
 */
export function buildLoginRedirect(): string {
  if (typeof window === "undefined") return "/login";
  const { pathname, search, hash } = window.location;
  const current = `${pathname}${search}${hash}`;
  if (!isSafeRedirectPath(current)) return "/login";
  return `/login?redirect=${encodeURIComponent(current)}`;
}
