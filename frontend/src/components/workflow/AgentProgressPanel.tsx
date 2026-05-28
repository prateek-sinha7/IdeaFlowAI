"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Loader2, RotateCcw, ArrowRight, Square, Sparkles, ChevronDown } from "lucide-react";
import type { AgentRunState, PipelineRunState, WorkflowType } from "@/types/index";
import { availableChainTargets } from "@/lib/workflowChaining";
import { TokenUsageSummary, AgentTokenPill } from "./TokenUsageSummary";

interface AgentProgressPanelProps {
  pipelineState: PipelineRunState;
  workflowType: WorkflowType;
  onViewResults?: () => void;
  onRunAnother?: () => void;
  onFollowUp?: (message: string) => void;
  onChainPipeline?: (type: WorkflowType) => void;
  completedPipelineTypes?: WorkflowType[];
  onCancelPipeline?: () => void;
}

const PIPELINE_LABELS: Record<string, string> = {
  user_stories: "User Stories",
  ppt: "Presentation",
  prototype: "Prototype",
  od_prototype: "Prototype",
  app_builder: "App Builder",
  custom: "Custom Workflow",
};

// Deterministic initials color per agent index — monochrome
const ICON_STYLES = [
  { bg: "#E8EDF5", text: "#1B2A4A" },
  { bg: "#F0EDE8", text: "#5C4A2A" },
  { bg: "#EAF0EA", text: "#2A5C2A" },
  { bg: "#F0E8EE", text: "#5C2A4A" },
  { bg: "#E8EEF0", text: "#2A4A5C" },
  { bg: "#F0EEE8", text: "#5C5A2A" },
];

