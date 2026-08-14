/**
 * Pure, unit-testable WS replay/dedup + per-run-reset helpers (Phase 12 / 12-07).
 *
 * The dashboard's `handleWebSocketMessage` is a `useCallback` closure inside the
 * DashboardPage component and is not independently importable, so the dedup
 * DECISION and the per-run RESET are extracted here as pure functions operating
 * on plain values (no React). This lets the durable-reconnect idempotency
 * contract (CR-05) and the per-run reset (WR-03) be tested directly.
 *
 * - `shouldApplyEvent` is the single dedup site hoisted to the TOP of the
 *   handler so EVERY event type (wave AND non-wave: agent_chunk, tool_call,
 *   task_progress) is deduped exactly once before routing — a replayed (or
 *   doubly-delivered) event applies at most once.
 * - `resetReplayState` clears the per-run dedup/cursor/wave state so a new run
 *   starts clean (run 2's seq advances from 0; the previous run's wave panel
 *   does not bleed in; the seen-set does not grow unboundedly across runs).
 */

import type { WaveGroup } from "@/types/index";

/**
 * Decide whether to apply an incoming WS event, deduping by `event_id`.
 *
 * Returns `false` (drop) when `eventId` is present AND already in `seen`.
 * Otherwise records `eventId` (when present) and returns `true` (apply). An
 * undefined/empty `eventId` always returns `true` — legacy/unstamped events
 * fall through undeduped, as today.
 *
 * Mutates `seen` (adds the id) as the canonical record of applied events; this
 * is intentional so the caller's seen-set is the single source of truth.
 */
export function shouldApplyEvent(
  seen: Set<string>,
  eventId: string | undefined,
): boolean {
  if (!eventId) return true; // legacy/unstamped — never deduped
  if (seen.has(eventId)) return false; // already applied — drop the duplicate
  seen.add(eventId);
  return true;
}

/** Imperative handle the dashboard wires into `resetReplayState`. */
export interface ReplayStateRefs {
  /** The per-run seen-event_id set (cleared in place). */
  seen: Set<string>;
  /** Setter for the max-seen seq ref/state — zeroed on reset. */
  setLastSeq: (n: number) => void;
  /** Setter for the wave-tree groups state — emptied on reset. */
  setWaveGroups: (groups: WaveGroup[]) => void;
}

/**
 * Reset the per-run FE replay state when a new run starts (WR-03).
 *
 * Clears the seen-set, zeroes the last-seq cursor, and empties the wave groups.
 * Pure/deterministic: it holds no module-level state of its own — it only acts
 * on the refs/setters handed in. After a reset an event_id that was seen before
 * the reset is treated as new again (run 2 is not poisoned by run 1's ids).
 */
export function resetReplayState(refs: ReplayStateRefs): void {
  refs.seen.clear();
  refs.setLastSeq(0);
  refs.setWaveGroups([]);
}

/**
 * Decide whether an incoming frame belongs to a run this tab is NOT tracking.
 *
 * The SSE provider attaches one stream per live run and fans EVERY frame out to
 * the single dashboard subscriber, so a concurrently running run's frames arrive
 * here too. This is the ONE shared predicate for that decision (previously
 * open-coded twice in `dashboard/page.tsx` for `pipeline_start` / `pipeline_complete`).
 *
 * Conservative by design — returns `false` (treat as OURS) unless BOTH ids are
 * known and they differ:
 *   - no `frameRunId` (an untagged/legacy frame) → not attributable, never dropped;
 *   - no `trackedRunId` (nothing claimed yet, e.g. the launch → first-frame window)
 *     → the frame is adopted, so launch→watch is unchanged.
 */
export function isForeignRunFrame(
  frameRunId: string | undefined | null,
  trackedRunId: string | undefined | null,
): boolean {
  if (!frameRunId || !trackedRunId) return false;
  return frameRunId !== trackedRunId;
}

/**
 * The run an incoming frame belongs to — the ONE routing decision `handleWebSocketMessage`
 * makes before it can hand the frame to that run's per-run store entry.
 *
 * Three sources, in priority order:
 *   1. `_sourceRunId` — injected per SSE stream by `RunConnectionProvider`;
 *   2. `data.pipeline_run_id` — carried only by the run-lifecycle frames;
 *   3. `sourceRunId` — the transport's stamp, passed as an ARGUMENT.
 *
 * (3) is load-bearing and was missing until ISS-082, where the dashboard open-coded (1)+(2)
 * in a local `const frameRunId` that SHADOWED its own `frameRunId` parameter. Neither key
 * survives to the per-agent frames on EITHER path — a REST-replayed frame never had them,
 * and the live subscription rebuilds the message as `{ type, data }` and passes the id
 * separately — so every `agent_*` frame resolved to `undefined` and the per-run store was
 * never given one. FIX-201 worked around that with a second, undeduped replay pass, which
 * is what doubled the reducer's accumulating fields.
 *
 * Extracted here, with `shouldApplyEvent` and `isForeignRunFrame`, for the reason stated at
 * the top of this file: the decision is testable, the closure it came from is not.
 */
export function resolveFrameRunId(
  msg: { data?: unknown; [key: string]: unknown },
  sourceRunId: string | undefined,
): string | undefined {
  const injected = (msg as Record<string, unknown>)._sourceRunId;
  if (typeof injected === "string" && injected) return injected;
  const fromData = (msg.data as Record<string, unknown> | undefined)?.pipeline_run_id;
  if (typeof fromData === "string" && fromData) return fromData;
  return sourceRunId;
}

/**
 * Frame types whose payload is keyed by `agent_id` and which MUTATE the viewed
 * run's per-agent live state (status / output / tokens / tool calls / task
 * progress) in `handlePipelineMessage`.
 *
 * These payloads carry NO `pipeline_run_id`, and agent ids are NOT unique across
 * runs (two prototype runs both stream `prototype-build` / `prototype-validate`),
 * so applying a foreign run's copy silently rewrites the viewed run's agents —
 * flipping already-`done` agents back to `running` after the run has completed.
 * They are therefore dropped when they arrive from a foreign run.
 *
 * Run-LIFECYCLE frames (`pipeline_start` / `pipeline_complete` / `pipeline_failed`
 * / `pipeline_cancelled` / `pipeline_reconnected`, planner + clarify) are
 * deliberately NOT in this set: they carry their own `pipeline_run_id` and drive
 * cross-run behaviour that must keep working (revision runs advancing the content
 * source, chaining, history reopen).
 */
export const AGENT_SCOPED_FRAME_TYPES: ReadonlySet<string> = new Set([
  "agent_start",
  "agent_thinking",
  "agent_chunk",
  "agent_complete",
  "agent_error",
  "agent_input",
  "agent_skills",
  "tool_call",
  "tool_result",
  "task_progress",
  "task_loop_progress",
  "validator_result",
  "gate_passed",
  "gate_blocked",
]);

/** Whether `type` mutates per-agent live state (see AGENT_SCOPED_FRAME_TYPES). */
export function isAgentScopedFrame(type: string): boolean {
  return AGENT_SCOPED_FRAME_TYPES.has(type);
}
