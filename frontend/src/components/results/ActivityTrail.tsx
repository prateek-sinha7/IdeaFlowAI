"use client";

/**
 * ActivityTrail — what a step did, as a row of small pills rather than prose.
 *
 * `reason › read ×4 › write › output`: the one thing on a step you can read
 * without reading. Each pill carries an icon and a verb in one muted tone, so
 * the trail never competes with the step's content; only a failed call gets a
 * pale colour of its own. Hover a pill for the files it touched. A live step
 * shows full labels and may wrap; a settled step summarises to icons on one line.
 */

import { useLayoutEffect, useRef, useState, type ComponentType } from "react";
import {
  Brain,
  ChevronRight,
  FileText,
  Globe,
  MessageSquare,
  PenLine,
  Search,
  Sparkles,
  Terminal,
  Wrench,
} from "lucide-react";
import type { ActivityKind, ActivityRun } from "@/lib/runChain";

const KIND_LABEL: Record<ActivityKind, string> = {
  reason: "reason",
  read: "read",
  write: "write",
  search: "search",
  run: "run",
  browse: "browse",
  ask: "ask",
  tool: "tool",
  output: "output",
};

export const KIND_ICON: Record<ActivityKind, ComponentType<{ className?: string }>> = {
  reason: Brain,
  read: FileText,
  write: PenLine,
  search: Search,
  run: Terminal,
  browse: Globe,
  ask: MessageSquare,
  tool: Wrench,
  output: Sparkles,
};

function toneFor(kind: ActivityKind, hasFailed?: boolean): string {
  // Dim on purpose. The trail is a footnote to the step, not a headline: one
  // muted tone for every kind, the icon carries the meaning, and only a failed
  // call gets a (pale) colour of its own.
  void kind; // one gray for every kind; the icon is the only distinction
  if (hasFailed) return "border-status-failed-border bg-status-failed-fill text-status-failed opacity-70";
  return "border-line-faint-row bg-surface-warm text-ink-500";
}

