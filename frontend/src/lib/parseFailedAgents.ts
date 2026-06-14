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

// ISS-024 (16 review IN-02) — shared agent-id→name resolution.
//
// The failed-agent lists carried into the terminal-failure DegradedRunAffordance
// are raw agent IDs (e.g. "prototype-build", "app-sdlc-governance"), but the
// affordance must show human NAMES (e.g. "Build Agent", "SDLC Governance"). The
// id→name source differs per surface — the LIVE path has pipelineState.agents
// ({id,name}); the HISTORY-reopen path has the persisted agentOutputs
// ({agent_id,name}) — so each call site builds the {id→name} map from its own
// source and both feed it through this ONE resolver (INV-3 / no-dual-impl).
//
// Fallback (REQUIRED): an id absent from the map resolves to the raw id, so
// older runs / unknown agents never render blank — they degrade to the id,
// exactly the prior behaviour.

/** Build an id→name lookup from any list of agents carrying an id + name. */
export function buildAgentNameById(
  agents: ReadonlyArray<{ id: string; name?: string | null }> | undefined,
): Record<string, string> {
  const map: Record<string, string> = {};
  if (!agents) return map;
  for (const a of agents) {
    if (a && a.id && a.name) map[a.id] = a.name;
  }
  return map;
}

/** Resolve agent ids to human names, falling back to the raw id when unknown. */
export function resolveAgentNames(
  ids: ReadonlyArray<string> | undefined,
  nameById: Record<string, string> | undefined,
): string[] {
  if (!ids) return [];
  return ids.map((id) => (nameById && nameById[id]) || id);
}
