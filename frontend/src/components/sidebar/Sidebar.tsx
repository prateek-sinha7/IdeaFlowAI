"use client";

import { useCallback, useEffect, useState } from "react";
import { motion } from "motion/react";
import {
  Plus,
  Search,
  Sparkles,
  LogOut,
  PanelLeftClose,
  FileText,
  Presentation,
  Layout,
  GitBranch,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Loader2,
  Clock,
} from "lucide-react";
import type { ChatSession, WorkflowRun, WorkflowStatus, WorkflowType } from "@/types/index";
import { getToken, getChats } from "@/lib/api";
// KAN-116 (Bug 3): safety net for titles stored in DB with === markers.
import { parseRunInput } from "@/lib/runInput";

interface SidebarProps {
  activeChatId?: string;
  onSelectChat?: (chatId: string) => void;
  onNewChat?: (chatSession: ChatSession) => void;
  onDeleteChat?: (chatId: string) => void;
  onLogout?: () => void;
  onCollapse?: () => void;
  chatTitleUpdate?: { chat_session_id: string; title: string } | null;
  onOpenWorkflow?: () => void;
  recentRuns?: WorkflowRun[];
  onSelectRun?: (run: WorkflowRun) => void;
}

const TYPE_CONFIG: Record<WorkflowType, { icon: typeof FileText; color: string; label: string }> = {
  user_stories: { icon: FileText, color: "text-blue-400", label: "User Stories" },
  user_stories_revision: { icon: FileText, color: "text-blue-400", label: "User Stories (revision)" },
  ppt: { icon: Presentation, color: "text-amber-400", label: "Presentation" },
  ppt_v2: { icon: Presentation, color: "text-amber-400", label: "Presentation (v2)" },
  ppt_revision: { icon: Presentation, color: "text-amber-400", label: "Presentation (revision)" },
  prototype: { icon: Layout, color: "text-emerald-400", label: "Prototype" },
  prototype_revision: { icon: Layout, color: "text-emerald-400", label: "Prototype (revision)" },
  prototype_large_revision: { icon: Layout, color: "text-emerald-400", label: "Prototype (large revision)" },
  prototype_feature_revision: { icon: Layout, color: "text-emerald-400", label: "Prototype (feature revision)" },
  app_builder: { icon: Layout, color: "text-orange-400", label: "App Builder" },
  app_builder_revision: { icon: Layout, color: "text-orange-400", label: "App Builder (revision)" },
  custom: { icon: Layout, color: "text-slate-400", label: "Custom" },
  migration: { icon: GitBranch, color: "text-teal-400", label: "Platform" },
  mulesoft_to_springboot: { icon: GitBranch, color: "text-teal-400", label: "Mulesoft → Spring Boot" },
  dotnet_to_azure: { icon: GitBranch, color: "text-indigo-400", label: ".NET → Azure" },
};

const STATUS_ICON: Record<WorkflowStatus, typeof Loader2> = {
  running: Loader2,
  completed: CheckCircle2,
  failed: XCircle,
  cancelled: XCircle,
  // Phase 16 (WR-01): "degraded" is a partial-failure terminal; "revising" is an
  // in-progress re-run. Map both so the sidebar status maps stay exhaustive.
  degraded: AlertTriangle,
  revising: Loader2,
  // Extended live statuses (FIX-156 WorkflowStatus expansion) — all in-progress.
  planning: Loader2,
  generating: Loader2,
  waiting_for_user: Loader2,
  clarifying: Loader2,
  analyzing: Loader2,
  // R-14 (014-conditional-gates): a terminal hand-off, not a failure — GitBranch
  // is already imported for the branching-workflow types above, reused here.
  diverted: GitBranch,
};

const STATUS_COLOR: Record<WorkflowStatus, string> = {
  running: "text-blue-400",
  completed: "text-green-400",
  failed: "text-red-400",
  cancelled: "text-amber-400",
  degraded: "text-amber-400",
  revising: "text-blue-400",
  // Extended live statuses — all shown as in-progress blue.
  planning: "text-amber-400",
  generating: "text-blue-400",
  waiting_for_user: "text-amber-400",
  clarifying: "text-amber-400",
  analyzing: "text-blue-400",
  diverted: "text-indigo-400",
};

/**
 * Sidebar component — workflow-first design.
 * Shows recent workflow runs as the primary history, with a "New Project" CTA.
 */
