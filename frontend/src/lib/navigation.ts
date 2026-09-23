/**
 * The one "Back" guard (ISS-741 / ISS-786).
 *
 * An in-app control labelled "Back" must POP the entry the user came from, not
 * PUSH a fresh copy of the destination: a push leaves the screen being left on
 * the stack, so the next Back — the browser's own, or a correctly implemented
 * in-app one on the destination — walks straight back into it. That is
 * QA-SG-003: run detail pushed `/runs`, Run History's own (correct) Back popped
 * to the just-repushed `/runs/{id}`, and the two screens oscillated forever.
 *
 * `fallback()` runs only when there is no prior entry to pop — a direct or
 * shared URL that landed the user straight on this screen.
 *
 * `DashboardLayout.handleBackNav` established this shape; it lives here so the
 * routes that mount outside `DashboardLayout` (and so cannot call its private
 * handler) share the guard instead of each keeping its own copy.
 */
export function goBackOr(router: { back: () => void }, fallback: () => void): void {
  if (typeof window !== "undefined" && window.history.length > 1) {
    router.back();
    return;
  }
  fallback();
}
