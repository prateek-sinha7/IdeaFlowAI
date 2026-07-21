"use client";

/**
 * Badge — shared run-screen status-chip primitive (SC-1, D-15).
 *
 * Keyed on the canonical status model (evidence 11 §B3): running->blue,
 * done->green, failed->red, cancelled->amber, queued->neutral-grey. Each key
 * maps to its status-ramp token classes (text + fill + border) from the plan-01
 * token layer — NO raw hex. `status` is a GENERIC prop (never a workflow name,
 * SC-001). `completed` normalizes to `done`; unknown -> neutral-grey (no throw).
 */
export type BadgeStatus =
  | "running"
  | "done"
  | "failed"
  | "cancelled"
  | "gate"
  | "queued";

// Status key -> status-ramp token classes. Fill/border ramp vars live in :root
// (not @theme), so they are consumed via arbitrary var() utilities.
const STATUS_CLASS: Record<BadgeStatus, string> = {
  running:
    "text-status-running bg-[var(--status-running-fill)] border-[var(--status-running-border)]",
  done: "text-status-done bg-[var(--status-done-fill)] border-[var(--status-done-border)]",
  failed:
    "text-status-failed bg-[var(--status-failed-fill)] border-[var(--status-failed-border)]",
  cancelled:
    "text-status-amber bg-[var(--status-amber-fill)] border-[var(--status-amber-border)]",
  // gate/review-paused shares the amber ramp (globals.css:103 "cancelled + gate/review").
  gate:
    "text-status-amber bg-[var(--status-amber-fill)] border-[var(--status-amber-border)]",
  queued:
    "text-status-queued bg-[var(--status-queued-fill)] border-[var(--status-queued-border)]",
};

/** Normalize a free-string status into a canonical badge key (§B3). */
function normalizeStatus(status: string): BadgeStatus {
  const s = (status || "").toLowerCase();
  if (s === "completed" || s === "done" || s === "success") return "done";
  if (s === "running") return "running";
  if (s === "failed" || s === "error") return "failed";
  if (s === "cancelled" || s === "canceled") return "cancelled";
  if (s === "gate" || s === "review" || s === "paused") return "gate";
  if (s === "queued" || s === "pending") return "queued";
  return "queued"; // unknown -> neutral-grey (never throws)
}

export interface BadgeProps {
  status: BadgeStatus | string;
  label?: string;
  className?: string;
}

export function Badge({ status, label, className = "" }: BadgeProps) {
  const key = normalizeStatus(status);
  return (
    <span
      className={[
        "inline-flex items-center gap-1 border rounded-[var(--radius-tag)] px-1.5 py-0.5 font-sans text-[8.5px] font-semibold uppercase tracking-wide leading-none",
        STATUS_CLASS[key],
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {/* LW-02: fall back to the NORMALIZED canonical key, never the raw
          `status` — an unknown/free-string status renders the safe "queued"
          default (not arbitrary text uppercased by the chip). */}
      {label ?? key}
    </span>
  );
}

export default Badge;
