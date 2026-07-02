"use client";

// ─────────────────────────────────────────────────────────────────────────────
// Live version chip (B3 / POR §5 D5) — the in-preview "v{n} ▾" affordance.
// REUSE-FIRST per WORKSTREAM-B-UI-SPEC.md Surface 3: every visual node below
// inherits an existing analog (file:line cited inline). No net-new hex values,
// radii, font sizes, or motion curves — the toggle-pill, the dropdown/listbox,
// the amber read-only banner, the status dots and the pulse all already exist in
// this codebase and are copied here.
//
//   • chip pill              → PrototypePreview.tsx:529-539 (browser-chrome toggle pill)
//   • trailing chevron       → AgentThinkingTab.tsx:164 (ChevronDown)
//   • pulse on the pill      → AgentThinkingTab.tsx:123,163 (animate-pulse)
//   • older-version sub-dot  → PrototypePreview.tsx:538 (bg-amber-400)
//   • dropdown / listbox     → WorkflowHistory.tsx:925-944 + outside-click :961-963
//   • read-only amber banner → ReviewGatePanel.tsx:398-403 (bg-amber-50 …)
//   • status dot colours     → statusDotClass (RevisionFamilyView.tsx — inherited map)
//
// This presentational sibling mirrors B2's RevisionFamilyView.tsx: PreviewPanel
// owns the viewing-version state + the getWorkflow read-only fetch; this file
// owns only the chip / dropdown / banner pixels + keyboard wiring.
// ─────────────────────────────────────────────────────────────────────────────

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { ChevronDown, AlertTriangle } from "lucide-react";
import type { RunFamily, WorkflowStatus } from "@/types/index";
import { statusDotClass } from "@/components/history/RevisionFamilyView";

// ─── Relative-time helper (mirrors RevisionFamilyView.tsx:42-54 — a local copy so
// the dropdown rows show "3m ago" without importing from a component that would
// create a cycle). Pure formatting util, not an engine abstraction.
function formatRelativeTime(dateStr: string): string {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  const diff = Date.now() - d.getTime();
  const mins = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days < 7) return `${days}d ago`;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

