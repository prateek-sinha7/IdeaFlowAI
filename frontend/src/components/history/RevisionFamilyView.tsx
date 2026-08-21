"use client";

// ─────────────────────────────────────────────────────────────────────────────
// Revision Families (B2 / POR §5 D3+D4) — history family grouping + detail
// version timeline. REUSE-FIRST per WORKSTREAM-B-UI-SPEC.md: every visual node
// below inherits an existing analog (file:line cited inline). No net-new hex
// values, radii, font sizes, or motion curves — the chips/pills/status-dots/
// cards/rows/cross-fade all already exist in this codebase and are copied here.
//
// This sibling module keeps the ~1000-line WorkflowHistory.tsx manageable: the
// grouping helper + the two presentational components + the preview shim live
// here; WorkflowHistory wires them into its list + detail views.
// ─────────────────────────────────────────────────────────────────────────────

import { useEffect, useRef } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  FileText, Presentation, Layout,
  ChevronRight, MoreHorizontal, Trash2, GitBranch, CornerUpLeft,
} from "lucide-react";
import type { WorkflowRun, WorkflowStatus, RunFamily } from "@/types/index";
import { parseRunInput } from "@/lib/runInput";
// INV-12: the run-stat formatters live once in @/lib/runStats — no local copy.
import { formatDuration, formatTokenCount } from "@/lib/runStats";

// ─── cleanDisplayTitle — KAN-116 (Bug 3) + FIX-130 + FIX-131 safety net.
// Strips === markers AND "Title: " prefix from polluted DB titles.
// SC-001: generic, no workflow-name branches.
function cleanDisplayTitle(
  title: string | null | undefined,
  fallback = "",
  runInput?: string | null,
): string {
  const stripTitlePrefix = (s: string) =>
    s.startsWith("Title: ") ? s.slice("Title: ".length).trim() : s;
  const extractFromInput = (input: string): string => {
    const parsed = parseRunInput(input);
    const raw = (parsed.revisionInstruction ?? parsed.brief ?? "").split("\n")[0].trim();
    return stripTitlePrefix(raw);
  };
  if (!title) return runInput ? (extractFromInput(runInput) || fallback) : fallback;
  if (!title.includes("===")) return stripTitlePrefix(title);
  if (title.trimStart().startsWith("===")) {
    return runInput ? (extractFromInput(runInput) || fallback) : fallback;
  }
  const fromTitle = extractFromInput(title);
  if (fromTitle) return fromTitle;
  return runInput ? (extractFromInput(runInput) || fallback) : fallback;
}

// ─── Display helpers (mirrors WorkflowHistory.tsx:87-120 — small presentational
// utilities copied so the family card renders the SAME row shape without a
// circular import back into WorkflowHistory). Not an engine abstraction; these
// are pure formatting helpers (INV-3 targets superseded logic, not view utils).
const TYPE_META: Record<string, { icon: typeof FileText; label: string }> = {
  user_stories: { icon: FileText, label: "User Stories" },
  user_stories_revision: { icon: FileText, label: "User Stories (Revised)" },
  ppt: { icon: Presentation, label: "Presentation" },
  ppt_revision: { icon: Presentation, label: "Presentation (Revised)" },
  prototype: { icon: Layout, label: "Prototype" },
  prototype_revision: { icon: Layout, label: "Prototype (Revised)" },
  app_builder: { icon: Layout, label: "App Builder" },
  app_builder_revision: { icon: Layout, label: "App Builder (Revised)" },
  custom: { icon: FileText, label: "Custom" },
};

function formatDate(dateStr: string): string {
  const d = new Date(dateStr);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  const mins = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days < 7) return `${days}d ago`;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

// Normalize a run type to its base (strip _revision) — SHARED by both the
// family-count and the type-filter tabs. Same rule as WorkflowHistory.tsx
// (SC-001: generic suffix, never a workflow-name branch).
export function baseWorkflowType(type: string): string {
  return type.replace("_revision", "");
}

