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
