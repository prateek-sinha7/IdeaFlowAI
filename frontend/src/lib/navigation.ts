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

/**
 * The list screen a run was opened from — the Runs list or the dashboard.
 *
 * A run's own Back must return THERE, not one browser entry back: switching run
 * tabs pushes an entry per tab, and a run launched from a wizard has the wizard
 * behind it, so `router.back()` walked through tabs or into the wizard.
 * The list screen records itself (with `history.length` at that moment) and the
 * run's Back pops exactly the entries pushed since — a pop, not a push, so the
 * list's own Back does not loop into the run (ISS-741).
 */
export type BackOrigin = { label: "runs" | "dashboard"; path: string; len: number };

const ORIGIN_KEY = "velocity.backOrigin";
const DEFAULT_ORIGIN: BackOrigin = { label: "dashboard", path: "/dashboard", len: 0 };

export function rememberBackOrigin(label: BackOrigin["label"], path: string): void {
  try {
    sessionStorage.setItem(ORIGIN_KEY, JSON.stringify({ label, path, len: window.history.length }));
  } catch {
    /* storage blocked — Back falls back to the dashboard */
  }
}

export function readBackOrigin(): BackOrigin {
  try {
    const o = JSON.parse(sessionStorage.getItem(ORIGIN_KEY) ?? "null");
    if (o && (o.label === "runs" || o.label === "dashboard") && typeof o.path === "string") return o;
  } catch {
    /* unreadable — default */
  }
  return DEFAULT_ORIGIN;
}

export function backToOrigin(router: { push: (href: string) => void }): void {
  const origin = readBackOrigin();
  const steps = window.history.length - origin.len;
  if (origin.len > 0 && steps > 0) {
    window.history.go(-steps);
    return;
  }
  // Opened from a shared link, or history was cut — go to the list directly.
  router.push(origin.path);
}
