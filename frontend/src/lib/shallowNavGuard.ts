/**
 * Shallow-navigation guard for the DashboardLayout ↔ page.tsx seam.
 *
 * When `handlePreviewPanelTabSelect` calls `window.history.pushState` for a
 * shallow tab-URL update, it increments this counter.  page.tsx's viewPath
 * effect calls `consumeShallowNav()` before minting a `requestOpenTab` for the
 * same run — if the counter is positive the URL change was a self-initiated tab
 * click (the tab switch already happened via `handleTabChange`), so the effect
 * skips the deep-link request.  Back/forward navigation does NOT call
 * `markShallowNav()`, so `consumeShallowNav()` returns false and the effect
 * fires normally.
 *
 * Module-level state is safe here because both callers are in the same client
 * bundle (same process, same tick loop).
 */

let _pendingShallowNavs = 0;

/** Mark that an imminent `window.history.pushState` is a self-initiated shallow
 *  tab navigation.  Must be called synchronously before the `pushState` call. */
export function markShallowNav(): void {
  _pendingShallowNavs += 1;
}

/** Consume one pending shallow-nav token.  Returns `true` if the URL change was
 *  a self-initiated tab click (the caller should skip deep-linking); `false` if
 *  it was an external or back/forward navigation (the caller should deep-link). */
export function consumeShallowNav(): boolean {
  if (_pendingShallowNavs > 0) {
    _pendingShallowNavs -= 1;
    return true;
  }
  return false;
}

// ── Path-keyed guard (AI workflow builder, design §3.10.6 / D-08) ───────────
//
// A plain `replaceState` to `/workflows/{id}/edit` would make page.tsx's edit
// cold-mount effect fetch the row and remount the composer.  The host marks the
// exact target path right before `replaceState`; the effect consumes it and
// returns early, so `savedComposition` stays null and the composer keeps its
// state.  Unlike the counter above this is keyed by path, so a mark for one URL
// can never swallow a navigation to another.

const _pendingShallowNavPaths = new Map<string, number>();

/** Reduce a URL or pathname to its pathname: drop query and hash, collapse a
 *  trailing slash (the root stays "/"), the same segment view `usePathname()`
 *  and `parseViewPath` work with. */
function normalizeShallowPath(path: string): string {
  const pathOnly = path.split(/[?#]/, 1)[0];
  const trimmed = pathOnly.replace(/\/+$/, "");
  return trimmed === "" ? "/" : trimmed;
}

/** Mark that an imminent `window.history.replaceState` to `path` is a
 *  self-initiated shallow navigation.  Call synchronously before `replaceState`. */
export function markShallowNavTo(path: string): void {
  const key = normalizeShallowPath(path);
  _pendingShallowNavPaths.set(key, (_pendingShallowNavPaths.get(key) ?? 0) + 1);
}

/** Consume one pending mark for `path`.  Returns `true` once per mark (the
 *  caller should skip its cold-mount work); `false` for any other path or when
 *  the mark was already consumed. */
export function consumeShallowNavTo(path: string): boolean {
  const key = normalizeShallowPath(path);
  const pending = _pendingShallowNavPaths.get(key) ?? 0;
  if (pending <= 0) return false;
  if (pending === 1) _pendingShallowNavPaths.delete(key);
  else _pendingShallowNavPaths.set(key, pending - 1);
  return true;
}
