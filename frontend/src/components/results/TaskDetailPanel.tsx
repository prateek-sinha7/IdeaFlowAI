"use client";

// ─────────────────────────────────────────────────────────────────────────────
// Phase 39 plan 02 (RUNUI-06/08) — TaskDetailPanel: the Steps tab's L3 view.
// A single construction task's detail — status node, "Task N · {title}",
// duration, a reasoning card (from the task's live summary), and the task's
// tool-call rows. Opened from an L2 construction task row and back-navigates to
// the agent detail. All values are LIVE (ND-D) — sourced from the construction
// data already threaded (protoCompletedTasks + the build agent's toolCalls);
// never the mock's fixed transcript. Token-reskinned (no gray-* palette).
// ─────────────────────────────────────────────────────────────────────────────

import { Check, ChevronLeft, ChevronRight } from "lucide-react";
import type { ToolCallEntry } from "@/types/index";
import { formatDuration } from "@/lib/runStats";

export type TaskDetailStatus = "done" | "running" | "pending";

export interface TaskDetailPanelProps {
  taskIndex: number;
  agentName: string;
  status: TaskDetailStatus;
  task?: { number: number; title: string; summary: string };
  duration?: number | null;
  toolCalls?: ToolCallEntry[];
  onBack: () => void;
}

export function TaskDetailPanel({
  taskIndex, agentName, status, task, duration, toolCalls, onBack,
}: TaskDetailPanelProps) {
  const n = task?.number ?? taskIndex + 1;
  const title = task?.title ?? `Task ${n}`;
  const summary = task?.summary ?? "";
  const tools = toolCalls ?? [];

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

        {/* reasoning (violet) */}
        {summary.trim().length > 0 && (
          <div className="rounded-[11px] border border-[#E4E0F5] bg-[#F4F2FB] px-3.5 py-3 mb-3.5">
            <p className="m-0 mb-1.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-[#5A4FC0] font-[Manrope]">Reasoning</p>
            <p className="m-0 text-[13px] leading-[1.6] text-[#4A4680] whitespace-pre-wrap">{summary}</p>
          </div>
        )}

        {/* tool calls */}
        {tools.length > 0 && (
          <>
            <p className="m-0 mb-2 text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-500 font-[Manrope]">Tool calls</p>
            <div className="space-y-1.5">
              {tools.map((tc, i) => (
                <div key={i} className="flex items-center gap-2.5 px-3 py-2 border border-line-faint-row bg-surface-white rounded-[9px]">
                  <span className="w-5 h-5 flex-none rounded-[5px] border border-line-control bg-surface-warm grid place-items-center">
                    <ChevronRight className="h-2.5 w-2.5 text-ink-500" />
                  </span>
                  <span className="text-[12.5px] font-medium text-ink-800 font-[Manrope]">{tc.tool}</span>
                  <span className="text-[11.5px] text-ink-300 flex-1 min-w-0 truncate">
                    {Object.entries(tc.args || {}).map(([k, v]) => `${k}: ${String(v).slice(0, 24)}`).join(", ") || "no args"}
                  </span>
                  <span className="text-[10.5px] font-mono text-ink-500 bg-surface-paper px-1.5 py-0.5 rounded flex-none">{tc.result != null ? "ok" : "…"}</span>
                </div>
              ))}
            </div>
          </>
        )}

        {tools.length === 0 && summary.trim().length === 0 && (
          <p className="m-0 text-[12px] text-ink-300">No further detail recorded for this task.</p>
        )}
      </div>
    </div>
  );
}
