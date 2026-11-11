/**
 * Wording of the Builder panel's progress lines (Req 16.2 to 16.6, design 3.10.5).
 *
 * Pure functions: each returns the English text a line shows, so the wording
 * has one definition that the components and tests share.
 */

import type { LimitWarningView } from "./builderReducer";
import { formatElapsed } from "./builderSelectors";
import type {
  CheckResult,
  CheckSource,
  CheckVerdict,
  ToolStatus,
} from "@/types/workflowBuilder";

const SOURCE_LABELS: Readonly<Record<CheckSource, string>> = {
  skill_validator: "Skill validator",
  platform_dry_run: "Platform check",
  server_gate: "Server gate",
};

const VERDICT_LABELS: Readonly<Record<CheckVerdict, string>> = {
  valid: "VALID",
  invalid: "INVALID",
  unknown: "UNKNOWN",
};

const STATUS_LABELS: Readonly<Record<ToolStatus, string>> = {
  running: "Running",
  ok: "Done",
  error: "Failed",
  refused: "Refused",
  timed_out: "Timed out",
  stopped: "Stopped",
};

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

/** The status word shown on an activity line. */
export function activityStatusText(status: ToolStatus): string {
  return STATUS_LABELS[status];
}

/** "740 ms" below one second, otherwise the elapsed format. `null` when unknown. */
export function formatDuration(durationMs: number | null): string | null {
  if (durationMs === null || !Number.isFinite(durationMs) || durationMs < 0) {
    return null;
  }
  if (durationMs < 1000) {
    return `${Math.round(durationMs)} ms`;
  }
  return formatElapsed(durationMs);
}

/**
 * One check line, for example "Skill validator: VALID, 1 warning" or
 * "Platform check: 2 problems, fixing (attempt 1 of 2)".
 */
export function checkLineText(check: CheckResult): string {
  const parts: string[] = [
    check.errors > 0 ? plural(check.errors, "problem") : VERDICT_LABELS[check.verdict],
  ];
  if (check.warnings > 0) {
    parts.push(plural(check.warnings, "warning"));
  }
  if (check.errors > 0 && check.attempt !== null && check.attempts_left !== null) {
    parts.push(
      check.attempts_left > 0
        ? `fixing (attempt ${check.attempt} of ${check.attempt + check.attempts_left})`
        : "no attempts left",
    );
  }
  return `${SOURCE_LABELS[check.source]}: ${parts.join(", ")}`;
}

/**
 * The quiet notice for a limit warning, naming the limit and how much is left,
 * for example "About 3 minutes left in this turn".
 */
export function limitNoticeText(warning: LimitWarningView): string {
  const left = Math.max(0, warning.limit - warning.used);
  switch (warning.kind) {
    case "time":
      if (left < 60) {
        return `About ${plural(left, "second")} left in this turn`;
      }
      return `About ${plural(Math.round(left / 60), "minute")} left in this turn`;
    case "tool_calls":
      return `About ${plural(left, "tool call")} left in this turn`;
    case "tokens":
      return `About ${plural(left, "token")} left in this turn`;
  }
}
