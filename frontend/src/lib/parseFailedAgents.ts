// IN-01 (16 review) — shared failed-agent-id parser.
//
// The backend persists a degraded/failed run's failed-agent ids into `wr.error`
// as "...agent(s) failed: <id1>, <id2>" (websocket.py). This parses those ids
// back out so a reopened run's terminal-empty degraded/failed affordance can
// list the real failed agents instead of an empty list. Returns `undefined`
// when the marker is absent (e.g. a plain failure message), so the affordance
// simply omits the agent list.
//
// SHARED (INV-3 / no-dual-impl): the SINGLE source of truth consumed by BOTH
//   • app/dashboard/page.tsx   — the live-reopen → PreviewPanel path, and
//   • components/history/WorkflowHistory.tsx — the history-reopen detail view.
// The marker contract must not be duplicated; both reopen surfaces parse the
// persisted `error` identically and so cannot diverge. Server-keyed — no client
// guess about which agents failed.
const FAILED_AGENTS_MARKER = /agent\(s\) failed:\s*(.+)$/i;

export function parseFailedAgentIds(error: string | undefined): string[] | undefined {
  if (!error) return undefined;
  const match = error.match(FAILED_AGENTS_MARKER);
  if (!match) return undefined;
  const ids = match[1]
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  return ids.length > 0 ? ids : undefined;
}
