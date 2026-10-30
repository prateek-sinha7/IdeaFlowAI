/**
 * Settled-run hydration (finished-run perf, plan D3).
 *
 * A finished run's per-token stream deltas (`agent_chunk` / `agent_thinking`)
 * are ~98% of its `/events` log. The backend already folds them, per closed
 * pass, into `workflow_runs.agent_outputs` (run_commands.py
 * `_apply_terminal_output_columns`): one row per `agent_complete` /
 * `agent_error`, keyed by `(agent_id, task_id or "")`, holding that pass's chunk
 * concatenation (`output`) and thinking (`thinking_text`). A pass interrupted by
 * another `agent_start` for the same key is dropped, never written.
 *
 * These helpers let a reopened finished run replay the log WITHOUT the deltas
 * and fill the Steps text from those rows instead, reproducing exactly what the
 * live reducer (`hooks/useWorkflow.ts`) would have accumulated:
 *  - a plain step resets `output` / `thinkingText` on every `agent_start`, so it
 *    shows its LAST pass, i.e. the LAST row for `(agent_id, "")`;
 *  - a wave worker never resets across re-runs (`upsertWaveWorker` carries
 *    `prior.output`), so it shows ALL its passes, i.e. every row for
 *    `(agent_id, task_id)` concatenated in order.
 *
 * SC-001: everything is keyed on event data (agent ids, task ids, event types),
 * never on a workflow or agent name.
 */
import type { DurableFrame } from "@/lib/api";
import type { AgentRunState, PipelineRunState, WaveWorkerEntry } from "@/types/index";

/** One element of the persisted `workflow_runs.agent_outputs` JSON array
 *  (only the fields hydration reads). `task_id` is present on wave workers. */
export interface PersistedAgentOutputRow {
  agent_id: string;
  task_id?: string | null;
  output?: string;
  thinking_text?: string;
}

const LIFECYCLE_TYPES = new Set(["agent_start", "agent_complete", "agent_error"]);
const CLOSING_TYPES = new Set(["agent_complete", "agent_error"]);

/** The collector's row key: `(agent_id, task_id or "")`. */
function keyOf(agentId: string, taskId: unknown): string {
  return `${agentId}\u0000${typeof taskId === "string" ? taskId : ""}`;
}

/**
 * Boundary validation of the run record's `agent_outputs` (a JSON string on the
 * wire, or an already-parsed array). Returns `null` when the value is absent,
 * not valid JSON, or not an array; drops elements without a non-empty string
 * `agent_id`; keeps only string `output` / `thinking_text` / `task_id`.
 */
export function parsePersistedAgentOutputs(raw: unknown): PersistedAgentOutputRow[] | null {
  let value = raw;
  if (typeof value === "string") {
    try {
      value = JSON.parse(value);
    } catch {
      return null;
    }
  }
  if (!Array.isArray(value)) return null;
  const rows: PersistedAgentOutputRow[] = [];
  for (const item of value) {
    if (typeof item !== "object" || item === null) continue;
    const record = item as Record<string, unknown>;
    if (typeof record.agent_id !== "string" || !record.agent_id) continue;
    rows.push({
      agent_id: record.agent_id,
      task_id: typeof record.task_id === "string" ? record.task_id : null,
      ...(typeof record.output === "string" ? { output: record.output } : {}),
      ...(typeof record.thinking_text === "string" ? { thinking_text: record.thinking_text } : {}),
    });
  }
  return rows;
}

/**
 * True when `rows` reproduce, for every key, what replaying the full log would
 * accumulate, so the delta-free frames + `applyAgentOutputs` are equivalent.
 *
 * Holds when, for every `(agent_id, task_id or "")` key:
 *  - the number of `agent_start` frames equals the number of rows (every pass
 *    was closed and written; a start->start re-run drops a pass the reducer
 *    still shows for a worker), and
 *  - the key's last lifecycle frame is `agent_complete` or `agent_error` (the
 *    final pass is closed, so its row exists), and
 *  - no row exists for a key that never started (its chunks were accumulated
 *    without a reset, which a per-pass row cannot reproduce).
 * A log with no `agent_start` and no rows has nothing to hydrate (true).
 * Rows `null` (missing / unparseable column) with any start is false.
 */