export function ActivityTrail({
  runs,
  className = "",
  status,
  iconsOnly: iconsOnlyProp,
  maxPills: maxPillsProp,
}: {
  runs: ActivityRun[];
  className?: string;
  /** The step's status; while it runs, the last pill pulses. */
  status?: string;
  /** Icon and count only; the verb lives in the tooltip and the aria-label.
   *  Unset = by status: a LIVE step shows full labels and may wrap, because it
   *  is what you are watching; a settled step summarises to icons on one line. */
  iconsOnly?: boolean;
  /** Fixed pill budget (tests, or a caller that knows its width). Unset = fit
   *  the row: the trail measures itself and folds until it is one line. */
  maxPills?: number;
}) {
  const isLive = status === "running" || status === "thinking";
  const iconsOnly = iconsOnlyProp ?? !isLive;
  const wraps = !iconsOnly; // a live, labelled trail may take a second line
  const ref = useRef<HTMLSpanElement>(null);
  // Fit-to-width: start with everything, and while the row overflows, drop one
  // pill and let the fold absorb it. A resize resets and the loop runs again.
  const [budget, setBudget] = useState<number>(maxPillsProp ?? Number.MAX_SAFE_INTEGER);
  useLayoutEffect(() => {
    if (maxPillsProp !== undefined || wraps) return;
    const el = ref.current;
    if (!el) return;
    if (el.scrollWidth > el.clientWidth + 1 && budget > 3) {
      setBudget(Math.min(budget, runs.length) - 1);
    }
  });
  useLayoutEffect(() => {
    if (maxPillsProp !== undefined || typeof ResizeObserver === "undefined") return;
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setBudget(Number.MAX_SAFE_INTEGER));
    ro.observe(el);
    return () => ro.disconnect();
  }, [maxPillsProp]);
  if (runs.length === 0) return null;

  // One line, always. A long trail keeps its ends and its heavy pills (the
  // `read ×66` is the story of the step) and folds the light ones between them
  // into "+N" pills; each fold's tooltip lists exactly what it hides.
  const MAX_PILLS = wraps ? Number.MAX_SAFE_INTEGER : Math.max(3, budget);
  type Cell = { run: ActivityRun; hidden?: ActivityRun[] };
  let cells: Cell[] = runs.map((run) => ({ run }));
  if (runs.length > MAX_PILLS) {
    const keep = new Set<number>([0, runs.length - 1]);
    [...runs.keys()]
      .filter((i) => !keep.has(i))
      .sort((a, b) => runs[b].count - runs[a].count || a - b)
      .slice(0, MAX_PILLS - 2)
      .forEach((i) => keep.add(i));
    cells = [];
    runs.forEach((run, i) => {
      if (keep.has(i)) cells.push({ run });
      else if (cells.length && cells[cells.length - 1].hidden) cells[cells.length - 1].hidden!.push(run);
      else cells.push({ run: { kind: "tool", count: 1 }, hidden: [run] });
    });
  }

  return (
    <span
      ref={ref}
      data-testid="activity-trail"
      aria-label={`Activity: ${runs
        .map((r) => (r.count > 1 ? `${r.kind} ${r.count} times` : r.kind))
        .join(", then ")}`}
      className={`flex min-w-0 max-w-full items-center ${wraps ? "flex-wrap gap-y-1" : "overflow-hidden whitespace-nowrap"} ${className}`}
    >
      {cells.map(({ run, hidden }, i) => {
        const isLast = i === cells.length - 1;
        if (hidden) {
          const summary = hidden.map((h) => (h.count > 1 ? `${h.kind} ×${h.count}` : h.kind)).join(" › ");
          return (
            <span key={`more-${i}`} className="inline-flex items-center">
              <ChevronRight aria-hidden className="mx-[1px] h-3 w-3 flex-none text-line-faint opacity-70" />
              <span
                data-testid="activity-more"
                title={summary}
                className="inline-flex h-[20px] cursor-default select-none items-center rounded-full border border-dashed border-line-control bg-surface-white px-2 font-sans text-[10.5px] font-medium leading-none text-ink-500"
              >
                +{hidden.length}
              </span>
            </span>
          );
        }
        const Icon = KIND_ICON[run.kind];
        const paths = run.paths?.slice(0, 5) ?? [];
        // Tooltip as a short column, not a sentence: the kind and count first,
        // then one file per line with only its name (a full path is unreadable
        // in a hover), then how many calls the lines did not cover.
        const fileName = (p: string) => {
          const parts = p.split("/").filter(Boolean);
          return parts.length > 1 ? `…/${parts[parts.length - 1]}` : p;
        };
        const tooltip = [
          `${KIND_LABEL[run.kind]}${run.count > 1 ? ` ×${run.count}` : ""}${run.tools?.length ? ` · ${run.tools.join(", ")}` : ""}`,
          ...paths.map(fileName),
          run.count > paths.length && paths.length > 0 ? `+${run.count - paths.length} more` : "",
          run.hasFailed ? "a call returned an error" : "",
        ]
          .filter(Boolean)
          .join("\n");
        return (
          <span key={`${run.kind}-${i}`} className="inline-flex flex-none items-center">
            {i > 0 && <ChevronRight aria-hidden className="mx-[1px] h-3 w-3 flex-none text-line-faint opacity-70" />}
            <span
              data-testid="activity-box"
              data-kind={run.kind}
              title={tooltip}
              className={`inline-flex h-[20px] cursor-default select-none items-center gap-[3px] rounded-full border ${iconsOnly ? "px-[5px]" : "px-1.5"} font-sans text-[10.5px] font-medium leading-none ${toneFor(
                run.kind,
                run.hasFailed,
              )} ${isLive && isLast ? "animate-pulse" : ""}`}
            >
              <Icon className={iconsOnly ? "h-3.5 w-3.5 flex-none" : "h-3 w-3 flex-none"} />
              {!iconsOnly && KIND_LABEL[run.kind]}
              {run.hasFailed && <span aria-label="failed">!</span>}
              {run.count > 1 && <span className="tabular-nums opacity-70">×{run.count}</span>}
            </span>
          </span>
        );
      })}
    </span>
  );
}

export default ActivityTrail;
