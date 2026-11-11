/**
 * Pure selectors of the Builder panel (design 3.10.6; Req 4.5, 4.6, 8.3, 9.3, 17.7).
 *
 * No I/O, no clock, no React. The panel components read these instead of
 * re-deriving the rules, so the Send rule, the Undo target and the summary
 * line have one definition each.
 *
 * Pending G-23: the length is counted in code points (`Array.from`), the same
 * count the server uses (`len(str)`), and whitespace-only is empty.
 */
import type {
  ActivitySummary,
  CheckResult,
  DraftRevisionOut,
  StoredStep,
  ToolActivity,
  TranscriptMessage,
} from "@/types/workflowBuilder";

import type { BuilderState, TurnStep, TurnView } from "./builderReducer";

/** `BUILDER_MAX_MESSAGE_CHARS` placeholder (Q-24), in code points. */
export const MAX_MESSAGE_CODE_POINTS = 12_000;

/** The character counter appears past this many code points (design 3.10.6). */
export const MESSAGE_COUNTER_THRESHOLD = 11_000;

/**
 * Characters Python's `str.strip()` removes: those with `str.isspace()` true.
 * The server rejects content when `value.strip()` is empty, so the client must
 * use this set, not `String.prototype.trim` (which also strips U+FEFF but not
 * U+001C to U+001F or U+0085).
 */
const PYTHON_BLANK = /^[\t-\r\u001C-\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]*$/;

/** Number of Unicode code points in `text` (not UTF-16 units). */
export function codePointLength(text: string): number {
  return Array.from(text).length;
}

/** True when the server would treat `text` as empty. */
export function isBlank(text: string): boolean {
  return PYTHON_BLANK.test(text);
}

/**
 * Whether Send is enabled: no turn is sending or running (including a turn
 * started in another tab), the text is not blank, and it has at most
 * `maxCodePoints` code points.
 */
export function canSend(
  text: string,
  turn: TurnView,
  maxCodePoints: number = MAX_MESSAGE_CODE_POINTS,
): boolean {
  if (turn.kind === "sending" || turn.kind === "running") {
    return false;
  }
  return !isBlank(text) && codePointLength(text) <= maxCodePoints;
}

/**
 * The one message that offers "Undo": the latest assistant message whose
 * accepted revision is the session's latest revision, and only when that
 * latest revision is of kind `accepted` (an undo, seed or unproposed revision
 * on top means there is nothing to undo). Returns `null` for none.
 */
export function undoTargetMessageId(
  transcript: readonly Pick<TranscriptMessage, "id" | "seq" | "role" | "revision">[],
  revisions: readonly Pick<DraftRevisionOut, "revision" | "kind">[],
): string | null {
  let latest: Pick<DraftRevisionOut, "revision" | "kind"> | null = null;
  for (const entry of revisions) {
    if (latest === null || entry.revision > latest.revision) {
      latest = entry;
    }
  }
  if (latest === null || latest.kind !== "accepted") {
    return null;
  }
  let target: Pick<TranscriptMessage, "id" | "seq"> | null = null;
  for (const message of transcript) {
    if (
      message.role === "assistant" &&
      message.revision === latest.revision &&
      (target === null || message.seq > target.seq)
    ) {
      target = message;
    }
  }
  return target === null ? null : target.id;
}

/** "1 min 12 s", "40 s", "2 min". Negative or non-finite input reads as "0 s". */
export function formatElapsed(durationMs: number): string {
  const total = Number.isFinite(durationMs) && durationMs > 0 ? Math.floor(durationMs / 1000) : 0;
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  if (minutes === 0) {
    return `${seconds} s`;
  }
  return seconds === 0 ? `${minutes} min` : `${minutes} min ${seconds} s`;
}

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

/** The one-line summary from stored counts, for example "14 actions, 2 checks, 1 min 40 s". */
export function formatActivitySummary(
  summary: Pick<ActivitySummary, "actions" | "checks" | "duration_ms">,
): string {
  return [
    plural(summary.actions, "action"),
    plural(summary.checks, "check"),
    formatElapsed(summary.duration_ms),
  ].join(", ");
}

/** The one-line summary of a live turn's activity list, check results and duration. */
export function activitySummary(
  activity: readonly ToolActivity[],
  checks: readonly CheckResult[],
  durationMs: number,
): string {
  return formatActivitySummary({
    actions: activity.length,
    checks: checks.length,
    duration_ms: durationMs,
  });
}

/**
 * Stored steps in the shape the live view renders, so a finished reply and a running
 * one share one renderer. Ids are the step index, which is stable for a stored list.
 * Returns `null` when there is nothing to show, so the caller keeps the older layout.
 */
export function storedStepsToTurnSteps(
  steps: readonly StoredStep[] | null,
): readonly TurnStep[] | null {
  // A payload from before `steps` existed (or a mock) can lack the key: read it as none.
  if (!steps || steps.length === 0) {
    return null;
  }
  return steps.map((step, index): TurnStep => {
    switch (step.kind) {
      case "thinking":
        return { kind: "thinking", id: `stored-${index}`, text: step.text };
      case "tools":
        return { kind: "tools", id: `stored-${index}`, callIds: step.call_ids };
      case "check":
        return { kind: "check", id: `stored-${index}`, check: step.check };
    }
  });
}

/**
 * The ordered steps to show for a finished assistant message, or `null` to keep the
 * older layout (one summary line, a separate Thinking block). Steps apply only when the
 * turn made tool calls: a thinking-only turn has no summary to open, so it keeps the
 * Thinking block.
 */
export function orderedStepsOf(
  message: Pick<TranscriptMessage, "role" | "steps" | "activity_summary">,
): readonly TurnStep[] | null {
  if (message.role !== "assistant") {
    return null;
  }
  const summary = message.activity_summary;
  if (summary === null || summary.actions === 0) {
    return null;
  }
  return storedStepsToTurnSteps(message.steps);
}

/**
 * True from `turn_started` (or a snapshot that reports a running turn) until
 * `turn_completed`, in this tab or another. The Composer reads this to make the
 * canvas read-only and to disable Save and Run (Req 9.3, 9.4).
 */
export function isTurnRunning(state: Pick<BuilderState, "turn">): boolean {
  return state.turn.kind === "running";
}
