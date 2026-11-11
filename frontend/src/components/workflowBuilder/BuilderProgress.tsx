"use client";

/**
 * BuilderProgress: the activity of one turn in the Builder panel (Req 16.1 to 16.5, 5.3).
 *
 * Two modes:
 * - `live`: the stage label with the elapsed time ticking every second, the
 *   limit notices, the check lines and an expandable activity list. Used while a
 *   turn runs, in this tab or another.
 * - `ended`: the stored one-line summary ("14 actions, 2 checks, 1 min 40 s"),
 *   which expands to the activity list and check lines.
 *
 * Each activity line expands to the tool's summary. A script call also shows
 * its command, and nothing else from the call's arguments (Req 16.3, 16.4).
 * Text here is rendered as React text, never as HTML.
 */

import { useEffect, useState } from "react";

import type { LimitWarningView } from "./builderReducer";
import { formatActivitySummary, formatElapsed } from "./builderSelectors";
import {
  activityStatusText,
  checkLineText,
  formatDuration,
  limitNoticeText,
} from "./progressText";
import type {
  ActivitySummary,
  CheckResult,
  ToolActivity,
} from "@/types/workflowBuilder";

const TICK_MS = 1000;

const FOCUS_RING =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1";

const FOLD_CLASS =
  "rounded-[var(--radius-node)] border border-line-border bg-surface-card text-[12px] text-ink-700";

// --- Clock -----------------------------------------------------------------------------

/** The current time in ms, refreshed every second while the component is mounted. */
function useClock(): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), TICK_MS);
    return () => clearInterval(timer);
  }, []);
  return now;
}

// --- Lists -----------------------------------------------------------------------------

function ActivityRow({ line }: { line: ToolActivity }) {
  const duration = formatDuration(line.duration_ms);
  const head = (
    <>
      <span className="min-w-0 flex-1 break-words">{line.label}</span>
      <span className="shrink-0 text-ink-500">{activityStatusText(line.status)}</span>
      {duration !== null ? <span className="shrink-0 text-ink-500">{duration}</span> : null}
    </>
  );

  // Script calls show their command. Other calls show only the summary.
  const command = line.kind === "script" ? line.command : null;
  if (line.summary === null && command === null) {
    return (
      <li className="flex min-w-0 items-center gap-2 px-1 py-0.5">{head}</li>
    );
  }

  return (
    <li className="min-w-0">
      <details>
        <summary
          className={`flex min-w-0 cursor-pointer items-center gap-2 rounded-[var(--radius-tag)] px-1 py-0.5 ${FOCUS_RING}`}
        >
          {head}
        </summary>
        <div className="flex flex-col gap-2 px-1 pb-1 pt-1.5">
          {line.summary !== null ? (
            <p className="break-words text-ink-700">{line.summary}</p>
          ) : null}
          {command !== null ? (
            <code className="block whitespace-pre-wrap break-all font-mono text-[11px] text-ink-900">
              {command}
            </code>
          ) : null}
        </div>
      </details>
    </li>
  );
}

/** The activity list of a turn, one line per tool call. Renders nothing when empty. */
export function ActivityList({ activity }: { activity: readonly ToolActivity[] }) {
  if (activity.length === 0) {
    return null;
  }
  return (
    <ul aria-label="Activity" className="flex flex-col gap-1 text-[12px] text-ink-700">
      {activity.map((line) => (
        <ActivityRow key={line.call_id} line={line} />
      ))}
    </ul>
  );
}

/** The check lines (validator and platform results). Renders nothing when empty. */
export function CheckList({ checks }: { checks: readonly CheckResult[] }) {
  if (checks.length === 0) {
    return null;
  }
  return (
    <ul aria-label="Checks" className="flex flex-col gap-1 text-[12px] text-ink-700">
      {checks.map((check, index) => (
        <li key={`${check.source}-${index}`} className="break-words">
          {checkLineText(check)}
        </li>
      ))}
    </ul>
  );
}

// --- Modes -----------------------------------------------------------------------------

export interface LiveProgressProps {
  /** The current stage label from the server, for example "Checking the workflow". */
  label: string;
  /** Client clock, ms since the epoch, when the turn started. */
  startedAt: number;
  activity: readonly ToolActivity[];
  checks: readonly CheckResult[];
  warnings: readonly LimitWarningView[];
}

/** Stagger of the three working dots, as in the run chat's reading indicator. */
const DOT_DELAYS = ["", "[animation-delay:150ms]", "[animation-delay:300ms]"] as const;

/** The run chat's three pulsing brand dots. Decorative; still under reduced motion. */
function WorkingDots() {
  return (
    <span aria-hidden="true" className="flex flex-none items-center gap-[3px]">
      {DOT_DELAYS.map((delay) => (
        <span
          key={delay || "first"}
          className={`h-[5px] w-[5px] animate-pulse rounded-full bg-brand motion-reduce:animate-none ${delay}`}
        />
      ))}
    </span>
  );
}

function LiveProgress({ label, startedAt, activity, checks, warnings }: LiveProgressProps) {
  const now = useClock();
  const elapsed = Math.max(0, now - startedAt);
  return (
    <section aria-label="Progress" className="flex flex-col gap-2 text-[12px] text-ink-700">
      <div className="flex min-h-[22px] items-center gap-[9px]">
        <WorkingDots />
        <p className="min-w-0 font-sans text-[11.5px] font-medium tabular-nums text-ink-500">{`${label} · ${formatElapsed(elapsed)}`}</p>
      </div>
      {warnings.map((warning) => (
        <p
          key={warning.kind}
          className="rounded-[var(--radius-node)] border border-status-amber-border bg-status-amber-fill px-3 py-1.5 text-[11px] text-ink-800"
        >
          {limitNoticeText(warning)}
        </p>
      ))}
      <CheckList checks={checks} />
      {activity.length > 0 ? (
        <details open className={FOLD_CLASS}>
          <summary
            className={`cursor-pointer rounded-[var(--radius-node)] px-3 py-1.5 font-semibold text-ink-700 ${FOCUS_RING}`}
          >
            {`Activity (${activity.length})`}
          </summary>
          <div className="border-t border-line-divider px-3 py-2">
            <ActivityList activity={activity} />
          </div>
        </details>
      ) : null}
    </section>
  );
}

export interface EndedProgressProps {
  summary: Pick<ActivitySummary, "actions" | "checks" | "duration_ms">;
  activity: readonly ToolActivity[];
  checks: readonly CheckResult[];
}

function EndedProgress({ summary, activity, checks }: EndedProgressProps) {
  return (
    <details className={FOLD_CLASS}>
      <summary
        className={`cursor-pointer rounded-[var(--radius-node)] px-3 py-1.5 font-semibold text-ink-700 ${FOCUS_RING}`}
      >
        {formatActivitySummary(summary)}
      </summary>
      <div className="flex flex-col gap-2 border-t border-line-divider px-3 py-2">
        <ActivityList activity={activity} />
        <CheckList checks={checks} />
      </div>
    </details>
  );
}

export type BuilderProgressProps =
  | ({ mode: "live" } & LiveProgressProps)
  | ({ mode: "ended" } & EndedProgressProps);

/** Progress of one turn: the live view while it runs, the collapsed summary once it has ended. */
export function BuilderProgress(props: BuilderProgressProps) {
  if (props.mode === "live") {
    return (
      <LiveProgress
        label={props.label}
        startedAt={props.startedAt}
        activity={props.activity}
        checks={props.checks}
        warnings={props.warnings}
      />
    );
  }
  return (
    <EndedProgress summary={props.summary} activity={props.activity} checks={props.checks} />
  );
}

export default BuilderProgress;