export function canHydrateFromAgentOutputs(
  frames: readonly DurableFrame[],
  rows: readonly PersistedAgentOutputRow[] | null,
): boolean {
  const lifecycle = new Map<string, { starts: number; last: string }>();
  let anyStart = false;
  for (const frame of frames) {
    if (!LIFECYCLE_TYPES.has(frame.type)) continue;
    const agentId = frame.data.agent_id;
    if (typeof agentId !== "string" || !agentId) continue;
    const key = keyOf(agentId, frame.data.task_id);
    const entry = lifecycle.get(key) ?? { starts: 0, last: frame.type };
    entry.last = frame.type;
    if (frame.type === "agent_start") {
      entry.starts += 1;
      anyStart = true;
    }
    lifecycle.set(key, entry);
  }
  if (rows === null) return !anyStart;
  const rowCounts = new Map<string, number>();
  for (const row of rows) {
    const key = keyOf(row.agent_id, row.task_id);
    rowCounts.set(key, (rowCounts.get(key) ?? 0) + 1);
  }
  for (const [key, entry] of lifecycle) {
    if (entry.starts === 0) continue;
    if (rowCounts.get(key) !== entry.starts) return false;
    if (!CLOSING_TYPES.has(entry.last)) return false;
  }
  for (const key of rowCounts.keys()) {
    if (!lifecycle.get(key)?.starts) return false;
  }
  return true;
}

/** Fill one wave step's known workers from their rows (concatenated in order). */
function hydrateWorkers(
  workers: readonly WaveWorkerEntry[],
  rowsByTask: ReadonlyMap<string, PersistedAgentOutputRow[]>,
): WaveWorkerEntry[] | null {
  let changed = false;
  const next = workers.map((worker) => {
    const taskRows = rowsByTask.get(worker.taskId);
    if (!taskRows) return worker;
    const output = taskRows.map((row) => row.output ?? "").join("");
    const thinking = taskRows.map((row) => row.thinking_text ?? "").join("");
    const outputDiffers = output !== (worker.output ?? "");
    const thinkingDiffers = thinking !== (worker.thinking ?? "");
    if (!outputDiffers && !thinkingDiffers) return worker;
    changed = true;
    return {
      ...worker,
      ...(outputDiffers ? { output } : {}),
      ...(thinkingDiffers ? { thinking } : {}),
    };
  });
  return changed ? next : null;
}

/** Fill one step: its plain text from its last row, its workers from theirs. */
function hydrateAgent(
  agent: AgentRunState,
  lastPlainRow: PersistedAgentOutputRow | undefined,
  rowsByTask: ReadonlyMap<string, PersistedAgentOutputRow[]> | undefined,
): AgentRunState {
  let next = agent;
  if (lastPlainRow) {
    const output = lastPlainRow.output ?? "";
    const thinkingText = lastPlainRow.thinking_text ?? "";
    const outputDiffers = output !== next.output;
    const thinkingDiffers = thinkingText !== (next.thinkingText ?? "");
    if (outputDiffers || thinkingDiffers) {
      next = {
        ...next,
        ...(outputDiffers ? { output } : {}),
        ...(thinkingDiffers ? { thinkingText } : {}),
      };
    }
  }
  if (rowsByTask && next.waveWorkers) {
    const workers = hydrateWorkers(next.waveWorkers, rowsByTask);
    if (workers) next = { ...next, waveWorkers: workers };
  }
  return next;
}

/**
 * Write persisted per-pass text into a state replayed from delta-free frames.
 * Plain step -> the LAST row for `(agent_id, "")` into `output` / `thinkingText`;
 * wave worker -> ALL rows for `(agent_id, task_id)` concatenated into the
 * worker's `output` / `thinking`. Agents not in the roster and workers not on
 * their step are ignored (the live reducer drops their deltas too). Returns
 * `state` itself when nothing changes. Call only when
 * `canHydrateFromAgentOutputs` holds.
 */
export function applyAgentOutputs(
  state: PipelineRunState,
  rows: readonly PersistedAgentOutputRow[],
): PipelineRunState {
  const lastPlainRows = new Map<string, PersistedAgentOutputRow>();
  const workerRows = new Map<string, Map<string, PersistedAgentOutputRow[]>>();
  for (const row of rows) {
    if (!row.task_id) {
      lastPlainRows.set(row.agent_id, row);
      continue;
    }
    const byTask = workerRows.get(row.agent_id) ?? new Map<string, PersistedAgentOutputRow[]>();
    byTask.set(row.task_id, [...(byTask.get(row.task_id) ?? []), row]);
    workerRows.set(row.agent_id, byTask);
  }
  let changed = false;
  const agents = state.agents.map((agent) => {
    const next = hydrateAgent(agent, lastPlainRows.get(agent.id), workerRows.get(agent.id));
    if (next !== agent) changed = true;
    return next;
  });
  return changed ? { ...state, agents } : state;
}
