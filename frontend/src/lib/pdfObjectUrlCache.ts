import { getToken } from "@/lib/api";

/**
 * Object URLs of finished runs' PDFs, kept so re-entering the Preview tab does
 * not download the file again (RCA item 9). It lives at module scope on purpose:
 * it has to outlive the tab body that created it.
 *
 * That also means it outlives a sign-out, so it is scoped to the ACCOUNT:
 *  - A key carries the token's `sub` (the account id), never the bearer token.
 *    A token refresh mints a new token for the same account and must keep the
 *    entry, and a credential must not sit in a Map key. This is how ISS-188 and
 *    ISS-201 scope per-account caches too.
 *  - A token with no readable account id gets no key, so nothing is cached for it.
 *  - Entries of any other account are revoked the next time a preview reads the
 *    cache (every download is preceded by that read), and `clearPdfUrlCache()`
 *    revokes all of them when the user signs out.
 *
 * Insertion order is recency order: a hit is re-inserted, and the oldest entry
 * is evicted and revoked once there are more than `MAX_ENTRIES`.
 */
const MAX_ENTRIES = 4;

interface Entry {
  readonly account: string;
  readonly url: string;
}

const entries = new Map<string, Entry>();

/** Identifies one cached PDF. `account` is the signed-in account that fetched it. */
export interface PdfCacheKey {
  readonly account: string;
  readonly id: string;
}

/** The signed-in account id (the JWT `sub`), or null when signed out or the token carries none. */
function signedInAccount(): string | null {
  const payload = getToken()?.split(".")[1];
  if (!payload) return null;
  try {
    const claims = JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/"))) as { sub?: unknown };
    return typeof claims.sub === "string" && claims.sub !== "" ? claims.sub : null;
  } catch {
    return null;
  }
}

/** Revoke and forget every entry that does not belong to `account`. */
function dropEntriesNotOf(account: string | null): void {
  for (const [id, entry] of entries) {
    if (entry.account === account) continue;
    entries.delete(id);
    URL.revokeObjectURL(entry.url);
  }
}

/**
 * The key for one PDF as seen by the signed-in account, or null when there is
 * no account id to scope it to. A null key means "do not cache".
 */
export function pdfCacheKey(runId: string, path: string, selectedRef: string | undefined): PdfCacheKey | null {
  const account = signedInAccount();
  if (account === null) return null;
  // JSON, not a delimiter join: a file name or a version tag may contain any separator character.
  return { account, id: JSON.stringify([account, runId, path, selectedRef ?? ""]) };
}

/** The cached URL for `key`, if any. Safe to call while rendering: it changes nothing. */
export function peekCachedPdfUrl(key: PdfCacheKey): string | undefined {
  return entries.get(key.id)?.url;
}

/** The cached URL for `key`, marked most recently used. Call it from effects, not while rendering. */
export function readCachedPdfUrl(key: PdfCacheKey): string | undefined {
  dropEntriesNotOf(signedInAccount());
  const entry = entries.get(key.id);
  if (entry === undefined) return undefined;
  entries.delete(key.id);
  entries.set(key.id, entry);
  return entry.url;
}

/**
 * Keep `url` for `key`. Returns false, and keeps nothing, when the key's account
 * is no longer the signed-in one (it signed out while the PDF was downloading).
 * The caller then still owns `url` and must revoke it.
 */
export function storeCachedPdfUrl(key: PdfCacheKey, url: string): boolean {
  const account = signedInAccount();
  if (account !== key.account) return false;
  const previous = entries.get(key.id);
  if (previous !== undefined && previous.url !== url) URL.revokeObjectURL(previous.url);
  entries.delete(key.id);
  entries.set(key.id, { account, url });
  for (const [id, entry] of entries) {
    if (entries.size <= MAX_ENTRIES) break;
    entries.delete(id);
    URL.revokeObjectURL(entry.url);
  }
  return true;
}

/** Revoke and forget every cached URL. Called on sign-out, when no account owns them any more. */
export function clearPdfUrlCache(): void {
  for (const entry of entries.values()) URL.revokeObjectURL(entry.url);
  entries.clear();
}
