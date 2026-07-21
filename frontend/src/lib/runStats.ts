/**
 * Shared run-stat formatters — the SINGLE source for the duration + token
 * formatters the run-detail surfaces render (D-15 / no dual implementation).
 *
 * Extracted so `RunDetailPage` imports them rather than re-implementing the
 * `fmt`/`formatDuration` closures inline. The in-panel `WorkflowHistory` detail
 * still carries its own local copies today; those are retired together with the
 * whole in-panel duplicate in 36-05 (which then repoints onto this module).
 */

/** Human-readable duration: "45s" / "2m 5s". Falsy/zero → "" (no chip). */
export function formatDuration(seconds?: number | null): string {
  if (!seconds) return "";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

/** Compact token count: 2_000_000 → "2.0M", 1_200 → "1.2K", 800 → "800". */
export function formatTokenCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}