// ─── statusDotClass — semantic status → dot color. INHERITED map (UI-SPEC §0
// "Semantic status colors" + Sidebar.tsx:66-73 + dot shape PrototypePreview.tsx:509,538).
// These are inherited semantic dots, NOT new literals.
export function statusDotClass(status: WorkflowStatus): string {
  const base = "w-1.5 h-1.5 rounded-full ";
  switch (status) {
    case "completed":
      return base + "bg-status-done";
    case "cancelled":
    case "degraded":
      return base + "bg-status-amber";
    case "failed":
      return base + "bg-status-queued";
    // R-14 (014-conditional-gates): "diverted" is a distinct terminal status,
    // never a failure/cancellation — reuses the existing brand token (the same
    // one the "vN" version pill already uses) rather than a new color.
    case "diverted":
      return base + "bg-brand";
    case "running":
    case "revising":
    default:
      return base + "bg-status-running";
  }
}

// ─── FamilyGroup — one revision family: its root, all present members (v1..vN
// chronological), and the latest member. Grouped client-side on the B1 rootRunId
// field (UI-SPEC Surface 1 Data; POR §2 D2 chronological index).
export interface FamilyGroup {
  rootRunId: string;
  root: WorkflowRun;
  members: WorkflowRun[];
  latest: WorkflowRun;
}

// ─── familyRootFor — R-20 (014-conditional-gates): `parent_run_id` is the SAME
// structural FK for both a revision (child revises parent) AND a cross-workflow
// divert (child is the newly-minted run a `trigger: workflow` outcome spawned,
// R-15). The two must never share a family/version-list — R-20 is explicit:
// "two linked run-history cards, not a stitched timeline". The disambiguator is
// R-14: a run only ever reaches `status === "diverted"` via a divert, never a
// revision — so walking up from `run`, a parent found with that status marks
// the DIVERT boundary, and `run` becomes its own family root from there down.
// Falls back to the backend-computed `rootRunId` the moment an ancestor isn't
// in the loaded page (same windowed-caveat degradation as before this change).
function familyRootFor(run: WorkflowRun, byId: Map<string, WorkflowRun>): string {
  let cur = run;
  while (cur.id !== cur.rootRunId) {
    const parent = cur.parentRunId ? byId.get(cur.parentRunId) : undefined;
    if (!parent) return cur.rootRunId;
    if (parent.status === "diverted") return cur.id;
    cur = parent;
  }
  return cur.id;
}

export function groupRunsByFamily(runs: WorkflowRun[]): FamilyGroup[] {
  const byId = new Map(runs.map((r) => [r.id, r]));
  const buckets = new Map<string, WorkflowRun[]>();
  for (const run of runs) {
    const key = familyRootFor(run, byId);
    const bucket = buckets.get(key);
    if (bucket) bucket.push(run);
    else buckets.set(key, [run]);
  }
  const groups: FamilyGroup[] = [];
  for (const [rootRunId, bucket] of buckets) {
    // v1..vN chronological by (created_at ASC, id ASC) — the SAME deterministic
    // tie-break the Workstream-A /family endpoint uses. Backend contract:
    // revision_index == created_at-ASC rank, tie-broken by id (the /family query
    // orders by created_at ASC, id ASC) → this list and the detail timeline / live
    // chip derive IDENTICAL member orderings (identical v-numbers) for all present
    // members. Windowed-count caveat: a family with members OUTSIDE the <=100-run
    // getWorkflows list window shows fewer versions in this list card than the
    // authoritative detail timeline (POR §11 / B2 W3), by design.
    const members = [...bucket].sort((a, b) => {
      const dt = new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime();
      if (dt !== 0) return dt;
      return a.id.localeCompare(b.id);
    });
    // root = the member whose id IS the rootRunId; else the earliest present
    // (legacy NULL-parent / a family whose root fell outside the fetch window).
    const root = members.find((m) => m.id === rootRunId) ?? members[0];
    const latest = members[members.length - 1];
    groups.push({ rootRunId, root, members, latest });
  }
  // Newest family first (by latest member) — preserves today's newest-first list
  // order → zero ordering regression.
  return groups.sort(
    (a, b) => new Date(b.latest.createdAt).getTime() - new Date(a.latest.createdAt).getTime(),
  );
}

