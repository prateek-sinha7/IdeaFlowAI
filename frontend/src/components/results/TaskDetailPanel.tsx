"use client";

// ─────────────────────────────────────────────────────────────────────────────
// Phase 39 plan 02 (RUNUI-06/08) — TaskDetailPanel: the Steps tab's L3 view.
// A single construction task's detail — status node, "Task N · {title}", the
// per-task duration (WHEN live data carries one), and a reasoning card (from the
// task's live summary). Opened from an L2 construction task row, back-navigating
// to the agent detail. All values are LIVE (ND-D) from the construction data
// (protoCompletedTasks).
//
// INTENDED DIVERGENCES vs the mock (audit 39-02, live-data limits — SC-001):
//   ND-N — per-task TOOL CALLS: the mock shows a per-task tool-call list, but our
//     live trace records tool calls at the AGENT level, not attributed to an
//     individual subagent task. Rendering the whole build agent's tools on every
//     task would be misleading, so the L3 tool-call list is OMITTED (never the
//     agent-wide tools). If per-task tool attribution ever lands on the wire, wire
//     it here.
//   ND-O — per-task DURATION: protoCompletedTasks carries {number,title,summary}
//     with no per-task duration, so the duration line is omitted unless a live
//     `duration` is supplied.
// Token-reskinned (no gray-* palette).
// ─────────────────────────────────────────────────────────────────────────────

import { Check, ChevronLeft } from "lucide-react";
import { formatDuration } from "@/lib/runStats";

export type TaskDetailStatus = "done" | "running" | "pending";

export interface TaskDetailPanelProps {
  taskIndex: number;
  agentName: string;
  status: TaskDetailStatus;
  task?: { number: number; title: string; summary: string };
  /** Per-task duration — rendered ONLY when live data supplies one (ND-O). */
  duration?: number | null;
  onBack: () => void;
}

export function TaskDetailPanel({
  taskIndex, agentName, status, task, duration, onBack,
}: TaskDetailPanelProps) {
  const n = task?.number ?? taskIndex + 1;
  const title = task?.title ?? `Task ${n}`;
  const summary = task?.summary ?? "";

  return (
    <div className="max-w-[860px] mx-auto">
      {/* Breadcrumb — {agent} / task detail */}
      <button
        onClick={onBack}
        className="inline-flex items-center gap-1.5 text-[12.5px] font-medium text-ink-500 hover:text-ink-900 transition-colors mb-4"
      >
        <ChevronLeft className="h-[15px] w-[15px]" />
        {agentName} <span className="text-line-faint">/</span> <span className="text-ink-900">task detail</span>
      </button>

      <div className="rounded-[14px] border border-line-border bg-surface-card px-5 py-4.5">
        {/* header */}
        <div className="flex items-center gap-3 mb-4">
          {status === "done" ? (
            <span className="w-[30px] h-[30px] flex-none rounded-lg bg-surface-near-black grid place-items-center"><Check className="h-[15px] w-[15px] text-white" /></span>
          ) : status === "running" ? (
            <span className="w-[30px] h-[30px] flex-none rounded-lg bg-brand-fill border-[1.5px] border-brand grid place-items-center"><span className="w-2 h-2 rounded-full bg-brand animate-pulse" /></span>
          ) : (
            <span className="w-[30px] h-[30px] flex-none rounded-lg border-[1.5px] border-line-control" />
          )}
          <div className="flex-1 min-w-0">
            <p className="m-0 mb-0.5 text-[14.5px] font-semibold text-ink-900 font-[Manrope]">Task {n} · {title}</p>
            {duration != null && <p className="m-0 text-[11.5px] text-ink-300 font-mono">{formatDuration(duration)}</p>}
          </div>
        </div>

        {/* reasoning (violet) — the task's live summary */}
        {summary.trim().length > 0 ? (
          <div className="rounded-[11px] border border-[#E4E0F5] bg-[#F4F2FB] px-3.5 py-3">
            <p className="m-0 mb-1.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-[#5A4FC0] font-[Manrope]">Reasoning</p>
            <p className="m-0 text-[13px] leading-[1.6] text-[#4A4680] whitespace-pre-wrap">{summary}</p>
          </div>
        ) : (
          <p className="m-0 text-[12px] text-ink-300">No further detail recorded for this task.</p>
        )}
      </div>
    </div>
  );
}
