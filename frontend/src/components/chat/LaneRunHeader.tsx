"use client";

/**
 * LaneRunHeader — the run-screen LEFT-lane run header (Phase 39, RUNUI-06).
 *
 * Reproduces the mock's settled/live/failed header composition exactly (D39-1;
 * `Hexaware Run.dc.html:51-64`): a "Back to history" link, a type eyebrow · dot ·
 * status token, the run title, and a meta row (elapsed · N/M agents · tokens).
 *
 * SC-001 / ND-D: every value is GENERIC + LIVE — the type is humanized from the
 * `pipeline_type` / `runType` string (never branched on a workflow name), the
 * status token keys off the generic `runState`, and the meta row derives from the
 * live `pipelineState` via the shared `runStats` formatters (INV-12 single
 * source). It NEVER clones the mock's fixed elapsed / token values.
 */
import type { ReactNode } from "react";
import { Check, ChevronLeft, X } from "lucide-react";

import type { PipelineRunState } from "@/types/index";
import { formatDuration, formatTokenCount } from "@/lib/runStats";
import type { RunLaneState } from "./RunChatLane";

/**
 * Humanize a raw `pipeline_type` into a display eyebrow — a GENERIC string
 * transform (split on `_`/`-`/space, drop a leading `od` engine-domain segment,
 * title-case). Never a workflow-name branch (SC-001).
 */
export function humanizeRunType(raw?: string | null): string {
  if (!raw) return "";
  const parts = raw
    .split(/[_\-\s]+/)
    .filter(Boolean)
    .filter((seg, i) => !(i === 0 && seg.toLowerCase() === "od"));
  return parts
    .map((seg) => seg.charAt(0).toUpperCase() + seg.slice(1).toLowerCase())
    .join(" ");
}

/** The three meta parts of the header row, derived from live `pipelineState`. */
export interface LaneMeta {
  elapsed: string;
  agents: string;
  tokens: string;
}

/**
 * Derive the header meta row from live telemetry (SC-001). Empty parts are
 * suppressed so a fresh/partial run never renders a dangling "0/0 agents".
 */
export function deriveLaneMeta(pipelineState?: PipelineRunState): LaneMeta {
  const elapsed = formatDuration(pipelineState?.totalDuration);
  const total = pipelineState?.agents?.length ?? 0;
  const done = pipelineState?.completedCount ?? 0;
  const agents = total > 0 ? `${done}/${total} agents` : "";
  const tok = pipelineState?.totalTokens ?? 0;
  const tokens = tok > 0 ? `${formatTokenCount(tok)} tokens` : "";
  return { elapsed, agents, tokens };
}

type StatusTone = "done" | "running" | "failed" | "amber" | "neutral";

interface LaneStatus {
  label: string;
  tone: StatusTone;
  /** A steady completed check (settled) vs. a pulsing phase pill (live). */
  variant: "token" | "pill";
}

/**
 * Map the GENERIC lane state (+ the terminal `pipelineState` markers) to the
 * header status token. Keys off `runState` only — never a workflow name.
 */
function laneStatus(
  runState: RunLaneState,
  pipelineState?: PipelineRunState,
): LaneStatus | null {
  switch (runState) {
    case "building":
      return { label: "Running", tone: "running", variant: "pill" };
    case "clarify":
      return { label: "Clarifying", tone: "running", variant: "pill" };
    case "gate":
      return { label: "Awaiting approval", tone: "running", variant: "pill" };
    case "complete":
      return { label: "Done", tone: "done", variant: "token" };
    case "terminal":
      if (pipelineState?.cancelled)
        return { label: "Cancelled", tone: "neutral", variant: "token" };
      if (pipelineState?.failed)
        return { label: "Failed", tone: "failed", variant: "token" };
      if (pipelineState?.degraded)
        return { label: "Issues", tone: "amber", variant: "token" };
      return { label: "Ended", tone: "neutral", variant: "token" };
    case "idle":
    default:
      // A reopened, settled run with completed work reads as Done; a fresh idle
      // lane shows no status token.
      return (pipelineState?.completedCount ?? 0) > 0
        ? { label: "Done", tone: "done", variant: "token" }
        : null;
  }
}

