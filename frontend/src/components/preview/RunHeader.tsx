"use client";

/**
 * RunHeader — the run-screen RIGHT-column header row (Phase 39, RUNUI-06/07).
 *
 * Share button (Option B): opens a popover that mints a public /s/{token} link.
 * The caller supplies `onShare` for backwards compatibility; when `runId` is also
 * provided the button calls POST /api/runs/{id}/share, shows a copy-able URL, and
 * offers a Revoke action. Falls back to the legacy clipboard-copy when only
 * `onShare` is supplied (history reopens that don't carry a runId).
 *
 * SC-001 / ND-D: status keys off the generic `RunLaneState` discriminator — never
 * a workflow name. Styling routes through the Phase-32 token layer.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Check, ChevronDown, Download, Link2, Loader2, Pause, Trash2, Upload, Clock, X } from "lucide-react";

import type { RunFamily } from "@/types/index";
import type { RunLaneState } from "@/components/chat/RunChatLane";
import { formatRelativeAge } from "@/components/chat/LaneRunHeader";
import { getToken, postShareRun, deleteShareRun } from "@/lib/api";

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
  /** Optional: the settled run's id — used to call POST /api/runs/{id}/share
   *  and mint a public link. When absent, falls back to the legacy onShare callback. */
  runId?: string;
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
  runId,
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

  const shareEnabled = isSettled && !!onShare;
  const handleShare = () => {
    if (!shareEnabled || !onShare) return;
    onShare();
    setCopied(true);
    if (copiedTimer.current) clearTimeout(copiedTimer.current);
    copiedTimer.current = setTimeout(() => setCopied(false), 2000);
  };

  // ── Share popover state (Option B public link) ────────────────────────────
  const [sharePopoverOpen, setSharePopoverOpen] = useState(false);
  const [shareLoading, setShareLoading] = useState(false);
  const [shareLink, setShareLink] = useState<string | null>(null);
  const [shareError, setShareError] = useState<string | null>(null);
  const [linkCopied, setLinkCopied] = useState(false);
  const linkCopiedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  // Close popover on outside click.
  useEffect(() => {
    if (!sharePopoverOpen) return;
    const handler = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setSharePopoverOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [sharePopoverOpen]);

  const handleOpenSharePopover = useCallback(async () => {
    if (!isSettled) return;
    setSharePopoverOpen(true);
    setShareError(null);
    // If we have a runId, mint/refresh the share link via the API.
    if (runId) {
      setShareLoading(true);
      try {
        const jwt = getToken();
        if (!jwt) throw new Error("Not authenticated");
        const result = await postShareRun(jwt, runId);
        const fullUrl = typeof window !== "undefined"
          ? `${window.location.origin}${result.share_url}`
          : result.share_url;
        setShareLink(fullUrl);
      } catch (err) {
        setShareError((err as Error)?.message ?? "Could not create share link");
      } finally {
        setShareLoading(false);
      }
    }
  }, [isSettled, runId]);

  const handleCopyShareLink = useCallback(() => {
    if (!shareLink) return;
    void navigator.clipboard?.writeText(shareLink);
    setLinkCopied(true);
    if (linkCopiedTimer.current) clearTimeout(linkCopiedTimer.current);
    linkCopiedTimer.current = setTimeout(() => setLinkCopied(false), 2000);
  }, [shareLink]);

  const handleRevokeShare = useCallback(async () => {
    if (!runId) return;
    setShareLoading(true);
    try {
      const jwt = getToken();
      if (!jwt) return;
      await deleteShareRun(jwt, runId);
      setShareLink(null);
      setSharePopoverOpen(false);
    } catch { /* best-effort */ }
    finally { setShareLoading(false); }
  }, [runId]);

  return (
    <div
      data-testid="run-header"
      data-run-state={runState}
      className="flex flex-none items-center gap-[14px] px-[30px] pt-4"
    >
      {/* Version chip — live/failed states: moved to the LEFT of the status badge
          so it reads "[v1 draft] [Running · Streaming]" (Option A, user request).
          Settled state: the VersionMenu below takes this slot instead. */}
      {!isSettled && versionLabel && (
        <span className="tabular-nums rounded-[8px] border border-line-control bg-surface-card px-2.5 py-[7px] font-serif text-[11.5px] font-normal leading-none text-ink-300">
          {versionLabel}
          {isRunning ? " draft" : isFailed ? " · partial" : ""}
        </span>
      )}

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

      {/* Share — settled = enabled with popover; running = disabled; failed = absent. */}
      {!isFailed && (
        <div className="relative" ref={popoverRef}>
          <button
            type="button"
            onClick={handleOpenSharePopover}
            disabled={!isSettled}
            aria-label="Share this run"
            className={`inline-flex items-center gap-2 rounded-[10px] border px-3.5 py-2 font-sans text-[13px] font-medium transition-colors ${
              isSettled
                ? "cursor-pointer border-line-control bg-surface-card text-ink-700 hover:border-line-faint hover:bg-surface-white"
                : "cursor-not-allowed border-line-control bg-surface-card text-ink-200"
            }`}
          >
            <Upload aria-hidden className="h-[15px] w-[15px]" strokeWidth={1.7} />
            Share
          </button>

          {sharePopoverOpen && (
            <div className="absolute right-0 top-full mt-2 z-50 w-[320px] rounded-[14px] border border-line-border bg-surface-white shadow-xl p-4 flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <p className="text-[13px] font-semibold text-ink-900">Share deliverable</p>
                <button
                  type="button"
                  onClick={() => setSharePopoverOpen(false)}
                  aria-label="Close share panel"
                  className="text-ink-400 hover:text-ink-700"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              {shareLoading ? (
                <div className="flex items-center gap-2 text-[12px] text-ink-400 py-2">
                  <Loader2 className="h-4 w-4 animate-spin" /> Generating link…
                </div>
              ) : shareError ? (
                <p className="text-[12px] text-status-failed">{shareError}</p>
              ) : shareLink ? (
                <>
                  <p className="text-[11.5px] text-ink-500 leading-relaxed">
                    Anyone with this link can view the deliverable — no login required.
                    Link expires in 30 days.
                  </p>
                  <div className="flex items-center gap-2 rounded-[9px] border border-line-border bg-surface-warm px-3 py-2">
                    <Link2 aria-hidden className="h-3.5 w-3.5 flex-none text-ink-400" />
                    <span className="flex-1 min-w-0 truncate text-[11px] text-ink-600 font-mono">
                      {shareLink}
                    </span>
                    <button
                      type="button"
                      onClick={handleCopyShareLink}
                      className="flex-none text-[11px] font-medium text-brand hover:text-brand-pressed transition-colors"
                    >
                      {linkCopied ? <Check className="h-4 w-4 text-status-done" /> : "Copy"}
                    </button>
                  </div>
                  <button
                    type="button"
                    onClick={() => void handleRevokeShare()}
                    className="flex items-center gap-1.5 text-[11.5px] text-ink-400 hover:text-status-failed transition-colors self-start"
                  >
                    <Trash2 className="h-3.5 w-3.5" /> Revoke link
                  </button>
                </>
              ) : (
                <p className="text-[11.5px] text-ink-500">
                  Share a public link to the deliverable only — not the chat or agent outputs.
                </p>
              )}
            </div>
          )}
        </div>
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
