"use client";

/**
 * RunEngineNotice — engine-fact presentation for chain-context and
 * finalization-failure notices (Task 11.5, Requirement 20).
 *
 * NOT a chat message from an agent. These notices surface events that the
 * engine emitted (`chain_context_unavailable`, `run_finalization_failed`) and
 * were stored in `pipelineState` by the Task 9.2 handlers.
 *
 * Accessibility contract (Req 20 AC 5):
 *  - Non-color-only indicator: icon + label text, never color alone.
 *  - `role="status"` with `aria-live="polite"` so the transcript's
 *    `role="log"` (ChatPanel.tsx:283) announces it as it appears.
 *  - A details button exposes the reason code in a keyboard-reachable panel.
 *  - Unknown reason codes fall back to a generic message and "contact support"
 *    action — never a raw internal string shown to the user.
 *
 * Exactly ONE element with `role="alert"` may exist in the tree at a time
 * (established at AgentsPopup.tsx:2670). RunEngineNotice uses `role="status"`
 * so it can coexist with that alert without violating the convention.
 */

import { useState } from "react";
import { AlertTriangle, Info, ChevronDown, ChevronUp } from "lucide-react";

// ─── Reason → action mapping ─────────────────────────────────────────────────
//
// Five bounded reason codes from the backend (Req 20 AC 3, Req 19 AC 4).
// "run_finalization_failed" is NOT one of the five chain-refusal codes; it
// is its own event type with its own copy and action.

type ChainUnavailableReason =
  | "source_running"
  | "source_not_finalized"
  | "source_non_chainable"
  | "source_payload_missing"
  | "source_provenance_conflict"
  // Task 11.8 (Req 21 AC 9): mixed-deploy reason codes.
  | "incompatible_backend"
  | "unsupported_version_combination";

type FinalizationFailedReason = string; // bounded codes, unknown falls back

interface NoticeContent {
  headline: string;
  detail: string;
  actionLabel?: string;
  actionKind?: "retry" | "choose-source" | "retry-later" | "contact-support";
}

function chainUnavailableContent(reason: string): NoticeContent {
  switch (reason as ChainUnavailableReason) {
    case "source_running":
      return {
        headline: "Source run is still in progress",
        detail:
          "The source run must finish before its output can be used as context. Try again once it completes.",
        actionLabel: "Retry later",
        actionKind: "retry-later",
      };
    case "source_not_finalized":
      return {
        headline: "Source run output is not yet ready",
        detail:
          "The source run completed but its output hasn't been finalized yet. Retry in a moment.",
        actionLabel: "Retry",
        actionKind: "retry",
      };
    case "source_non_chainable":
      return {
        headline: "Source run cannot be used as context",
        detail:
          "This run's output has been marked as non-chainable and cannot be passed to another run. Choose a different source.",
        actionLabel: "Choose a different source",
        actionKind: "choose-source",
      };
    case "source_payload_missing":
      return {
        headline: "Source run output is unavailable",
        detail:
          "The source run's output could not be retrieved. It may have been swept or was never materialized. Choose a different source.",
        actionLabel: "Choose a different source",
        actionKind: "choose-source",
      };
    case "source_provenance_conflict":
      return {
        headline: "Source run provenance could not be verified",
        detail:
          "The source output's identity does not match its declared version. This may indicate a data integrity issue. Choose a different source.",
        actionLabel: "Choose a different source",
        actionKind: "choose-source",
      };
    // Task 11.8 (Req 21 AC 9): New frontend against an older backend.
    // The backend accepted the launch but does not support v2 chaining, so
    // source_workflow_run_id was silently ignored and the run started without
    // chain context.
    case "incompatible_backend":
      return {
        headline: "Chain context unavailable: backend version mismatch",
        detail:
          "The backend does not yet support v2 chain context. This run will start without the source run's output. Upgrade the backend or choose a workflow that does not require chain context.",
        actionLabel: "Wait for backend upgrade",
        actionKind: "retry-later",
      };
    // Task 11.8 (Req 21 AC 9): any other unsupported version combination.
    case "unsupported_version_combination":
      return {
        headline: "Chain context unavailable: unsupported version combination",
        detail:
          "The combination of frontend and backend versions used for this launch is not supported for chain context delivery. The run will proceed without chain context.",
        actionLabel: "Contact support",
        actionKind: "contact-support",
      };
    default:
      // Unknown reason code — generic fallback, never expose the raw code in
      // user-facing copy. The reason code is surfaced inside the details panel
      // so support can read it.
      return {
        headline: "Source context is unavailable",
        detail:
          "An unexpected error prevented the source run's output from being used. This run will proceed without it.",
        actionLabel: "Contact support",
        actionKind: "contact-support",
      };
  }
}