// ─── DivertLink / buildDivertLinks — R-20 (014-conditional-gates, T38 HISTORICAL
// case). Reconstructed purely from persisted fields already on every fetched
// `WorkflowRun` row (`status`, `parentRunId`) — no fetch, no live event needed
// (contracts/sse-pipeline-diverted.md: "the event is a LIVE-only convenience,
// not the sole source of truth"). `status === "diverted"` is the sole,
// unambiguous signal (R-14: only a divert ever sets it), so it doubles as both
// directions of the link: the run WITH that status is the source; the run
// whose `parentRunId` points at it is the target.
//
// `stepId` (the manifest step the divert fired from) is sourced from the
// diverting run's persisted `diverted_at_step_id` column (T41 migration 0033 +
// engine write; T42 threads it through normalizeWorkflowRun as
// `WorkflowRun.divertedAtStepId`). Absent/null on legacy pre-migration rows —
// the card omits the ", step {step_id}" clause in that case rather than
// fabricating a value.
export interface DivertLink {
  direction: "source" | "target";
  other: WorkflowRun;
  stepId?: string;
}

export function buildDivertLinks(runs: WorkflowRun[]): Map<string, DivertLink> {
  const links = new Map<string, DivertLink>();
  for (const run of runs) {
    if (run.status !== "diverted") continue;
    const target = runs.find((r) => r.parentRunId === run.id);
    if (!target) continue; // target run outside the loaded page — degrade gracefully (no link)
    links.set(run.id, { direction: "source", other: target });
    links.set(target.id, { direction: "target", other: run, stepId: run.divertedAtStepId ?? undefined });
  }
  return links;
}

// ─── Today / Earlier / Older date buckets + tokens/duration sort (SHELL-02).
// A grouping/sort layer that sits OVER groupRunsByFamily, derived ENTIRELY from
// fields already on each list row — `root.created_at` for the bucket key,
// `latest.duration` / `latest.tokenUsage.total_tokens` for the sort key. No new
// fetch, no backend change (36-RESEARCH A2). Extended HERE (next to the family
// grouping) rather than inline in WorkflowHistory.
export type HistorySortKey = "recent" | "tokens" | "duration";
export type DateBucketLabel = "Today" | "Earlier" | "Older";

const BUCKET_ORDER: DateBucketLabel[] = ["Today", "Earlier", "Older"];

// Today = same local calendar day; Earlier = within the last 7 days; Older = beyond.
export function dateBucketOf(dateStr: string, now: Date = new Date()): DateBucketLabel {
  const t = new Date(dateStr).getTime();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  if (t >= startOfToday) return "Today";
  if (t >= startOfToday - 7 * 86_400_000) return "Earlier";
  return "Older";
}

// Representative metric for a family — the displayed/latest member (the card row
// renders the latest member's status/date), so the sort matches what is shown.
function groupTokens(g: FamilyGroup): number {
  return g.latest.tokenUsage?.total_tokens ?? 0;
}
function groupDuration(g: FamilyGroup): number {
  return g.latest.duration ?? 0;
}

export interface HistorySection {
  bucket: DateBucketLabel;
  groups: FamilyGroup[];
}

// Partition family groups into Today/Earlier/Older (keyed on root.created_at) and
// sort within each bucket by the chosen key. `recent` (default) = newest latest-
// member first — preserves today's newest-first order. Only non-empty buckets are
// returned, in Today → Earlier → Older order.
export function bucketAndSortFamilies(
  groups: FamilyGroup[],
  sortKey: HistorySortKey = "recent",
  now: Date = new Date(),
): HistorySection[] {
  const byBucket = new Map<DateBucketLabel, FamilyGroup[]>();
  for (const g of groups) {
    const bucket = dateBucketOf(g.root.createdAt, now);
    const arr = byBucket.get(bucket);
    if (arr) arr.push(g);
    else byBucket.set(bucket, [g]);
  }
  const cmp = (a: FamilyGroup, b: FamilyGroup): number => {
    if (sortKey === "tokens") {
      const d = groupTokens(b) - groupTokens(a);
      if (d !== 0) return d;
    } else if (sortKey === "duration") {
      const d = groupDuration(b) - groupDuration(a);
      if (d !== 0) return d;
    }
    // recent + deterministic tie-break: newest latest-member first, then rootRunId.
    const dt = new Date(b.latest.createdAt).getTime() - new Date(a.latest.createdAt).getTime();
    if (dt !== 0) return dt;
    return b.rootRunId.localeCompare(a.rootRunId);
  };
  const sections: HistorySection[] = [];
  for (const bucket of BUCKET_ORDER) {
    const arr = byBucket.get(bucket);
    if (arr && arr.length > 0) sections.push({ bucket, groups: [...arr].sort(cmp) });
  }
  return sections;
}

