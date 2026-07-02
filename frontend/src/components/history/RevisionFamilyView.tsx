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

import { motion, AnimatePresence } from "motion/react";
import {
  FileText, Presentation, Layout,
  ChevronRight, MoreHorizontal, Trash2,
} from "lucide-react";
import type { WorkflowRun, WorkflowStatus } from "@/types/index";

// ─── Display helpers (mirrors WorkflowHistory.tsx:87-120 — small presentational
// utilities copied so the family card renders the SAME row shape without a
// circular import back into WorkflowHistory). Not an engine abstraction; these
// are pure formatting helpers (INV-3 targets superseded logic, not view utils).
const TYPE_META: Record<string, { icon: typeof FileText; label: string }> = {
  user_stories: { icon: FileText, label: "User Stories" },
  user_stories_revision: { icon: FileText, label: "User Stories (Revised)" },
  ppt: { icon: Presentation, label: "Presentation" },
  ppt_revision: { icon: Presentation, label: "Presentation (Revised)" },
  od_ppt: { icon: Presentation, label: "Presentation" },
  od_ppt_revision: { icon: Presentation, label: "Presentation (Revised)" },
  prototype: { icon: Layout, label: "Prototype" },
  prototype_revision: { icon: Layout, label: "Prototype (Revised)" },
  od_prototype: { icon: Layout, label: "Prototype" },
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

function formatDuration(seconds?: number): string {
  if (!seconds) return "";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

// Normalize a run type to its base (od_prototype→prototype, od_ppt→ppt, strip
// _revision) — SHARED by both the family-count and the type-filter tabs. Same
// rule as WorkflowHistory.tsx:196-200 / :753-756 (SC-001: generic suffix, never
// a workflow-name branch).
export function baseWorkflowType(type: string): string {
  return type === "od_prototype" ? "prototype"
    : type === "od_ppt" ? "ppt"
    : type === "od_ppt_revision" ? "ppt"
    : type === "prototype_revision" ? "prototype"
    : type.replace("_revision", "");
}

// ─── statusDotClass — semantic status → dot color. INHERITED map (UI-SPEC §0
// "Semantic status colors" + Sidebar.tsx:66-73 + dot shape PrototypePreview.tsx:509,538).
// These are inherited semantic dots, NOT new literals.
export function statusDotClass(status: WorkflowStatus): string {
  const base = "w-1.5 h-1.5 rounded-full ";
  switch (status) {
    case "completed":
      return base + "bg-emerald-400";
    case "cancelled":
    case "degraded":
      return base + "bg-amber-400";
    case "failed":
      return base + "bg-gray-300";
    case "running":
    case "revising":
    default:
      return base + "bg-blue-400";
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

export function groupRunsByFamily(runs: WorkflowRun[]): FamilyGroup[] {
  const buckets = new Map<string, WorkflowRun[]>();
  for (const run of runs) {
    const key = run.rootRunId;
    const bucket = buckets.get(key);
    if (bucket) bucket.push(run);
    else buckets.set(key, [run]);
  }
  const groups: FamilyGroup[] = [];
  for (const [rootRunId, bucket] of buckets) {
    // v1..vN chronological by created_at ASC (POR §2 D2).
    const members = [...bucket].sort(
      (a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime(),
    );
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

// ─── StatusBadge — the pill from WorkflowHistory.tsx:902-918, extracted so both
// the single-member row and the multi-member root row render the SAME badge for
// their target member (the family's latest for a multi-member card).
function StatusBadge({ status }: { status: WorkflowStatus }) {
  if (status === "completed") {
    return (
      <span className="text-[9px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-100 px-2 py-0.5 rounded-full">
        Done
      </span>
    );
  }
  if (status === "cancelled") {
    return (
      <span className="text-[9px] font-semibold text-amber-700 bg-amber-50 border border-amber-100 px-2 py-0.5 rounded-full">
        Cancelled
      </span>
    );
  }
  if (status === "failed") {
    return (
      <span className="text-[9px] font-semibold text-gray-500 bg-gray-100 border border-gray-200 px-2 py-0.5 rounded-full">
        Failed
      </span>
    );
  }
  return (
    <span className="text-[9px] font-semibold text-gray-500 bg-gray-100 border border-gray-200 px-2 py-0.5 rounded-full">
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
  return (
    <div className="relative">
      <button
        onClick={(e) => onToggleMenu(runId, e)}
        className="flex items-center justify-center h-7 w-7 rounded-lg text-gray-300 hover:text-gray-600 hover:bg-gray-100 transition-colors opacity-0 group-hover:opacity-100"
      >
        <MoreHorizontal className="h-4 w-4" />
      </button>
      <AnimatePresence>
        {openMenuId === runId && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: -4 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -4 }}
            transition={{ duration: 0.1 }}
            className="absolute right-0 top-8 z-20 bg-white border border-gray-200 rounded-lg shadow-lg py-1 min-w-[120px]"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={(e) => onDeleteClick(runId, e)}
              className="w-full flex items-center gap-2 px-3 py-2 text-[11px] text-red-600 hover:bg-red-50 transition-colors"
            >
              <Trash2 className="h-3.5 w-3.5" /> Delete
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ─── FamilyGroupCard — one row per family root. Single-member families render the
// EXACT existing flat row (WorkflowHistory.tsx:871-951, zero regression);
// multi-member families add a "v{N}" pill + a chevron toggle that expands into
// chronological version rows.
export function FamilyGroupCard({
  group, index, expanded, onToggle, onSelectRun, openMenuId, onToggleMenu, onDeleteClick,
}: {
  group: FamilyGroup;
  index: number;
  expanded: boolean;
  onToggle: () => void;
  onSelectRun: (run: WorkflowRun) => void;
  openMenuId: string | null;
  onToggleMenu: (runId: string, e?: React.MouseEvent) => void;
  onDeleteClick: (runId: string, e?: React.MouseEvent) => void;
}) {
  const rootMeta = TYPE_META[group.root.type] || TYPE_META.custom;
  const RootIcon = rootMeta.icon;
  const isMulti = group.members.length >= 2;

  // ─── Single-member family: byte-identical to today's flat row (no pill, no
  // expander) — visually indistinguishable from today, delete included.
  if (!isMulti) {
    const run = group.root;
    return (
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: index * 0.02 }}
        onClick={() => onSelectRun(run)}
        className="flex items-center gap-4 px-6 py-4 cursor-pointer hover:bg-gray-50 transition-colors group"
      >
        <div className="w-9 h-9 rounded-xl bg-gray-100 flex items-center justify-center flex-shrink-0 group-hover:bg-gray-200 transition-colors">
          <RootIcon className="h-4 w-4 text-gray-500" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-[13px] font-semibold text-gray-900 leading-tight">{run.title}</p>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-[10px] text-gray-400">{rootMeta.label}</span>
            <span className="text-gray-200">·</span>
            <span className="text-[10px] text-gray-400">{formatDate(run.createdAt)}</span>
            {run.duration && (
              <>
                <span className="text-gray-200">·</span>
                <span className="text-[10px] text-gray-400">{formatDuration(run.duration)}</span>
              </>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <StatusBadge status={run.status} />
          <RowMenu runId={run.id} openMenuId={openMenuId} onToggleMenu={onToggleMenu} onDeleteClick={onDeleteClick} />
          <ChevronRight className="h-4 w-4 text-gray-300 group-hover:text-gray-500 transition-colors" />
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

  return (
    <div>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: index * 0.02 }}
        onClick={() => onSelectRun(latest)}
        className="flex items-center gap-4 px-6 py-4 cursor-pointer hover:bg-gray-50 transition-colors group"
      >
        <div className="w-9 h-9 rounded-xl bg-gray-100 flex items-center justify-center flex-shrink-0 group-hover:bg-gray-200 transition-colors">
          <RootIcon className="h-4 w-4 text-gray-500" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-[13px] font-semibold text-gray-900 leading-tight">{group.root.title}</p>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-[10px] text-gray-400">{rootMeta.label}</span>
            <span className="text-gray-200">·</span>
            <span className="text-[10px] text-gray-400">{formatDate(latest.createdAt)}</span>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {/* "v{N}" count pill — filter-count-pill class (WorkflowHistory.tsx:806). */}
          <span
            aria-label={`${versionCount} versions`}
            className="text-[9px] font-semibold px-1 rounded bg-gray-200 text-gray-500"
          >
            v{versionCount}
          </span>
          <StatusBadge status={latest.status} />
          <RowMenu runId={group.root.id} openMenuId={openMenuId} onToggleMenu={onToggleMenu} onDeleteClick={onDeleteClick} />
          {/* Chevron toggle — controlled-state rotate (NOT group-open, which only
              fires inside a native <details>). */}
          <button
            onClick={(e) => { e.stopPropagation(); onToggle(); }}
            aria-expanded={expanded}
            aria-label={expanded ? "Collapse versions" : "Show versions"}
            className="flex items-center justify-center h-7 w-7 rounded-lg text-gray-300 hover:text-gray-600 hover:bg-gray-100 transition-colors"
          >
            <ChevronRight className={`h-3.5 w-3.5 text-gray-400 transition-transform ${expanded ? "rotate-90" : ""}`} />
          </button>
        </div>
      </motion.div>

      {/* Expanded child rows — indented (pl-8, AgentThinkingTab.tsx:119) chronological
          version rows v1..vN, each clickable to open that version. */}
      {expanded && (
        <div className="divide-y divide-gray-50">
          {group.members.map((member, i) => {
            // n = 1-based index of the parent within the family (fallback: the
            // previous sibling if the parent is not present in the list).
            const parentIdx = group.members.findIndex((m) => m.id === member.parentRunId);
            const revisesN = (parentIdx >= 0 ? parentIdx : i - 1) + 1;
            return (
              <div
                key={member.id}
                onClick={() => onSelectRun(member)}
                className="flex items-center gap-3 pl-8 pr-6 py-2.5 cursor-pointer hover:bg-gray-50 transition-colors"
              >
                <span className="text-[9px] font-semibold px-1 rounded bg-gray-200 text-gray-500">
                  v{i + 1}
                </span>
                <span className={statusDotClass(member.status)} />
                <span className="text-[12px] text-gray-700 truncate">{member.title}</span>
                <span className="text-[10px] text-gray-400">{formatDate(member.createdAt)}</span>
                {member.parentRunId && (
                  <span className="text-[10px] text-gray-400">↳ revises v{revisesN}</span>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
