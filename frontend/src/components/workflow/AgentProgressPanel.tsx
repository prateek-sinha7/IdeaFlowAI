"use client";

import { useRef, useState } from "react";
import { motion } from "motion/react";
import {
  CheckCircle2,
  Loader2,
  Circle,
  AlertCircle,
  RotateCcw,
  Send,
  Sparkles,
  Clock,
} from "lucide-react";
import type { AgentRunState, PipelineRunState, WorkflowType } from "@/types/index";

interface AgentProgressPanelProps {
  pipelineState: PipelineRunState;
  workflowType: WorkflowType;
  onViewResults?: () => void;
  onRunAnother?: () => void;
  onFollowUp?: (message: string) => void;
}

const STATUS_ICON = {
  idle: Circle,
  thinking: Loader2,
  running: Loader2,
  done: CheckCircle2,
  error: AlertCircle,
};

const STATUS_COLOR = {
  idle: "text-white/20",
  thinking: "text-blue-400",
  running: "text-blue-400",
  done: "text-green-400",
  error: "text-red-400",
};

/**
 * Left panel during pipeline execution.
 * Shows agent progress timeline, action buttons, and follow-up input.
 */
export function AgentProgressPanel({
  pipelineState,
  workflowType,
  onViewResults,
  onRunAnother,
  onFollowUp,
}: AgentProgressPanelProps) {
  const [followUpInput, setFollowUpInput] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const { agents, isRunning, completedCount, totalDuration } = pipelineState;
  const isComplete = !isRunning && agents.length > 0 && completedCount === agents.length;

  const handleSendFollowUp = () => {
    if (!followUpInput.trim()) return;
    onFollowUp?.(followUpInput.trim());
    setFollowUpInput("");
  };

  return (
    <div className="flex h-full flex-col" style={{ backgroundColor: "var(--theme-bg)" }}>
      {/* Header */}
      <div className="px-5 py-4 border-b border-white/8">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-white">
              {isRunning ? "Running Pipeline" : isComplete ? "Pipeline Complete" : "Agent Progress"}
            </h2>
            <p className="text-[11px] text-white/40 mt-0.5">
              {isRunning && `${completedCount}/${agents.length} agents completed`}
              {isComplete && totalDuration && `Finished in ${totalDuration.toFixed(1)}s`}
            </p>
          </div>
          {isRunning && (
            <div className="flex items-center gap-1.5 text-[10px] text-blue-400 bg-blue-500/10 rounded-full px-2.5 py-1">
              <Loader2 className="h-3 w-3 animate-spin" />
              Processing
            </div>
          )}
          {isComplete && (
            <div className="flex items-center gap-1.5 text-[10px] text-green-400 bg-green-500/10 rounded-full px-2.5 py-1">
              <CheckCircle2 className="h-3 w-3" />
              Done
            </div>
          )}
        </div>
      </div>

      {/* Agent Timeline */}
      <div className="flex-1 overflow-y-auto px-5 py-4">
        <div className="space-y-1">
          {agents.map((agent, idx) => {
            const StatusIcon = STATUS_ICON[agent.status];
            const statusColor = STATUS_COLOR[agent.status];
            const isActive = agent.status === "running" || agent.status === "thinking";

            return (
              <motion.div
                key={agent.id}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: idx * 0.02 }}
                className={`flex items-center gap-3 rounded-lg px-3 py-2.5 transition-all ${
                  isActive ? "bg-blue-500/5 border border-blue-500/20" : "border border-transparent"
                }`}
              >
                {/* Status icon */}
                <StatusIcon className={`h-4 w-4 flex-shrink-0 ${statusColor} ${isActive ? "animate-spin" : ""}`} />

                {/* Agent info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm">{agent.icon}</span>
                    <span className={`text-[12px] font-medium ${agent.status === "idle" ? "text-white/30" : "text-white/80"}`}>
                      {agent.name}
                    </span>
                  </div>
                  {isActive && agent.thinking && (
                    <p className="text-[10px] text-blue-300/60 mt-0.5 truncate ml-6">{agent.thinking}</p>
                  )}
                </div>

                {/* Duration */}
                {agent.duration !== null && (
                  <span className="text-[9px] text-white/25 flex items-center gap-0.5 flex-shrink-0">
                    <Clock className="h-2.5 w-2.5" />
                    {agent.duration.toFixed(1)}s
                  </span>
                )}
              </motion.div>
            );
          })}
        </div>
      </div>

      {/* Action Buttons (shown when complete) */}
      {isComplete && (
        <div className="px-5 py-3 border-t border-white/8 space-y-2">
          <button
            onClick={onViewResults}
            className="w-full flex items-center justify-center gap-2 rounded-xl bg-green-500/15 border border-green-500/25 text-green-300 px-4 py-2.5 text-xs font-medium hover:bg-green-500/25 transition-all"
          >
            <CheckCircle2 className="h-3.5 w-3.5" />
            View Results
          </button>
          <button
            onClick={onRunAnother}
            className="w-full flex items-center justify-center gap-2 rounded-xl bg-white/5 border border-white/10 text-white/60 px-4 py-2 text-xs font-medium hover:bg-white/10 hover:text-white transition-all"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            Run Another Pipeline
          </button>
        </div>
      )}

      {/* Follow-up Input */}
      <div className="px-4 py-3 border-t border-white/8">
        <div className="flex items-center gap-2">
          <div className="flex-1 flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.02] px-3 py-2.5 focus-within:border-white/20 transition-colors">
            <Sparkles className="h-3 w-3 text-white/30 flex-shrink-0" />
            <input
              ref={inputRef}
              type="text"
              value={followUpInput}
              onChange={(e) => setFollowUpInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleSendFollowUp(); }}
              placeholder="Steer agents or ask follow-up..."
              className="flex-1 bg-transparent text-[11px] text-white placeholder-white/30 focus:outline-none"
            />
          </div>
          <button
            onClick={handleSendFollowUp}
            disabled={!followUpInput.trim()}
            className="flex items-center justify-center rounded-xl bg-white text-black p-2.5 transition-all disabled:opacity-20 disabled:cursor-not-allowed"
          >
            <Send className="h-3 w-3" />
          </button>
        </div>
      </div>
    </div>
  );
}