// ─── StatusBadge — the pill from WorkflowHistory.tsx:902-918, extracted so both
// the single-member row and the multi-member root row render the SAME badge for
// their target member (the family's latest for a multi-member card).
function StatusBadge({ status }: { status: WorkflowStatus }) {
  if (status === "completed") {
    return (
      <span className="text-[9px] font-semibold text-status-done bg-[var(--status-done-fill)] border border-[var(--status-done-border)] px-2 py-0.5 rounded-full">
        Done
      </span>
    );
  }
  if (status === "cancelled") {
    return (
      <span className="text-[9px] font-semibold text-status-amber bg-[var(--status-amber-fill)] border border-[var(--status-amber-border)] px-2 py-0.5 rounded-full">
        Cancelled
      </span>
    );
  }
  if (status === "failed") {
    return (
      <span className="text-[9px] font-semibold text-ink-500 bg-surface-warm border border-line-border px-2 py-0.5 rounded-full">
        Failed
      </span>
    );
  }
  // R-14/R-20 (014-conditional-gates): a diverted run completed its own steps
  // successfully and handed off to a new run — reads as a distinct, non-failure
  // terminal state. The "Diverted to X →" link itself renders separately (see
  // DivertBadge below); this pill is just the row's compact status token.
  if (status === "diverted") {
    return (
      <span className="text-[9px] font-semibold text-brand bg-brand-fill border border-line-border px-2 py-0.5 rounded-full">
        Diverted
      </span>
    );
  }
  return (
    <span className="text-[9px] font-semibold text-ink-500 bg-surface-warm border border-line-border px-2 py-0.5 rounded-full">
      Running
    </span>
  );
}

