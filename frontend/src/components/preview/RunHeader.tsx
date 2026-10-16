"use client";

/**
 * RunHeader — the run-screen RIGHT-column header row (Phase 39, RUNUI-06/07).
 *
 * Share button (Option B): opens a popover that mints a public /s/{token} link.
 * When `runId` is provided the button calls POST /api/runs/{id}/share, shows a
 * copy-able URL, and offers a Revoke action. `onShare` is still accepted for
 * API compatibility but is NOT currently invoked — the legacy clipboard-copy
 * fallback for runId-less reopens was never wired to the button.
 *
 * SC-001 / ND-D: status keys off the generic `RunLaneState` discriminator — never
 * a workflow name. Styling routes through the Phase-32 token layer.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Archive, Check, ChevronDown, Download, FileText, Link2, Loader2, Package, Pause, Trash2, Upload, Clock, X } from "lucide-react";

import type { RunLaneState } from "@/components/chat/RunChatLane";
import { getToken, postShareRun, deleteShareRun } from "@/lib/api";

/** `v1`, `v2`, …, `v10` → descending numeric order ("newest first"). A tag
 *  that doesn't fit the `vN` shape falls back to a reverse string compare
 *  rather than being dropped. */
function sortTagsNewestFirst(tags: string[]): string[] {
  return [...tags].sort((a, b) => {
    const na = Number(a.replace(/^v/i, ""));
    const nb = Number(b.replace(/^v/i, ""));
    if (!Number.isNaN(na) && !Number.isNaN(nb)) return nb - na;
    return b.localeCompare(a);
  });
}

