"use client";

/**
 * RunHeader — the run-screen RIGHT-column header row (Phase 39, RUNUI-06/07).
 *
 * Reproduces the mock's header bar exactly (D39-1):
 *   • settled (`Hexaware Run.dc.html:144-173`): Version ▾ menu · Share · Download.
 *   • live    (`Hexaware Run - Live.dc.html:159-166`): status badge + note ·
 *     version chip · DISABLED Share (no Download while building).
 *   • failed  (`Hexaware Run - Failed.dc.html:94-98`): red "Run failed" badge ·
 *     version chip (no actions).
 *
 * SC-001 / ND-D: every value is GENERIC + LIVE — the version list comes from the
 * live `runFamily`, the status keys off the generic `RunLaneState` discriminator
 * (never a workflow name), and the chip label is derived from the live family.
 * ND-H: Share is CLIENT-ONLY — it copies the owner-auth-gated run deep link to the
 * clipboard; there is NO backend endpoint and no network request in this file
 * (enforced by the plan's banned-network-call grep). Styling routes through the
 * Phase-32 token layer.
 */
import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, Download, Loader2, Pause, Upload, Clock, X } from "lucide-react";

import type { RunFamily } from "@/types/index";
import type { RunLaneState } from "@/components/chat/RunChatLane";
// INV-12 — single relative-age formatter (shared with the left-lane header).
import { formatRelativeAge } from "@/components/chat/LaneRunHeader";

