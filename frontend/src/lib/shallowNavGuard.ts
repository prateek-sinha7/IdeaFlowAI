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