// ─── VersionMenu — Phase 6 (task 8.5) → Phase U (task U1) ───────────────────
// The single version selector for the whole run: a chip + a dropdown of the
// git tags fetched from GET /api/runs/{id}/sandbox/refs by the caller (so it
// can also decide, alongside the status badge, whether a tag exists at all).
// Options: every tag newest first, with "Latest (live)" (selects null) above
// them only when the caller says it still means something — see showLatestLive.
// Selecting a tag never blocks and never touches the live run — it only
// changes what the caller reads at that ref (Requirement 19 AC2).
//
// QA-PS-058 — "Latest (live)" is the UNCOMMITTED working tree and nothing else.
// On a settled, fully tagged family it is the newest tag's own bytes offered a
// second time under a second name, so the caller drops it there; `neverCaptured`
// marks the one settled case where it is kept because there is no tag to select
// instead (ISS-697).
//
// When no tags exist yet the caller keeps today's static chip instead of
// mounting this component at all (Requirement 19 AC1).
function VersionMenu({
  tags,
  selectedRef,
  liveLabel,
  showLatestLive,
  neverCaptured,
  onSelectVersion,
}: {
  tags: string[];
  /** The tag currently pinned for read-only browsing, or null = live/latest. */
  selectedRef: string | null;
  /** Chip text while no tag is pinned, e.g. "v2", "v3 draft", "v1 · partial". */
  liveLabel: string;
  /** QA-PS-058 — whether the "Latest (live)" option is offered at all. */
  showLatestLive: boolean;
  /** QA-PS-058 — the live tree is SETTLED work that never got a tag (ISS-697),
   *  so the option is the only route to it and says so. */
  neverCaptured: boolean;
  onSelectVersion: (tag: string | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const [highlightIdx, setHighlightIdx] = useState(0);
  const menuRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const optionRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const sortedTags = useMemo(() => sortTagsNewestFirst(tags), [tags]);

  // Close on outside click.
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Keyboard contract (restored from the pre-24f11270 VersionMenu; the tag-driven
  // rewrite dropped it without saying so): opening moves focus INTO the listbox
  // onto the highlighted option, Arrow keys move it, Enter/Space selects, and
  // Escape closes and returns focus to the chip.
  useEffect(() => {
    if (open) optionRefs.current[highlightIdx]?.focus();
  }, [open, highlightIdx]);

  const chipText = selectedRef ? `Viewing ${selectedRef}` : liveLabel;
  // With "Latest (live)" dropped, nothing in the menu would be marked as the
  // current selection while browsing un-pinned — so the tag matching the chip's
  // own label (the version actually on screen) carries it instead. `liveLabel`
  // is the bare `vN` in exactly the states where the live entry is dropped.
  const markedRef = selectedRef ?? (showLatestLive ? null : liveLabel);
  // Every option in render order: `null` is "Latest (live)", then tags newest first.
  const entries: (string | null)[] = showLatestLive ? [null, ...sortedTags] : sortedTags;

  const openMenu = () => {
    const marked = entries.indexOf(markedRef);
    setHighlightIdx(marked >= 0 ? marked : 0);
    setOpen(true);
  };
  const closeMenu = () => {
    setOpen(false);
    buttonRef.current?.focus();
  };
  const select = (tag: string | null) => {
    onSelectVersion(tag);
    closeMenu();
  };
  const onListKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      e.preventDefault();
      closeMenu();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlightIdx((i) => Math.min(i + 1, entries.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightIdx((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      if (highlightIdx < entries.length) select(entries[highlightIdx]);
    }
  };

  return (
    // `relative` anchors the listbox below — without a positioned ancestor its
    // `absolute` box laid out against the nearest one further up the tree,
    // which put it far down the page instead of adjacent to the chip.
    <div className="relative inline-flex flex-col items-start gap-[3px]" ref={menuRef}>
      <button
        ref={buttonRef}
        type="button"
        onClick={() => (open ? setOpen(false) : openMenu())}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="inline-flex items-center gap-[9px] rounded-[10px] border border-line-control bg-surface-card px-3 py-2 cursor-pointer hover:border-line-faint hover:bg-surface-white"
      >
        <span aria-hidden className="h-[7px] w-[7px] rounded-full bg-brand" />
        <span className="font-sans text-[13px] font-semibold leading-none text-ink-900">
          {chipText}
        </span>
        <span className="font-serif text-[11px] text-ink-400">▾</span>
      </button>

      {open && (
        <div
          role="listbox"
          aria-label="Select a version"
          onKeyDown={onListKeyDown}
          className="absolute left-0 top-full z-50 mt-1 min-w-[160px] rounded-[12px] border border-line-border bg-surface-white shadow-xl py-1"
        >
          {showLatestLive && (
            <>
              <button
                ref={(el) => {
                  optionRefs.current[0] = el;
                }}
                type="button"
                role="option"
                aria-selected={markedRef === null}
                tabIndex={highlightIdx === 0 ? 0 : -1}
                onMouseEnter={() => setHighlightIdx(0)}
                onClick={() => select(null)}
                className={`w-full px-4 py-2 text-left font-sans text-[12.5px] hover:bg-surface-warm transition-colors ${
                  markedRef === null ? "font-semibold text-brand" : "text-ink-700"
                }`}
              >
                Latest (live)
              </button>
              {neverCaptured && (
                <p className="max-w-[220px] px-4 pb-2 font-sans text-[11px] leading-snug text-ink-400">
                  Never captured as a version — no tag to select instead.
                </p>
              )}
            </>
          )}
          {sortedTags.map((tag, i) => {
            const idx = showLatestLive ? i + 1 : i;
            return (
            <button
              key={tag}
              ref={(el) => {
                optionRefs.current[idx] = el;
              }}
              type="button"
              role="option"
              aria-selected={tag === markedRef}
              tabIndex={highlightIdx === idx ? 0 : -1}
              onMouseEnter={() => setHighlightIdx(idx)}
              onClick={() => select(tag)}
              className={`w-full px-4 py-2 text-left font-sans text-[12.5px] hover:bg-surface-warm transition-colors ${
                tag === markedRef ? "font-semibold text-brand" : "text-ink-700"
              }`}
            >
              {tag}
            </button>
            );
          })}
        </div>
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
  /** The active run id within the family — the Version menu's tag source. */
  activeRunId?: string | null;
  /** The active version label, e.g. "v3" — the Version-button / chip text. */
  versionLabel?: string;
  /** The tag currently pinned for read-only browsing (a sandbox ref), or null/
   *  absent when viewing the live/latest tree. Drives the chip text and which
   *  menu option is marked selected (task U1). */
  selectedRef?: string | null;
  /** Fired with a tag string to browse it read-only, or null for "Latest (live)". */
  onSelectVersion?: (tag: string | null) => void;
  /** QA-PS-058 — the NEWEST family member's git tag; `null` when it finished
   *  without one (ISS-697 — tag creation is best-effort), and ABSENT when the
   *  caller has no family data at all. Decides whether "Latest (live)" is a
   *  duplicate of the newest tag (dropped) or the only route to that content. */
  latestVersionTag?: string | null;
  /** QA-PS-058 — true while that newest member is still running, so the live
   *  tree is work in progress rather than a version that was never captured. */
  latestVersionInFlight?: boolean;
  /** Optional: the settled run's id — used to call POST /api/runs/{id}/share
   *  and mint a public link. When absent, falls back to the legacy onShare callback. */
  runId?: string;
  /** Client-only Share — copies the run deep link; disabled while running/failed. */
  onShare?: () => void;
  /** Primary deliverable download (settled only); disabled when nothing to download. */
  onDownload?: () => void;
  canDownload?: boolean;
  /**
   * Split-button variant: "backlog" renders a 3-option Zip/PDF/ZipWithPDF dropdown;
   * "default" (or absent) renders the existing single button unchanged.
   */
  downloadVariant?: "default" | "backlog";
  /** Backlog split-button primary action — workspace ZIP archive. Falls back to onDownload. */
  onDownloadZip?: () => void;
  /** Backlog split-button PDF action — Backlog.pdf. Falls back to onDownload. */
  onDownloadPdf?: () => void;
  /** Backlog split-button ZIP-with-PDFs action. Falls back to onDownload. */
  onDownloadZipWithPdf?: () => void;
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
  activeRunId = null,
  versionLabel,
  selectedRef = null,
  onSelectVersion,
  latestVersionTag,
  latestVersionInFlight = false,
  runId,
  onShare: _onShare,
  onDownload,
  canDownload = false,
  downloadVariant = "default",
  onDownloadZip,
  onDownloadPdf,
  onDownloadZipWithPdf,
  currentAgentName,
  buildStepIndex,
  buildStepTotal,
  clarifyCount,
}: RunHeaderProps) {
  const isFailed = failed || runState === "terminal";
  const isRunning = runState === "building" || runState === "clarify" || runState === "gate";
  const isSettled = !isFailed && !isRunning; // complete / idle-with-content

  // ── Version tags — fetched for EVERY run state (task U1), not settled-only,
  // so the menu can render "next to the status badge" while running/failed
  // too. Lives here (not inside VersionMenu) because the render branch below
  // needs to know hasTags before deciding whether to mount the menu at all.
  // Dynamic import (unchanged from the pre-U1 VersionMenu): a caller whose
  // @/lib/api test mock omits getRunSandboxRefs gets a swallowed rejection
  // here rather than a thrown, test-failing render-effect error.
  const [tags, setTags] = useState<string[]>([]);
  useEffect(() => {
    if (!activeRunId) { setTags([]); return; }
    let cancelled = false;
    import("@/lib/api").then(({ getToken, getRunSandboxRefs }) => {
      const token = getToken();
      if (!token) return;
      getRunSandboxRefs(token, activeRunId)
        .then((t) => { if (!cancelled) setTags(t); })
        .catch(() => { if (!cancelled) setTags([]); });
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [activeRunId]);
  const hasTags = tags.length > 0;
  // ── QA-PS-058 — the three states of "Latest (live)" ────────────────────────
  // It means the uncommitted working tree, so it is offered while a run in the
  // family is still writing to it, and when the newest version is NOT reachable
  // by tag — it never got one, or the sandbox's tag list no longer carries it
  // (ISS-697), leaving the live tree as the only route to that content, which
  // the menu then says out loud. On a settled, tagged family it is dropped: the
  // same bytes as the newest tag under a second name. With no family data at all
  // (`latestVersionTag` absent) it is kept — over-showing is recoverable,
  // hiding content is not.
  const latestReachableByTag = !!latestVersionTag && tags.includes(latestVersionTag);
  const inFlight = isRunning || latestVersionInFlight;
  const showLatestLive = inFlight || !latestReachableByTag;
  const neverCaptured = latestVersionTag !== undefined && !inFlight && !latestReachableByTag;
  // What the chip says while no tag is pinned — matches today's static chip
  // per run state so switching to the interactive menu changes nothing else.
  const liveLabel = `${versionLabel ?? "v1"}${!isSettled ? (isRunning ? " draft" : isFailed ? " · partial" : "") : ""}`;

  // ── Share popover state (Option B public link) ────────────────────────────
  const [sharePopoverOpen, setSharePopoverOpen] = useState(false);
  const [shareLoading, setShareLoading] = useState(false);
  const [shareLink, setShareLink] = useState<string | null>(null);
  const [shareError, setShareError] = useState<string | null>(null);
  const [linkCopied, setLinkCopied] = useState(false);
  const linkCopiedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  // ── Download split-button dropdown state (backlog variant only) ─────────────
  const [downloadMenuOpen, setDownloadMenuOpen] = useState(false);
  const downloadMenuRef = useRef<HTMLDivElement>(null);

  // Close the download dropdown on outside click — same pattern as Share popover.
  useEffect(() => {
    if (!downloadMenuOpen) return;
    const handler = (e: MouseEvent) => {
      if (downloadMenuRef.current && !downloadMenuRef.current.contains(e.target as Node)) {
        setDownloadMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [downloadMenuOpen]);

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
      {/* Version affordance — ONE selector for the whole run (task U1). Once the
          run has ≥1 tag, the interactive VersionMenu shows in EVERY state
          (running/failed/settled) NEXT TO the status badge below, never
          replacing it. With no tags yet, every state keeps today's static,
          non-interactive chip. */}
      {!hasTags && versionLabel && (
        <span className="tabular-nums rounded-[8px] border border-line-control bg-surface-card px-2.5 py-[7px] font-serif text-[11.5px] font-normal leading-none text-ink-300">
          {liveLabel}
        </span>
      )}

      {hasTags && (
        <VersionMenu
          tags={tags}
          selectedRef={selectedRef}
          liveLabel={liveLabel}
          showLatestLive={showLatestLive}
          neverCaptured={neverCaptured}
          onSelectVersion={onSelectVersion ?? (() => {})}
        />
      )}

      {!isSettled && (
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

      {/* Download — settled state only (Phase 6).
          "backlog" downloadVariant: split-button with Zip / PDF / Zip-with-PDF options.
          "default" (all other workflows): the original single button, byte-for-byte unchanged. */}
      {isSettled && downloadVariant === "backlog" && (
        <div className="relative inline-flex flex-col items-end gap-[3px]" ref={downloadMenuRef}>
          {/* Split button row */}
          <div className="inline-flex">
            {/* Left segment — primary "Zip" action */}
            <button
              type="button"
              onClick={() => canDownload && (onDownloadZip ?? onDownload)?.()}
              disabled={!canDownload}
              aria-label="Download workspace ZIP"
              className={`inline-flex items-center gap-2 rounded-l-[10px] rounded-r-none border-none px-[15px] py-2 font-sans text-[13px] font-semibold text-white transition-colors ${
                canDownload ? "cursor-pointer bg-brand hover:bg-brand-pressed" : "cursor-not-allowed bg-brand/50"
              }`}
            >
              <Download aria-hidden className="h-[15px] w-[15px]" strokeWidth={1.9} />
              Zip
            </button>
            {/* Vertical divider */}
            <span aria-hidden className={`self-stretch w-px ${canDownload ? "bg-white/30" : "bg-white/15"}`} />
            {/* Right segment — chevron toggle */}
            <button
              type="button"
              onClick={() => canDownload && setDownloadMenuOpen((o) => !o)}
              disabled={!canDownload}
              aria-haspopup="menu"
              aria-expanded={downloadMenuOpen}
              aria-label="More download options"
              className={`inline-flex items-center justify-center rounded-l-none rounded-r-[10px] border-none px-2 py-2 font-sans text-[13px] font-semibold text-white transition-colors ${
                canDownload ? "cursor-pointer bg-brand hover:bg-brand-pressed" : "cursor-not-allowed bg-brand/50"
              }`}
            >
              <ChevronDown aria-hidden className="h-[14px] w-[14px]" strokeWidth={2} />
            </button>
          </div>

          {/* Dropdown menu */}
          {downloadMenuOpen && canDownload && (
            <div
              role="menu"
              aria-label="Download options"
              onKeyDown={(e) => { if (e.key === "Escape") { e.preventDefault(); setDownloadMenuOpen(false); } }}
              className="absolute right-0 top-full z-50 mt-1 min-w-[220px] rounded-[12px] border border-line-border bg-surface-white shadow-xl py-1"
            >
              {/* Option 1 — Zip */}
              <button
                type="button"
                role="menuitem"
                aria-label="Download workspace ZIP archive"
                onClick={() => { (onDownloadZip ?? onDownload)?.(); setDownloadMenuOpen(false); }}
                className="flex w-full items-center gap-3 px-4 py-2.5 text-left font-sans text-[12.5px] text-ink-700 hover:bg-surface-warm transition-colors"
              >
                <Archive aria-hidden className="h-[14px] w-[14px] flex-none text-ink-400" strokeWidth={1.8} />
                Zip
              </button>

              {/* Option 2 — PDF */}
              <button
                type="button"
                role="menuitem"
                aria-label="Download Backlog as PDF"
                onClick={() => {
                  // TODO: dedicated Backlog.pdf endpoint
                  (onDownloadPdf ?? onDownload)?.();
                  setDownloadMenuOpen(false);
                }}
                className="flex w-full items-center gap-3 px-4 py-2.5 text-left font-sans text-[12.5px] text-ink-700 hover:bg-surface-warm transition-colors"
              >
                <FileText aria-hidden className="h-[14px] w-[14px] flex-none text-ink-400" strokeWidth={1.8} />
                PDF
              </button>

              {/* Option 3 — Zip with all docs as PDF */}
              <button
                type="button"
                role="menuitem"
                aria-label="Download ZIP with all documents as PDF"
                onClick={() => {
                  // TODO: server-side zip-with-pdfs endpoint
                  (onDownloadZipWithPdf ?? onDownload)?.();
                  setDownloadMenuOpen(false);
                }}
                className="flex w-full items-center gap-3 px-4 py-2.5 text-left font-sans text-[12.5px] text-ink-700 hover:bg-surface-warm transition-colors"
              >
                <Package aria-hidden className="h-[14px] w-[14px] flex-none text-ink-400" strokeWidth={1.8} />
                Zip with all docs as PDF
              </button>
            </div>
          )}
        </div>
      )}

      {isSettled && downloadVariant !== "backlog" && (
        <div className="inline-flex flex-col items-end gap-[3px]">
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
        </div>
      )}
    </div>
  );
}

export default RunHeader;