// ─── VersionMenu — the mock's "Version ▾" button + dropdown (settled only) ─────
// The keyboard/selection contract is the one proven by the retired LiveVersionChip
// (INV-12: that superseded chip is deleted, not duplicated), re-skinned to the
// mock's Version-button pixels. Renders nothing unless the on-screen run belongs
// to a ≥1-member family.
function VersionMenu({
  family,
  activeRunId,
  versionLabel,
  onSelectVersion,
}: {
  family: RunFamily | null;
  activeRunId: string | null;
  versionLabel: string;
  onSelectVersion: (memberId: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [highlightIdx, setHighlightIdx] = useState(0);
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const optionRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const members = family
    ? [...family.members].sort((a, b) => a.revision_index - b.revision_index)
    : [];
  const activeIdx = members.findIndex((m) => m.id === activeRunId);

  // Move keyboard focus INTO the listbox declaratively (mirrors the retired
  // LiveVersionChip focus-in-effect): whenever open, focus the highlighted option.
  useEffect(() => {
    if (open) optionRefs.current[highlightIdx]?.focus();
  }, [open, highlightIdx]);

  // Nothing to show without a family (history / pre-fetch / test renders).
  if (members.length < 1) return null;

  const openMenu = () => {
    setHighlightIdx(activeIdx >= 0 ? activeIdx : 0);
    setOpen(true);
  };
  const close = () => {
    setOpen(false);
    buttonRef.current?.focus();
  };
  const select = (memberId: string) => {
    onSelectVersion(memberId);
    setOpen(false);
    buttonRef.current?.focus();
  };

  const onListKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      e.preventDefault();
      close();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlightIdx((i) => Math.min(i + 1, members.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightIdx((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      const m = members[highlightIdx];
      if (m) select(m.id);
    }
  };

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        type="button"
        onClick={() => (open ? setOpen(false) : openMenu())}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`Version ${versionLabel}, choose version`}
        className="inline-flex items-center gap-[9px] rounded-[10px] border border-line-control bg-surface-card px-3 py-2 transition-colors hover:border-line-faint"
      >
        <span aria-hidden className="h-[7px] w-[7px] rounded-full bg-brand" />
        <span className="font-sans text-[13px] font-semibold leading-none text-ink-900">
          Version {versionLabel}
        </span>
        <ChevronDown
          aria-hidden
          className={`h-3.5 w-3.5 text-ink-400 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <>
          {/* Outside-click catcher. */}
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div
            role="listbox"
            aria-label="Run versions"
            onKeyDown={onListKeyDown}
            className="absolute left-0 top-[46px] z-20 w-[250px] rounded-[12px] border border-line-border bg-surface-white p-1.5 shadow-[0_12px_32px_rgba(17,17,20,0.12)]"
          >
            {members.map((member, i) => {
              const isActive = member.id === activeRunId;
              const isHighlighted = i === highlightIdx;
              return (
                <button
                  key={member.id}
                  ref={(el) => {
                    optionRefs.current[i] = el;
                  }}
                  type="button"
                  role="option"
                  aria-selected={isActive}
                  tabIndex={i === highlightIdx ? 0 : -1}
                  onMouseEnter={() => setHighlightIdx(i)}
                  onClick={() => select(member.id)}
                  className={`flex w-full items-center gap-2.5 rounded-[8px] px-2.5 py-2 text-left transition-colors ${
                    isHighlighted ? "bg-surface-warm" : "hover:bg-surface-warm"
                  }`}
                >
                  <span
                    aria-hidden
                    className={`h-[7px] w-[7px] flex-none rounded-full ${
                      isActive ? "bg-brand" : "bg-line-faint"
                    }`}
                  />
                  <div className="min-w-0 flex-1">
                    <p className="m-0 font-sans text-[13px] font-semibold leading-[1.2] text-ink-900">
                      Version v{i + 1}
                    </p>
                    <p className="m-0 mt-0.5 font-serif text-[11.5px] font-normal leading-none text-ink-300">
                      {formatRelativeAge(member.created_at) || "—"}
                    </p>
                  </div>
                  {isActive && <Check aria-hidden className="h-[15px] w-[15px] flex-none text-brand" />}
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

// ─── Status badge — the live/failed header eyebrow (SC-001, generic runState) ──
function StatusBadge({
  runState,
  failed,
  failureReason,
  currentAgentName,
  buildStepIndex,
  buildStepTotal,
  clarifyCount,
}: {
  runState: RunLaneState;
  failed: boolean;
  failureReason?: string;
  currentAgentName?: string;
  buildStepIndex?: number;
  buildStepTotal?: number;
  clarifyCount?: number;
}) {
  if (failed || runState === "terminal") {
    return (
      <span className="inline-flex items-center gap-[7px] rounded-[10px] border border-status-failed-border bg-status-failed-fill px-3 py-2 font-sans text-[11.5px] font-semibold leading-none text-status-failed">
        <X aria-hidden className="h-[13px] w-[13px]" strokeWidth={2.2} />
        Run failed{failureReason ? ` · ${failureReason}` : ""}
      </span>
    );
  }

  // Generic brand-toned live badges (building / clarify / gate).
  const brand = (
    icon: React.ReactNode,
    label: string,
    note?: string,
  ) => (
    <>
      <span className="inline-flex items-center gap-[7px] rounded-[10px] border border-brand-border bg-brand-fill px-3 py-2 font-sans text-[11.5px] font-semibold leading-none text-brand">
        {icon}
        {label}
      </span>
      {note && <span className="font-serif text-[12px] leading-none text-ink-400">{note}</span>}
    </>
  );

  if (runState === "gate") {
    return brand(
      <Pause aria-hidden className="h-[13px] w-[13px]" fill="currentColor" strokeWidth={0} />,
      "Paused · review gate",
      "task plan awaiting your approval",
    );
  }
  if (runState === "clarify") {
    return brand(
      <Clock aria-hidden className="h-[13px] w-[13px]" strokeWidth={2} />,
      "Waiting on you",
      clarifyCount && clarifyCount > 0
        ? `${clarifyCount} question${clarifyCount === 1 ? "" : "s"} to answer before the build starts`
        : "answer the questions before the build starts",
    );
  }
  // building (or any other running state)
  const label = currentAgentName ? `${currentAgentName} · streaming` : "Running · streaming";
  const note =
    buildStepIndex && buildStepTotal ? `building step ${buildStepIndex} of ${buildStepTotal}` : undefined;
  return brand(<Loader2 aria-hidden className="h-[13px] w-[13px] animate-spin" strokeWidth={2.4} />, label, note);
}

export interface RunHeaderProps {
  /** The GENERIC live-run state (mirrors the lane's discriminator, SC-001). */
  runState: RunLaneState;
  /** True when the terminal state is a hard failure (red badge). */
  failed?: boolean;
  /** Live failure LOCATION (first failed agent name) appended to the failed badge;
   *  ND-D live/generic, never the mock's fixed text. Absent → bare "Run failed". */
  failureReason?: string;
  /** The on-screen run's revision family (Version menu source, settled only). */
  family?: RunFamily | null;
  /** The active run id within the family (the checked / current version). */
  activeRunId?: string | null;
  /** The active version label, e.g. "v3" — the Version-button / chip text. */
  versionLabel?: string;
  /** Read-only older-version selection (reuses the family fetch). */
  onSelectVersion?: (memberId: string) => void;
  /** Client-only Share — copies the run deep link; disabled while running/failed. */
  onShare?: () => void;
  /** Primary deliverable download (settled only); disabled when nothing to download. */
  onDownload?: () => void;
  canDownload?: boolean;
  // ── Live badge inputs (generic/live values) ────────────────────────────────
  currentAgentName?: string;
  buildStepIndex?: number;
  buildStepTotal?: number;
  clarifyCount?: number;
}

export function RunHeader({
  runState,
  failed = false,
  failureReason,
  family = null,
  activeRunId = null,
  versionLabel,
  onSelectVersion,
  onShare,
  onDownload,
  canDownload = false,
  currentAgentName,
  buildStepIndex,
  buildStepTotal,
  clarifyCount,
}: RunHeaderProps) {
  const [copied, setCopied] = useState(false);
  const copiedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (copiedTimer.current) clearTimeout(copiedTimer.current); }, []);

  const isFailed = failed || runState === "terminal";
  const isRunning = runState === "building" || runState === "clarify" || runState === "gate";
  const isSettled = !isFailed && !isRunning; // complete / idle-with-content

  // Share is enabled ONLY in the settled state (mock: disabled cursor while
  // running, absent while failed). ND-H: copy the owner-auth-gated deep link.
  const shareEnabled = isSettled && !!onShare;
  const handleShare = () => {
    if (!shareEnabled || !onShare) return;
    onShare();
    setCopied(true);
    if (copiedTimer.current) clearTimeout(copiedTimer.current);
    copiedTimer.current = setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div
      data-testid="run-header"
      data-run-state={runState}
      className="flex flex-none items-center gap-[14px] px-[30px] pt-4"
    >
      {isSettled ? (
        <VersionMenu
          family={family}
          activeRunId={activeRunId}
          versionLabel={versionLabel ?? "v1"}
          onSelectVersion={onSelectVersion ?? (() => {})}
        />
      ) : (
        <StatusBadge
          runState={runState}
          failed={isFailed}
          failureReason={failureReason}
          currentAgentName={currentAgentName}
          buildStepIndex={buildStepIndex}
          buildStepTotal={buildStepTotal}
          clarifyCount={clarifyCount}
        />
      )}

      <div className="flex-1" />

      {/* Version chip — live/failed states carry a status-tinted version pill in
          place of the interactive menu (mock: "v1 draft" / "v1 · partial"). */}
      {!isSettled && versionLabel && (
        <span className="tabular-nums rounded-[8px] border border-line-control bg-surface-card px-2.5 py-[7px] font-serif text-[11.5px] font-normal leading-none text-ink-300">
          {versionLabel}
          {isRunning ? " draft" : isFailed ? " · partial" : ""}
        </span>
      )}

      {/* Share — settled = enabled; running = disabled; failed = absent. */}
      {!isFailed && (
        <button
          type="button"
          onClick={handleShare}
          disabled={!shareEnabled}
          aria-label="Copy a link to this run"
          className={`inline-flex items-center gap-2 rounded-[10px] border px-3.5 py-2 font-sans text-[13px] font-medium transition-colors ${
            shareEnabled
              ? "cursor-pointer border-line-control bg-surface-card text-ink-700 hover:border-line-faint hover:bg-surface-white"
              : "cursor-not-allowed border-line-control bg-surface-card text-ink-200"
          }`}
        >
          {copied ? <Check aria-hidden className="h-[15px] w-[15px]" /> : <Upload aria-hidden className="h-[15px] w-[15px]" strokeWidth={1.7} />}
          {copied ? "Link copied" : "Share"}
        </button>
      )}

      {/* Download — the mock shows it in the settled header only. */}
      {isSettled && (
        <button
          type="button"
          onClick={() => canDownload && onDownload?.()}
          disabled={!canDownload || !onDownload}
          aria-label="Download the deliverable"
          className={`inline-flex items-center gap-2 rounded-[10px] border-none px-[15px] py-2 font-sans text-[13px] font-semibold text-white transition-colors ${
            canDownload && onDownload ? "cursor-pointer bg-brand hover:bg-brand-pressed" : "cursor-not-allowed bg-brand/50"
          }`}
        >
          <Download aria-hidden className="h-[15px] w-[15px]" strokeWidth={1.9} />
          Download
        </button>
      )}
    </div>
  );
}

export default RunHeader;