export function Sidebar({
  activeChatId,
  onSelectChat,
  onNewChat,
  onDeleteChat,
  onLogout,
  onCollapse,
  chatTitleUpdate,
  onOpenWorkflow,
  recentRuns = [],
  onSelectRun,
}: SidebarProps) {
  const [searchQuery, setSearchQuery] = useState("");

  // Filter runs by search query
  const filteredRuns = recentRuns.filter((run) =>
    (run.title || run.input || "")
      .toLowerCase()
      .includes(searchQuery.toLowerCase())
  );

  // Group runs by date
  const groupedRuns = groupByDate(filteredRuns);

  return (
    <div className="flex h-full flex-col backdrop-blur-sm" style={{ backgroundColor: "var(--theme-sidebar-bg)" }}>
      {/* Header with branding */}
      <div className="px-5 pt-5 pb-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-white/10 border border-white/10">
              <Sparkles className="h-3.5 w-3.5 text-white" />
            </div>
            <h1 className="text-sm font-semibold tracking-tight" style={{ color: "var(--theme-fg)" }}>
              VelocityAI
            </h1>
          </div>
          {onCollapse && (
            <button
              onClick={onCollapse}
              className="flex items-center justify-center rounded-md p-1 text-grey/60 hover:text-white hover:bg-white/5 transition-all duration-200"
              aria-label="Close sidebar"
            >
              <PanelLeftClose className="h-3.5 w-3.5" />
            </button>
          )}
        </div>

        {/* New Project button */}
        <div className="space-y-1.5">
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={onOpenWorkflow}
            className="w-full flex items-center justify-center gap-1.5 rounded-md bg-gradient-to-r from-blue-500/15 to-purple-500/15 border border-blue-500/20 px-3 py-2 text-[11px] font-semibold text-white transition-all duration-200 hover:from-blue-500/25 hover:to-purple-500/25 hover:border-blue-400/40"
          >
            <Plus className="h-3 w-3" />
            New Project
          </motion.button>
        </div>
      </div>

      {/* Divider */}
      <div className="mx-5 border-t border-grey/15" />

      {/* Search input */}
      <div className="px-5 py-2.5">
        <div className="flex items-center gap-1.5 rounded-md border border-grey/15 px-2.5 py-1.5" style={{ backgroundColor: "var(--theme-input-bg)" }}>
          <Search className="h-3 w-3 text-grey/50" />
          <input
            type="text"
            aria-label="Search projects"
            name="sidebar-search"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search projects..."
            className="flex-1 bg-transparent text-[11px] text-white placeholder-grey/40 focus:outline-none"
          />
        </div>
      </div>

      {/* Workflow run history */}
      <div className="flex-1 overflow-y-auto px-3 pb-4">
        {recentRuns.length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/5 border border-white/10 mb-3">
              <Clock className="h-5 w-5 text-grey/40" />
            </div>
            <p className="text-xs text-grey/50 mb-1">No projects yet</p>
            <p className="text-[10px] text-grey/35">Start a workflow to see your history here</p>
          </div>
        )}

        {Object.entries(groupedRuns).map(([group, runs]) => (
          <div key={group} className="mb-4">
            <p className="text-[9px] uppercase tracking-wider text-grey/40 font-medium px-2 mb-1.5">
              {group}
            </p>
            <div className="space-y-1">
              {runs.map((run) => {
                const typeConf = TYPE_CONFIG[run.type];
                const TypeIcon = typeConf.icon;
                const StatusIcon = STATUS_ICON[run.status];
                const statusColor = STATUS_COLOR[run.status];

                return (
                  <motion.button
                    key={run.id}
                    whileHover={{ x: 2 }}
                    onClick={() => onSelectRun?.(run)}
                    className="w-full flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-left hover:bg-white/[0.04] transition-all group"
                  >
                    <div className="flex h-7 w-7 items-center justify-center rounded-md bg-white/5 flex-shrink-0">
                      <TypeIcon className={`h-3.5 w-3.5 ${typeConf.color}`} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-[11px] font-medium text-white/80 group-hover:text-white transition-colors">
                        {(() => {
                          const raw = run.title || run.input.slice(0, 40);
                          if (!raw.includes("===")) return raw;
                          const p = parseRunInput(raw);
                          return (p.revisionInstruction ?? p.brief ?? raw).split("\n")[0].trim() || raw;
                        })()}
                      </p>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        <StatusIcon className={`h-2.5 w-2.5 ${statusColor} ${run.status === "running" ? "animate-spin" : ""}`} />
                        <span className="text-[9px] text-grey/45">
                          {typeConf.label}
                          {run.duration ? ` • ${run.duration}s` : ""}
                        </span>
                      </div>
                    </div>
                  </motion.button>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* User section with logout */}
      {onLogout && (
        <div className="border-t border-grey/15 px-5 py-2 mb-1">
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={onLogout}
            className="w-full flex items-center justify-center gap-1.5 rounded-md border border-red-500/20 bg-red-500/10 px-2 py-1.5 text-[11px] font-medium text-red-300 hover:bg-red-500/20 hover:text-red-200 hover:border-red-500/30 transition-all duration-200"
          >
            <LogOut className="h-3 w-3" />
            Log out
          </motion.button>
        </div>
      )}
    </div>
  );
}

function groupByDate(runs: WorkflowRun[]): Record<string, WorkflowRun[]> {
  const groups: Record<string, WorkflowRun[]> = {};
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 86400000);
  const weekAgo = new Date(today.getTime() - 7 * 86400000);

  for (const run of runs) {
    const date = new Date(run.createdAt);
    let group: string;

    if (date >= today) {
      group = "Today";
    } else if (date >= yesterday) {
      group = "Yesterday";
    } else if (date >= weekAgo) {
      group = "This Week";
    } else {
      group = "Earlier";
    }

    if (!groups[group]) groups[group] = [];
    groups[group].push(run);
  }

  return groups;
}
