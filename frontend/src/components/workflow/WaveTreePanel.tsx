"use client";

/**
 * WaveTreePanel — surfaces the live wave/subagent tree from the run stream
 * (Phase 12 / §22 / API-03; clears the 08-08 D-11 sibling-panel deferral).
 *
 * Consumes the ADDITIVE `wave_started` / `wave_completed` / `wave_failed` /
 * `subagent_spawned` / `subagent_result` WS events (Phase 12 — additive only;
 * no existing event renamed/removed) and renders the wave groups (index + task
 * ids + status badge) with their worker leaves (agent + status badge). Lifecycle
 * statuses ONLY — there is no live worker token stream (D-14).
 *
 * Like `ValidatorIssuePanel` / `AgentProgressPanel`, it is fed the assembled tree
 * as a prop (the parent's WS handler routes the `wave_*` / `subagent_*` events
 * into the `waves` list and dedupes them by `event_id`) — the same props-driven,
 * pure-render shape, so the panel stays decoupled from the WS plumbing (the
 * 08-08 decoupling). It does NOT change any existing panel; a workflow that
 * declares no waves feeds an empty `waves` list and the tree renders empty.
 */

import { Layers, GitBranch, CheckCircle2, Loader2, XCircle, Circle } from "lucide-react";
import type { WaveGroup } from "@/types/index";

export interface WaveTreePanelProps {
  /**
   * Wave groups assembled from the live `wave_*` / `subagent_*` lifecycle
   * events (deduped by `event_id` in the parent). Empty = no waves reported yet
   * (an existing non-wave workflow renders nothing).
   */
  waves: WaveGroup[];
}

/** Normalize a free-string lifecycle status into a render bucket. */
function statusKind(status: string): "running" | "completed" | "failed" | "pending" {
  const s = (status || "").toLowerCase();
  // IN-05 — a cancelled wave/worker is TERMINAL, not pending: render it in the
  // failed (terminal) bucket so it shows a terminal chip, not a grey pending one.
  if (s.includes("cancel")) return "failed";
  if (s.includes("fail") || s.includes("error")) return "failed";
  if (s.includes("complete") || s.includes("done") || s.includes("success")) return "completed";
  if (s.includes("run") || s.includes("spawn") || s.includes("progress") || s.includes("start")) {
    return "running";
  }
  return "pending";
}

const STATUS_STYLE: Record<
  ReturnType<typeof statusKind>,
  { chip: string }
> = {
  running: { chip: "text-blue-700 bg-blue-100" },
  completed: { chip: "text-emerald-700 bg-emerald-100" },
  failed: { chip: "text-red-700 bg-red-100" },
  pending: { chip: "text-gray-600 bg-gray-100" },
};

function StatusIcon({ status }: { status: string }) {
  const kind = statusKind(status);
  if (kind === "running") return <Loader2 className="h-3 w-3 flex-shrink-0 animate-spin" />;
  if (kind === "completed") return <CheckCircle2 className="h-3 w-3 flex-shrink-0" />;
  if (kind === "failed") return <XCircle className="h-3 w-3 flex-shrink-0" />;
  return <Circle className="h-3 w-3 flex-shrink-0" />;
}

function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLE[statusKind(status)];
  return (
    <span
      className={`inline-flex items-center gap-1 text-[8px] font-semibold uppercase tracking-widest px-1.5 py-0.5 rounded ${style.chip}`}
    >
      <StatusIcon status={status} />
      {status || "pending"}
    </span>
  );
}

export function WaveTreePanel({ waves }: WaveTreePanelProps) {
  // Render in wave order (stable by waveIndex) so the tree reads top-to-bottom.
  const ordered = [...waves].sort((a, b) => a.waveIndex - b.waveIndex);

  return (
    <div className="flex flex-col">
      <div className="flex items-center gap-1.5 mb-2">
        <Layers className="h-3.5 w-3.5 text-[#1B2A4A]" />
        <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-widest">
          Wave / Subagent Tree
        </p>
      </div>

      {ordered.length === 0 ? (
        <div className="flex items-center gap-1.5 text-[11px] text-gray-500 bg-gray-50 rounded-lg px-2.5 py-1.5">
          <Circle className="h-3 w-3 flex-shrink-0" />
          No waves running.
        </div>
      ) : (
        <div className="space-y-2.5 max-h-[260px] overflow-y-auto pr-1">
          {ordered.map((wave) => (
            <div
              key={`${wave.step ?? ""}:${wave.waveIndex}`}
              className="border border-gray-100 rounded-lg px-2.5 py-1.5 bg-white"
            >
              <div className="flex items-center justify-between gap-2 mb-1">
                <div className="flex items-center gap-1.5 min-w-0">
                  <GitBranch className="h-3 w-3 flex-shrink-0 text-[#1B2A4A]" />
                  <span className="text-[11px] font-semibold text-gray-800">
                    Wave {wave.waveIndex}
                  </span>
                  {wave.taskIds.length > 0 && (
                    <span className="text-[9px] text-gray-400 truncate">
                      {wave.taskIds.join(", ")}
                    </span>
                  )}
                </div>
                <StatusBadge status={wave.status} />
              </div>

              {wave.workers.length > 0 && (
                <div className="space-y-1 pl-4 border-l border-gray-100">
                  {wave.workers.map((worker, idx) => (
                    <div
                      key={`${wave.step ?? ""}:${wave.waveIndex}-${
                        worker.worker ?? `${worker.agent}-${idx}`
                      }`}
                      className="flex items-center justify-between gap-2"
                    >
                      <span className="text-[10px] text-gray-700 truncate min-w-0">
                        {worker.agent}
                      </span>
                      <StatusBadge status={worker.status} />
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