function finalizationFailedContent(reason: FinalizationFailedReason): NoticeContent {
  // All reason codes fall through to the same user message; the reason code
  // is exposed in the details panel for support escalation.
  return {
    headline: "Run finalization encountered an issue",
    detail:
      "The run completed but its version record could not be fully saved. The output is still accessible. If this persists, contact support.",
    actionLabel: `Contact support (${reason || "unknown"})`,
    actionKind: "contact-support",
  };
}

// ─── Component ───────────────────────────────────────────────────────────────

export interface RunEngineNoticeProps {
  /**
   * Which event this notice surfaces.
   * - `"chain_unavailable"` — driven by `chain_context_unavailable` event.
   * - `"finalization_failed"` — driven by `run_finalization_failed` event.
   */
  type: "chain_unavailable" | "finalization_failed";
  /**
   * The bounded reason code from the server. Unknown values fall back to a
   * generic message — never rendered raw in user-visible copy.
   */
  reasonCode?: string;
  /**
   * Optional stable className for the outer container.
   */
  className?: string;
}

export function RunEngineNotice({
  type,
  reasonCode,
  className = "",
}: RunEngineNoticeProps) {
  const [detailOpen, setDetailOpen] = useState(false);

  const content =
    type === "chain_unavailable"
      ? chainUnavailableContent(reasonCode ?? "unknown")
      : finalizationFailedContent(reasonCode ?? "unknown");

  // Visual variant: chain_unavailable is informational (info tone); finalization
  // failures are warnings (amber tone). Both are NON-color-only: icon + label.
  const isWarning = type === "finalization_failed";

  const iconColorClass = isWarning
    ? "text-status-amber"
    : "text-brand";
  const borderClass = isWarning
    ? "border-[var(--status-amber-border)] bg-[var(--status-amber-fill)]"
    : "border-line-border bg-surface-card";
  const headlineColorClass = isWarning
    ? "text-status-amber"
    : "text-ink-700";

  const detailButtonId = `run-engine-notice-detail-${type}`;
  const detailPanelId = `run-engine-notice-panel-${type}`;

  return (
    // role="status" + aria-live="polite": announced by AT as it mounts.
    // The transcript's role="log" (ChatPanel.tsx:283) also announces additions,
    // so AT hears it through two complementary channels.
    <div
      role="status"
      aria-live="polite"
      aria-atomic="true"
      data-testid={`run-engine-notice-${type}`}
      className={[
        "mx-4 mb-2 rounded-[10px] border px-3.5 py-2.5",
        borderClass,
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {/* Header row — icon + headline + toggle button */}
      <div className="flex items-start gap-2.5">
        {/* Non-color-only indicator: icon conveys meaning independently of color. */}
        <span aria-hidden="true" className={`mt-[1px] flex-none ${iconColorClass}`}>
          {isWarning ? (
            <AlertTriangle className="h-[14px] w-[14px]" strokeWidth={2} />
          ) : (
            <Info className="h-[14px] w-[14px]" strokeWidth={2} />
          )}
        </span>

        {/* Headline — the only text visible by default; supplementary detail is hidden. */}
        <p className={`flex-1 font-sans text-[12.5px] font-medium leading-snug ${headlineColorClass}`}>
          {content.headline}
        </p>

        {/* Keyboard-reachable detail toggle */}
        <button
          id={detailButtonId}
          type="button"
          aria-expanded={detailOpen}
          aria-controls={detailPanelId}
          onClick={() => setDetailOpen((v) => !v)}
          className="flex-none rounded-[6px] p-0.5 text-ink-400 transition-colors hover:text-ink-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand"
          aria-label={detailOpen ? "Hide details" : "Show details"}
        >
          {detailOpen ? (
            <ChevronUp className="h-3.5 w-3.5" strokeWidth={2} />
          ) : (
            <ChevronDown className="h-3.5 w-3.5" strokeWidth={2} />
          )}
        </button>
      </div>

      {/* Expandable detail panel — programmatically associated via aria-controls */}
      {detailOpen && (
        <div
          id={detailPanelId}
          role="region"
          aria-labelledby={detailButtonId}
          className="mt-2 pl-[22px]"
        >
          <p className="font-sans text-[11.5px] leading-relaxed text-ink-500">
            {content.detail}
          </p>
          {content.actionLabel && content.actionKind !== "contact-support" && (
            <p className="mt-1 font-sans text-[11px] font-medium text-brand">
              {/* Suggested action — no action the server refuses (Req 20 AC 4).
                  This is copy guidance only; the actual retry/navigation is
                  driven by the caller. */}
              {content.actionLabel}
            </p>
          )}
          {content.actionKind === "contact-support" && (
            <p className="mt-1 font-sans text-[11px] text-ink-400">
              {content.actionLabel}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export default RunEngineNotice;