function AgentCard({ agent, index }: { agent: AgentRunState; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const isActive = agent.status === "running" || agent.status === "thinking";
  const isDone = agent.status === "done";
  const isError = agent.status === "error";
  const isIdle = agent.status === "idle";
  const iconStyle = ICON_STYLES[index % ICON_STYLES.length];
  const initials = agent.name.split(" ").map(w => w[0]).slice(0, 2).join("").toUpperCase();
  const hasOutput = isDone && agent.output && agent.output.trim().length > 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={
        isActive
          ? {
              opacity: 1,
              y: 0,
              boxShadow: [
                "0 0 0 0 rgba(27, 42, 74, 0.18), 0 1px 3px rgba(15, 23, 42, 0.04)",
                "0 0 0 6px rgba(27, 42, 74, 0.00), 0 6px 18px -8px rgba(27, 42, 74, 0.35)",
                "0 0 0 0 rgba(27, 42, 74, 0.18), 0 1px 3px rgba(15, 23, 42, 0.04)",
              ],
            }
          : { opacity: 1, y: 0 }
      }
      transition={
        isActive
          ? { boxShadow: { duration: 1.6, repeat: Infinity, ease: "easeInOut" }, default: { delay: index * 0.04 } }
          : { delay: index * 0.04 }
      }
      className={`rounded-xl border transition-colors ${
        isActive
          ? "border-[#1B2A4A] bg-white"
          : isDone
          ? "border-gray-100 bg-white"
          : isError
          ? "border-red-100 bg-red-50"
          : "border-gray-100 bg-white/60"
      }`}
    >
      {/* Main card content — clickable to expand when done */}
      <div
        className={`px-4 py-3.5 ${hasOutput ? "cursor-pointer select-none" : ""}`}
        onClick={() => hasOutput && setExpanded(v => !v)}
        role={hasOutput ? "button" : undefined}
        aria-expanded={hasOutput ? expanded : undefined}
      >
        {/* Top row */}
        <div className="flex items-center gap-3 mb-2">
          {/* Icon */}
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 text-[11px] font-bold"
            style={{ background: isIdle ? "#F5F5F0" : iconStyle.bg, color: isIdle ? "#9CA3AF" : iconStyle.text }}
          >
            {initials}
          </div>

          {/* Name + badge */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between gap-2">
              <p className={`text-[12px] font-semibold leading-tight ${isIdle ? "text-gray-500" : "text-gray-900"}`}>
                {agent.name}
              </p>
              <div className="flex items-center gap-1.5 flex-shrink-0">
                {isDone && agent.duration != null && (
                  <span className="text-[9px] text-gray-400">{agent.duration.toFixed(0)}s</span>
                )}
                {isDone && (
                  <span className="text-[9px] font-bold text-emerald-700 bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 rounded">
                    DONE
                  </span>
                )}
                {isActive && (
                  <span className="relative inline-flex items-center gap-1 text-[9px] font-bold text-white bg-[#1B2A4A] px-1.5 py-0.5 rounded">
                    <span className="relative inline-flex h-1.5 w-1.5">
                      <span className="absolute inline-flex h-full w-full rounded-full bg-white/70 animate-ping" />
                      <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-white" />
                    </span>
                    RUNNING
                  </span>
                )}
                {isError && (
                  <span className="text-[9px] font-bold text-red-700 bg-red-50 border border-red-200 px-1.5 py-0.5 rounded">
                    ERROR
                  </span>
                )}
                {hasOutput && (
                  <ChevronDown className={`h-3 w-3 text-gray-400 transition-transform ${expanded ? "rotate-180" : ""}`} />
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Status line */}
        {isDone && (
          <div className="flex items-center justify-between mb-1.5">
            <p className="text-[11px] text-gray-500">
              {hasOutput ? "Click to view output" : "Completed successfully"}
            </p>
            <AgentTokenPill
              inputTokens={agent.inputTokens}
              outputTokens={agent.outputTokens}
              totalTokens={agent.totalTokens}
            />
          </div>
        )}
        {isActive && (
          <p className="text-[11px] text-gray-700 mb-1.5 flex items-center gap-1.5">
            <Loader2 className="h-3 w-3 animate-spin text-[#1B2A4A]" />
            {agent.thinking || "In progress..."}
          </p>
        )}
        {isError && agent.error && (
          <p className="text-[11px] text-red-600 mb-1.5">{agent.error}</p>
        )}

        {/* Role / subtitle */}
        <p className={`text-[9px] font-semibold uppercase tracking-wider ${isIdle ? "text-gray-400" : "text-gray-500"}`}>
          {agent.role}
        </p>
      </div>

      {/* Expanded output */}
      <AnimatePresence>
        {expanded && hasOutput && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="border-t border-gray-100 px-4 py-3">
              <pre className="text-[10px] text-gray-700 leading-relaxed whitespace-pre-wrap break-words max-h-64 overflow-y-auto font-mono">
                {agent.output}
              </pre>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

export function AgentProgressPanel({
  pipelineState,
  workflowType,
  onRunAnother,
  onFollowUp,
  onChainPipeline,
  completedPipelineTypes = [],
  onCancelPipeline,
}: AgentProgressPanelProps) {
  const [isCancelled, setIsCancelled] = useState(false);
  const { agents, isRunning, completedCount, totalDuration } = pipelineState;

  const handleCancel = () => { setIsCancelled(true); onCancelPipeline?.(); };
  const isComplete = !isRunning && agents.length > 0 && completedCount === agents.length;
  const hasErrors = agents.some((a) => a.status === "error");
  const availablePipelines = availableChainTargets(workflowType, completedPipelineTypes);
  const pipelineLabel = PIPELINE_LABELS[workflowType] || workflowType;
  const progress = agents.length > 0 ? (completedCount / agents.length) * 100 : 0;

  return (
    <div className="flex h-full flex-col bg-white">
      {/* Header */}
      <div className="px-5 pt-5 pb-4 border-b border-gray-100 flex-shrink-0">
        <div className="flex items-start justify-between gap-2 mb-3">
          <div className="flex-1 min-w-0">
            <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-widest mb-1">{pipelineLabel}</p>
            <p className="text-[13px] font-semibold text-gray-900 leading-tight">
              {isCancelled ? "Pipeline stopped" :
               isRunning ? `${completedCount} / ${agents.length} agents` :
               isComplete ? `Done in ${totalDuration?.toFixed(1)}s` :
               "Agent Progress"}
            </p>
          </div>
          {isRunning && !isCancelled && (
            <button
              onClick={handleCancel}
              className="flex items-center gap-1.5 text-[10px] font-medium text-gray-500 hover:text-gray-900 border border-gray-200 hover:border-gray-300 rounded-lg px-2.5 py-1.5 transition-all flex-shrink-0"
            >
              <Square className="h-3 w-3" /> Stop
            </button>
          )}
        </div>

        {/* Progress bar */}
        {agents.length > 0 && (
          <div className="h-0.5 bg-gray-100 rounded-full overflow-hidden">
            <motion.div
              className={`h-full rounded-full ${hasErrors ? "bg-red-400" : isCancelled ? "bg-gray-300" : "bg-[#1B2A4A]"}`}
              initial={{ width: 0 }}
              animate={{ width: `${progress}%` }}
              transition={{ duration: 0.4, ease: "easeOut" }}
            />
          </div>
        )}
      </div>

      {/* Agent cards — scrollable */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
        {agents.map((agent, idx) => (
          <AgentCard key={agent.id} agent={agent} index={idx} />
        ))}
      </div>

      {/* Suggested next steps + New Pipeline — pinned at bottom */}
      {(isComplete || isCancelled) && (
        <div className="flex-shrink-0 border-t border-gray-100 px-4 py-3 space-y-2">
          {/* Token usage summary — shown when pipeline completes */}
          {isComplete && (
            <TokenUsageSummary pipelineState={pipelineState} modelId={pipelineState.modelId} />
          )}
          {isComplete && availablePipelines.length > 0 && onChainPipeline && (
            <motion.div
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
              className="rounded-2xl border-2 border-[#1B2A4A]/15 bg-gradient-to-br from-[#FAFBFF] to-[#F1F4FB] p-3.5 shadow-sm"
            >
              <div className="flex items-center gap-1.5 mb-2.5">
                <Sparkles className="h-3.5 w-3.5 text-[#1B2A4A]" />
                <p className="text-[10px] font-bold text-[#1B2A4A] uppercase tracking-[0.12em]">
                  Suggested next steps
                </p>
              </div>
              <div className="space-y-1.5">
                {availablePipelines.map((pipeline, idx) => (
                  <motion.button
                    key={pipeline.type}
                    initial={{ opacity: 0, x: -4 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.15 + idx * 0.05 }}
                    onClick={() => onChainPipeline(pipeline.type)}
                    className="group w-full flex items-center justify-between rounded-xl border border-[#1B2A4A]/20 bg-white hover:border-[#1B2A4A] hover:bg-[#1B2A4A] hover:shadow-md px-3.5 py-2.5 text-left transition-all"
                  >
                    <div className="min-w-0">
                      <p className="text-[12px] font-semibold text-gray-900 group-hover:text-white transition-colors">
                        {pipeline.label}
                      </p>
                      <p className="text-[10px] text-gray-500 group-hover:text-white/80 transition-colors leading-snug">
                        {pipeline.description}
                      </p>
                    </div>
                    <ArrowRight className="h-3.5 w-3.5 text-[#1B2A4A] group-hover:text-white group-hover:translate-x-0.5 transition-all flex-shrink-0 ml-2" />
                  </motion.button>
                ))}
              </div>
            </motion.div>
          )}

          <button
            onClick={() => { setIsCancelled(false); onRunAnother?.(); }}
            className="w-full flex items-center justify-center gap-2 rounded-xl border border-gray-200 bg-white hover:bg-gray-50 px-4 py-2.5 text-[11px] font-medium text-gray-600 transition-all"
          >
            <RotateCcw className="h-3.5 w-3.5" /> New Pipeline
          </button>
        </div>
      )}
    </div>
  );
}