// ─── LiveVersionChip — the "v{n} ▾" pill + version dropdown (UI-SPEC Surface 3).
// Renders nothing for a single-member (or absent) family — the same "hide when
// not a family" rule as the history version timeline.
export function LiveVersionChip({
  family,
  activeRunId,
  isViewingOlder,
  pulse,
  onSelectVersion,
  onBackToLatest,
}: {
  family: RunFamily | null;
  activeRunId: string | null;
  isViewingOlder: boolean;
  pulse: boolean;
  onSelectVersion: (memberId: string) => void;
  onBackToLatest: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [highlightIdx, setHighlightIdx] = useState(0);
  const chipRef = useRef<HTMLButtonElement | null>(null);
  // Per-option refs so the keyboard path can roving-focus the highlighted option
  // (mirrors VersionTimeline's chipRefs, RevisionFamilyView.tsx:392). Plain
  // <button> refs attach reliably (incl. under the tests' motion mock); a ref on
  // the motion.div listbox container would not.
  const optionRefs = useRef<(HTMLButtonElement | null)[]>([]);

  // Members ordered by revision_index ASC (v1..vN).
  const members = family
    ? [...family.members].sort((a, b) => a.revision_index - b.revision_index)
    : [];
  const activeIdx = members.findIndex((m) => m.id === activeRunId);

  // Keep the keyboard-highlighted option in sync with the active version when the
  // dropdown opens, and move keyboard focus INTO the listbox (onto the active
  // option) so Arrow/Enter/Escape are reachable. Focus only fires on open — the
  // active version only changes via select(), which closes the dropdown — so this
  // never steals focus on unrelated re-renders (mirrors VersionTimeline's
  // "focus only after a user action" intent, RevisionFamilyView.tsx:394-411).
  useEffect(() => {
    if (open) {
      const idx = activeIdx >= 0 ? activeIdx : 0;
      setHighlightIdx(idx);
      optionRefs.current[idx]?.focus();
    }
  }, [open, activeIdx]);

  // Hide the chip when this is not a family (single-member / absent).
  if (!family || family.members.length < 2) return null;

  const close = () => {
    setOpen(false);
    chipRef.current?.focus();
  };

  const select = (memberId: string) => {
    onSelectVersion(memberId);
    setOpen(false);
    chipRef.current?.focus();
  };

  const handleListKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      e.preventDefault();
      close();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      // Compute the next index explicitly so roving tabIndex + focus + highlight
      // stay in lockstep (the focused option is the one the next keydown lands on).
      const next = Math.min(highlightIdx + 1, members.length - 1);
      setHighlightIdx(next);
      optionRefs.current[next]?.focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      const next = Math.max(highlightIdx - 1, 0);
      setHighlightIdx(next);
      optionRefs.current[next]?.focus();
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      const member = members[highlightIdx];
      if (member) select(member.id);
    }
  };

  const activeLabel = `v${activeIdx >= 0 ? activeIdx + 1 : members.length}`;

  return (
    <div className="relative">
      {/* Chip — cloned from the PrototypePreview toggle-pill (PrototypePreview.tsx:529-539). */}
      <button
        ref={chipRef}
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`Current version ${activeLabel}, choose version`}
        className={`flex h-6 items-center gap-1 rounded px-1.5 text-[10px] font-medium transition-colors ${
          open ? "bg-[#1B2A4A] text-white" : "text-gray-400 hover:bg-gray-100 hover:text-gray-700"
        } ${pulse ? "animate-pulse" : ""}`}
      >
        {activeLabel}
        {/* Older-version amber sub-dot (PrototypePreview.tsx:538). */}
        {isViewingOlder && (
          <span aria-hidden className="ml-0.5 h-1.5 w-1.5 rounded-full bg-amber-400" />
        )}
        <ChevronDown aria-hidden className={`h-3 w-3 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      <AnimatePresence>
        {open && (
          <>
            {/* Outside-click catcher (WorkflowHistory.tsx:961-963). */}
            <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
            {/* Dropdown / listbox (WorkflowHistory.tsx:925-944). */}
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: -4 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: -4 }}
              transition={{ duration: 0.1 }}
              role="listbox"
              aria-label="Workflow versions"
              onKeyDown={handleListKeyDown}
              className="absolute right-0 top-8 z-20 bg-white border border-gray-200 rounded-lg shadow-lg py-1 min-w-[120px]"
            >
              {members.map((member, i) => {
                const isActive = member.id === activeRunId;
                const isHighlighted = i === highlightIdx;
                return (
                  <button
                    key={member.id}
                    ref={(el) => { optionRefs.current[i] = el; }}
                    role="option"
                    aria-selected={isActive}
                    tabIndex={i === highlightIdx ? 0 : -1}
                    onMouseEnter={() => setHighlightIdx(i)}
                    onClick={() => select(member.id)}
                    className={`w-full flex items-center gap-2 px-3 py-1.5 text-[11px] transition-colors ${
                      isActive || isHighlighted ? "bg-gray-100 text-gray-900" : "text-gray-600 hover:bg-gray-50"
                    }`}
                  >
                    <span className="text-[9px] font-semibold px-1 rounded bg-gray-200 text-gray-500">
                      v{i + 1}
                    </span>
                    <span aria-hidden className={statusDotClass(member.status as WorkflowStatus)} />
                    <span className="text-[10px] text-gray-400 ml-auto">
                      {formatRelativeTime(member.created_at)}
                    </span>
                  </button>
                );
              })}
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}

// ─── ReadOnlyVersionBanner — the amber "Viewing v{k} (read-only)" strip shown
// under the PreviewPanel header while an older version is on screen. Cloned from
// the ReviewGatePanel amber notice (ReviewGatePanel.tsx:398-403).
export function ReadOnlyVersionBanner({
  versionNumber,
  onBackToLatest,
}: {
  versionNumber: number;
  onBackToLatest: () => void;
}) {
  return (
    <div
      role="status"
      className="flex items-center gap-2 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-[10px] text-amber-700"
    >
      <AlertTriangle aria-hidden className="h-3.5 w-3.5 text-amber-600 flex-shrink-0" />
      <span>Viewing v{versionNumber} (read-only)</span>
      <button
        onClick={onBackToLatest}
        className="ml-auto text-amber-700 font-medium hover:underline"
      >
        Back to latest →
      </button>
    </div>
  );
}