function StatusToken({ status }: { status: LaneStatus }) {
  if (status.variant === "pill") {
    return (
      <span
        data-testid="lane-run-status"
        data-status-tone={status.tone}
        className="inline-flex items-center gap-1.5 rounded-[var(--radius-tag)] border border-brand-border bg-brand-fill px-2 py-1 font-sans text-[11px] font-semibold text-brand"
      >
        <span className="h-[6px] w-[6px] animate-pulse rounded-full bg-brand" />
        {status.label}
      </span>
    );
  }
  // Settled / terminal token — an inline check (Done) or cross (Failed).
  const tone =
    status.tone === "failed"
      ? "text-status-failed"
      : status.tone === "amber"
        ? "text-status-amber"
        : status.tone === "neutral"
          ? "text-ink-500"
          : "text-ink-600";
  return (
    <span
      data-testid="lane-run-status"
      data-status-tone={status.tone}
      className={`inline-flex items-center gap-[5px] font-sans text-[11px] font-medium ${tone}`}
    >
      {status.tone === "failed" ? (
        <X className="h-3 w-3 text-status-failed" strokeWidth={2.2} />
      ) : status.tone === "done" ? (
        <Check className="h-3 w-3 text-ink-900" strokeWidth={2} />
      ) : null}
      {status.label}
    </span>
  );
}

export interface LaneRunHeaderProps {
  /** The GENERIC live-run state that drives the status token (D-12, SC-001). */
  runState: RunLaneState;
  /** Live telemetry — the source for the meta row + terminal markers. */
  pipelineState?: PipelineRunState;
  /** An explicit display label; falls back to the humanized `pipeline_type`. */
  runType?: string;
  /** The run title (falls back to the caller's brief). */
  runTitle?: string;
  /** Back-to-history link — rendered only when supplied (wired by 39-05). */
  onBackToHistory?: () => void;
  /** Right-aligned actions in the back-link row (Stop / Compact while running). */
  actions?: ReactNode;
}

export function LaneRunHeader({
  runState,
  pipelineState,
  runType,
  runTitle,
  onBackToHistory,
  actions,
}: LaneRunHeaderProps) {
  const type = runType || humanizeRunType(pipelineState?.pipeline_type);
  const meta = deriveLaneMeta(pipelineState);
  const status = laneStatus(runState, pipelineState);
  const metaParts = [meta.elapsed, meta.agents, meta.tokens].filter(Boolean);

  // The back link always renders (mock fidelity). `onBackToHistory` overrides the
  // exact target (wired by 39-05); the default navigates back to the prior view
  // (the run history / dashboard) so the link is present + functional now.
  const handleBack =
    onBackToHistory ??
    (() => {
      if (typeof window !== "undefined") window.history.back();
    });

  return (
    <div
      data-testid="lane-run-header"
      className="flex-none border-b border-line-border bg-surface-warm px-[18px] pb-[14px] pt-4"
    >
      <div className="mb-[15px] flex items-center justify-between gap-2">
        <button
          type="button"
          data-testid="lane-back"
          onClick={handleBack}
          className="inline-flex items-center gap-[7px] font-sans text-[13px] font-medium text-ink-500 transition-colors hover:text-ink-900"
        >
          <ChevronLeft className="h-[15px] w-[15px]" strokeWidth={1.7} />
          Back to history
        </button>
        {actions && <div className="flex items-center gap-1.5">{actions}</div>}
      </div>

      {(type || status) && (
        <div className="mb-[9px] flex items-center gap-2">
          {type && (
            <span
              data-testid="lane-run-type"
              className="font-sans text-[10.5px] font-semibold uppercase tracking-[0.13em] text-ink-300"
            >
              {type}
            </span>
          )}
          {type && status && (
            <span className="h-[3px] w-[3px] rounded-full bg-line-faint" />
          )}
          {status && <StatusToken status={status} />}
        </div>
      )}

      {runTitle && (
        <p
          data-testid="lane-run-title"
          className="m-0 font-sans text-[20px] font-light leading-[1.28] tracking-[-0.01em] text-ink-900"
        >
          {runTitle}
        </p>
      )}

      {metaParts.length > 0 && (
        <div
          data-testid="lane-run-meta"
          className="mt-[9px] flex items-center gap-2 font-serif text-[12px] tabular-nums text-ink-400"
        >
          {metaParts.map((part, i) => (
            <span key={part} className="flex items-center gap-2">
              {i > 0 && <span className="text-line-faint">·</span>}
              <span>{part}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