// ─── RowMenu — the overflow menu + Delete popover from WorkflowHistory.tsx:920-947.
// (W1 fix) The delete affordance is threaded through props because the source
// markup references WorkflowHistory-local openMenuId/handleDeleteClick — a verbatim
// clone would not compile AND dropping it would remove delete-from-history. The
// delete-confirm modal itself stays in WorkflowHistory; this only opens the menu
// + fires onDeleteClick.
function RowMenu({
  runId, openMenuId, onToggleMenu, onDeleteClick,
}: {
  runId: string;
  openMenuId: string | null;
  onToggleMenu: (runId: string, e?: React.MouseEvent) => void;
  onDeleteClick: (runId: string, e?: React.MouseEvent) => void;
}) {
  const isOpen = openMenuId === runId;
  return (
    <div
      className="relative"
      onKeyDown={(e) => {
        // a11y: Escape closes the open menu (toggling the same row closes it).
        if (e.key === "Escape" && isOpen) { e.stopPropagation(); onToggleMenu(runId); }
      }}
    >
      <button
        type="button"
        onClick={(e) => onToggleMenu(runId, e)}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-label="Run actions"
        className="flex items-center justify-center h-7 w-7 rounded-[var(--radius-button)] text-ink-300 hover:text-ink-900 hover:bg-surface-warm transition-colors"
      >
        <MoreHorizontal className="h-4 w-4" />
      </button>
      <AnimatePresence>
        {isOpen && (
          <motion.div
            role="menu"
            initial={{ opacity: 0, scale: 0.95, y: -4 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -4 }}
            transition={{ duration: 0.1 }}
            className="absolute right-0 top-8 z-20 bg-surface-white border border-line-border rounded-[var(--radius-menu)] shadow-[var(--elevation-menu)] py-1 min-w-[120px]"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              type="button"
              role="menuitem"
              onClick={(e) => onDeleteClick(runId, e)}
              className="w-full flex items-center gap-2 px-3 py-2 text-[11px] text-status-failed hover:bg-[var(--status-failed-fill)] transition-colors"
            >
              <Trash2 className="h-3.5 w-3.5" /> Delete
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ─── RowStats — the mock's right-aligned per-row token / elapsed column
// (Hexaware Workspace v2.dc.html History row :398 — `r.tok` over `r.ago`). Both
// values come from fields ALREADY on the list row (`tokenUsage.total_tokens`,
// `created_at`), so there is no extra fetch. ND-D: never fabricate — the token
// line is omitted when the run carries no usage datum (0 tokens), so a run with
// no metered usage shows only its relative time, never a fake "0" count.
function RowStats({ run }: { run: WorkflowRun }) {
  const tokens = run.tokenUsage?.total_tokens ?? 0;
  const ago = formatDate(run.createdAt);
  if (tokens <= 0 && !ago) return null;
  return (
    <div className="w-[64px] flex-none text-right">
      {tokens > 0 && (
        <p className="text-[11px] font-semibold text-ink-700 tabular-nums leading-none">
          {formatTokenCount(tokens)}
        </p>
      )}
      {ago && (
        <p className="text-[10px] text-ink-400 tabular-nums leading-none mt-0.5">{ago}</p>
      )}
    </div>
  );
}

// ─── DivertBadge — the "Diverted to X →" / "← Continued from X[, step S]"
// breadcrumb line (R-20, both the live and historical case render through this
// same presentational component — only the DivertLink's source differs). A
// nested, stopPropagation'd button so clicking it navigates to the OTHER run
// without also firing the row's own onClick (which opens THIS run). Reuses the
// row's existing secondary-text sizing + the brand accent already used by
// StatusBadge/statusDotClass above (no new color introduced).
function DivertBadge({ link, onSelectRun }: { link: DivertLink; onSelectRun: (run: WorkflowRun) => void }) {
  const otherMeta = TYPE_META[link.other.type] || TYPE_META.custom;
  const otherLabel = cleanDisplayTitle(link.other.title, otherMeta.label, link.other.input) || otherMeta.label;
  const Icon = link.direction === "source" ? GitBranch : CornerUpLeft;
  const text = link.direction === "source"
    ? `Diverted to ${otherLabel} →`
    : `← Continued from ${otherLabel}${link.stepId ? `, step ${link.stepId}` : ""}`;
  return (
    <button
      type="button"
      onClick={(e) => { e.stopPropagation(); onSelectRun(link.other); }}
      aria-label={link.direction === "source" ? `Diverted to ${otherLabel}, open triggered run` : `Continued from ${otherLabel}, open originating run`}
      className="mt-1 inline-flex items-center gap-1 text-[10px] font-medium text-brand hover:underline"
    >
      <Icon className="h-2.5 w-2.5 flex-shrink-0" />
      <span className="truncate">{text}</span>
    </button>
  );
}

// ─── FamilyGroupCard — one row per family root. Single-member families render the
// EXACT existing flat row (WorkflowHistory.tsx:871-951, zero regression);
// multi-member families add a "v{N}" pill + a chevron toggle that expands into
// chronological version rows.
export function FamilyGroupCard({
  group, index, expanded, onToggle, onSelectRun, openMenuId, onToggleMenu, onDeleteClick, divertLinks,
}: {
  group: FamilyGroup;
  index: number;
  expanded: boolean;
  onToggle: () => void;
  onSelectRun: (run: WorkflowRun) => void;
  openMenuId: string | null;
  onToggleMenu: (runId: string, e?: React.MouseEvent) => void;
  onDeleteClick: (runId: string, e?: React.MouseEvent) => void;
  // R-20 (014-conditional-gates, T38): id → DivertLink, built once per fetch by
  // buildDivertLinks. Optional so every OTHER call site (none exist today, but
  // future ones might) keeps compiling without threading it through.
  divertLinks?: Map<string, DivertLink>;
}) {
  const rootMeta = TYPE_META[group.root.type] || TYPE_META.custom;
  const RootIcon = rootMeta.icon;
  const isMulti = group.members.length >= 2;

  // ─── Single-member family: byte-identical to today's flat row (no pill, no
  // expander) — visually indistinguishable from today, delete included.
  if (!isMulti) {
    const run = group.root;
    const divertLink = divertLinks?.get(run.id);
    return (
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: index * 0.02 }}
        onClick={() => onSelectRun(run)}
        role="button"
        tabIndex={0}
        aria-label={`Open ${cleanDisplayTitle(run.title)}, ${run.status}`}
        onKeyDown={(e) => { if ((e.key === "Enter" || e.key === " ") && e.target === e.currentTarget) { e.preventDefault(); onSelectRun(run); } }}
        className="flex items-center gap-4 px-6 py-4 cursor-pointer hover:bg-surface-warm focus-visible:bg-surface-warm outline-none transition-colors group"
      >
        <div className="w-9 h-9 rounded-xl bg-surface-warm flex items-center justify-center flex-shrink-0 group-hover:bg-surface-warm transition-colors">
          <RootIcon className="h-4 w-4 text-ink-500" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-[13px] font-semibold text-ink-900 leading-tight">{cleanDisplayTitle(run.title, rootMeta.label, run.input)}</p>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-[10px] text-ink-400">{rootMeta.label}</span>
            {run.duration ? (
              <>
                <span className="text-ink-200">·</span>
                <span className="text-[10px] text-ink-400">{formatDuration(run.duration)}</span>
              </>
            ) : null}
          </div>
          {/* R-20: the diverted-run/triggered-run breadcrumb — two linked
              cards, not a merged timeline (spec.md §4.4). */}
          {divertLink && <DivertBadge link={divertLink} onSelectRun={onSelectRun} />}
        </div>
        <div className="flex items-center gap-3 flex-shrink-0">
          <RowStats run={run} />
          <StatusBadge status={run.status} />
          <RowMenu runId={run.id} openMenuId={openMenuId} onToggleMenu={onToggleMenu} onDeleteClick={onDeleteClick} />
        </div>
      </motion.div>
    );
  }

  // ─── Multi-member family: same row shape + a "v{N}" pill and a chevron toggle.
  const latest = group.latest;
  // (W3 fix) v{N} counts window-present members — a summary; the detail
  // VersionTimeline (from /family) is the authoritative full-family count. They
  // coincide for recent clustered families; a family with members beyond the
  // getWorkflows fetch window shows fewer here by design (POR §11 large-family
  // edge case).
  const versionCount = group.members.length;
  // R-20: defensive — a family's LATEST member could itself be a divert source
  // (e.g. v3 of a revised prototype fires a `route:`); familyRootFor already
  // keeps a divert TARGET out of this family entirely, so only the source
  // direction is reachable here.
  const divertLink = divertLinks?.get(latest.id);

  return (
    <div>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: index * 0.02 }}
        onClick={() => onSelectRun(latest)}
        role="button"
        tabIndex={0}
        aria-label={`Open ${cleanDisplayTitle(group.root.title)} (latest version), ${latest.status}`}
        onKeyDown={(e) => { if ((e.key === "Enter" || e.key === " ") && e.target === e.currentTarget) { e.preventDefault(); onSelectRun(latest); } }}
        className="flex items-center gap-4 px-6 py-4 cursor-pointer hover:bg-surface-warm focus-visible:bg-surface-warm outline-none transition-colors group"
      >
        <div className="w-9 h-9 rounded-xl bg-surface-warm flex items-center justify-center flex-shrink-0 group-hover:bg-surface-warm transition-colors">
          <RootIcon className="h-4 w-4 text-ink-500" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-[13px] font-semibold text-ink-900 leading-tight">{cleanDisplayTitle(group.root.title, rootMeta.label, group.root.input)}</p>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-[10px] text-ink-400">{rootMeta.label}</span>
            {latest.duration ? (
              <>
                <span className="text-ink-200">·</span>
                <span className="text-[10px] text-ink-400">{formatDuration(latest.duration)}</span>
              </>
            ) : null}
          </div>
          {divertLink && <DivertBadge link={divertLink} onSelectRun={onSelectRun} />}
        </div>
        <div className="flex items-center gap-3 flex-shrink-0">
          {/* Purple "v{N}" version pill = the expand toggle (mock History row :397:
              #ECEAFC fill / #3C2CDA text → bg-brand-fill / text-brand, chevron
              rotates open). Merges the former grey count-pill + separate chevron
              button into the single control the mock shows. The inner span keeps
              the "{N} versions" a11y label; the button keeps the toggle label. */}
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onToggle(); }}
            aria-expanded={expanded}
            aria-label={expanded ? "Collapse versions" : "Show versions"}
            className="inline-flex items-center gap-1 text-[10px] font-semibold text-brand bg-brand-fill px-2 py-1 rounded-md hover:opacity-80 transition-opacity"
          >
            <span aria-label={`${versionCount} versions`}>v{versionCount}</span>
            <ChevronRight className={`h-2.5 w-2.5 text-brand transition-transform ${expanded ? "rotate-90" : ""}`} />
          </button>
          <RowStats run={latest} />
          <StatusBadge status={latest.status} />
          <RowMenu runId={group.root.id} openMenuId={openMenuId} onToggleMenu={onToggleMenu} onDeleteClick={onDeleteClick} />
        </div>
      </motion.div>

      {/* Expanded child rows — indented (pl-8, AgentThinkingTab.tsx:119) chronological
          version rows v1..vN, each clickable to open that version. */}
      {expanded && (
        <div className="divide-y divide-line-faint">
          {group.members.map((member, i) => {
            // n = 1-based index of the parent within the family (fallback: the
            // previous sibling if the parent is not present in the list).
            const parentIdx = group.members.findIndex((m) => m.id === member.parentRunId);
            const revisesN = (parentIdx >= 0 ? parentIdx : i - 1) + 1;
            return (
              // Native <button> so each child version row is keyboard-focusable +
              // Enter/Space-activatable for free (FIX 2 / §8 a11y). Keeps the exact
              // row className + appends `w-full text-left` to reproduce the
              // full-width flex row — no visual change. The ROOT family-card rows
              // stay <div onClick> (audit-scoped out).
              // FIX-169: each member row gets its own RowMenu so individual
              // revisions can be deleted independently (previously only the root
              // card had a delete affordance). Row wraps in a flex div so the
              // RowMenu sits at the trailing edge without pushing the button wider.
              // NOTE: no opacity-hide on RowMenu — the hover-fade race makes the
              // dropdown disappear before the click lands (FIX-169 follow-up).
              <div
                key={member.id}
                className="flex items-center hover:bg-surface-warm transition-colors"
              >
                <button
                  type="button"
                  onClick={() => onSelectRun(member)}
                  aria-label={`Version ${i + 1}, ${member.status}`}
                  className="flex-1 text-left flex items-center gap-3 pl-8 pr-2 py-2.5 cursor-pointer min-w-0"
                >
                  <span className="text-[9px] font-semibold px-1 rounded bg-surface-warm text-ink-500 flex-shrink-0">
                    v{i + 1}
                  </span>
                  <span className={`${statusDotClass(member.status)} flex-shrink-0`} />
                  <span className="text-[12px] text-ink-700 truncate">{cleanDisplayTitle(member.title, rootMeta.label, member.input)}</span>
                  <span className="text-[10px] text-ink-400 flex-shrink-0">{formatDate(member.createdAt)}</span>
                  {member.parentRunId && (
                    <span className="text-[10px] text-ink-400 flex-shrink-0">↳ revises v{revisesN}</span>
                  )}
                </button>
                <div className="pr-4 flex-shrink-0">
                  <RowMenu
                    runId={member.id}
                    openMenuId={openMenuId}
                    onToggleMenu={onToggleMenu}
                    onDeleteClick={onDeleteClick}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ─── extractRevisionInstructionPreview — a PREVIEW-ONLY inline shim.
// Workstream C1 (INV-12): the marker extraction now DELEGATES to the single
// project-wide parser (lib/runInput). This shim keeps ONLY the preview
// formatting (first meaningful line, clamped to 60 chars) — no second parser.
export function extractRevisionInstructionPreview(input: string): string {
  if (!input) return "";
  const parsed = parseRunInput(input);
  const source = parsed.revisionInstruction ?? parsed.brief;
  for (const rawLine of source.split("\n")) {
    const line = rawLine.trim();
    if (!line) continue;
    return line.length > 60 ? line.slice(0, 60) + "…" : line;
  }
  return "";
}

// ─── VersionTimeline — the detail-view version chip row (UI-SPEC Surface 2).
// A keyboard-navigable radiogroup of version chips above the tab bar; clicking a
// chip loads that member into the same detail surface. Renders nothing for a
// single-member (or absent) family — the same "hide when not a family" rule as
// the list.
export function VersionTimeline({
  family, activeRunId, activeInput, onSelectVersion,
}: {
  family: RunFamily | null;
  activeRunId: string;
  activeInput: string;
  onSelectVersion: (memberId: string) => void;
}) {
  const chipRefs = useRef<(HTMLButtonElement | null)[]>([]);
  // Managed focus: only steal focus after a USER-initiated switch, never on the
  // initial mount (so opening a run does not yank focus to the chip row).
  const userSwitched = useRef(false);

  // Members ordered by revision_index ASC (v1..vN).
  const members = family
    ? [...family.members].sort((a, b) => a.revision_index - b.revision_index)
    : [];
  const currentIdx = members.findIndex((m) => m.id === activeRunId);

  useEffect(() => {
    if (userSwitched.current) {
      const idx = members.findIndex((m) => m.id === activeRunId);
      if (idx >= 0) chipRefs.current[idx]?.focus();
      userSwitched.current = false;
    }
    // Only re-run when the active version changes (post-switch focus move).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeRunId]);

  // Hide the chip row when this is not a family (single-member / absent).
  if (!family || family.members.length < 2) return null;

  const select = (memberId: string) => {
    userSwitched.current = true;
    onSelectVersion(memberId);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (currentIdx < 0) return;
    if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
      e.preventDefault();
      if (currentIdx > 0) select(members[currentIdx - 1].id);
    } else if (e.key === "ArrowRight" || e.key === "ArrowDown") {
      e.preventDefault();
      if (currentIdx < members.length - 1) select(members[currentIdx + 1].id);
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      select(members[currentIdx].id);
    }
  };

  const activeMember = members.find((m) => m.id === activeRunId);
  const instructionPreview = extractRevisionInstructionPreview(activeInput);

  return (
    <div className="border-b border-line-divider bg-surface-white flex-shrink-0">
      {/* Chips row (mirrors the tab-bar container WorkflowHistory.tsx:574). */}
      <div
        role="radiogroup"
        aria-label="Workflow versions"
        onKeyDown={handleKeyDown}
        className="flex items-center gap-1 px-5 py-2"
      >
        {members.map((member, i) => {
          const isActive = member.id === activeRunId;
          return (
            <button
              key={member.id}
              ref={(el) => { chipRefs.current[i] = el; }}
              role="radio"
              aria-checked={isActive}
              aria-label={`Version ${i + 1}${member.parent_run_id ? `, revises version ${i}` : ""}, ${member.status}`}
              tabIndex={isActive ? 0 : -1}
              onClick={() => select(member.id)}
              className={`flex items-center gap-1.5 text-[11px] font-medium px-3 py-1.5 rounded-md transition-colors ${
                isActive
                  ? "bg-brand text-white"
                  : "text-ink-500 hover:text-ink-700 hover:bg-surface-warm"
              }`}
            >
              <span aria-hidden className={statusDotClass(member.status as WorkflowStatus)} />
              v{i + 1}
            </button>
          );
        })}
      </div>
      {/* Context line — only for a revision member (non-null parent). The quoted
          instruction suffix renders ONLY when a preview exists, so an empty input
          never yields dangling `— ''` quotes. */}
      {activeMember && activeMember.parent_run_id && (
        <p className="px-5 pb-2 text-[10px] text-ink-400 truncate">
          ↳ revises v{currentIdx}
          {instructionPreview ? <> — &lsquo;{instructionPreview}&rsquo;</> : null}
        </p>
      )}
    </div>
  );
}
