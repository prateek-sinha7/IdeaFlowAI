"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { CheckCircle2, Loader2, AlertCircle, RotateCcw, FileText, Presentation, Layout, ArrowRight, Square } from "lucide-react";
import type { AgentRunState, PipelineRunState, WorkflowType } from "@/types/index";

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

const PIPELINE_OPTIONS: { type: WorkflowType; label: string; description: string }[] = [
  { type: "ppt", label: "Presentation", description: "Turn results into slides" },
  { type: "user_stories", label: "User Stories", description: "Generate product backlog" },
  { type: "prototype", label: "Prototype", description: "Build interactive UI" },
];

const PIPELINE_LABELS: Record<string, string> = {
  user_stories: "User Stories",
  ppt: "Presentation",
  prototype: "Prototype",
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
  const isActive = agent.status === "running" || agent.status === "thinking";
  const isDone = agent.status === "done";
  const isError = agent.status === "error";
  const isIdle = agent.status === "idle";
  const iconStyle = ICON_STYLES[index % ICON_STYLES.length];
  const initials = agent.name.split(" ").map(w => w[0]).slice(0, 2).join("").toUpperCase();

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.04 }}
      className={`rounded-xl border px-4 py-3.5 transition-all ${
        isActive
          ? "border-gray-200 bg-white shadow-sm"
          : isDone
          ? "border-gray-100 bg-white"
          : isError
          ? "border-red-100 bg-red-50"
          : "border-gray-100 bg-white/60"
      }`}
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
            <p className={`text-[12px] font-semibold leading-tight ${isIdle ? "text-gray-400" : "text-gray-900"}`}>
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
                <span className="text-[9px] font-bold text-amber-700 bg-amber-50 border border-amber-200 px-1.5 py-0.5 rounded animate-pulse">
                  RUNNING
                </span>
              )}
              {isError && (
                <span className="text-[9px] font-bold text-red-700 bg-red-50 border border-red-200 px-1.5 py-0.5 rounded">
                  ERROR
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Status line */}
      {isDone && (
        <p className="text-[11px] text-gray-500 mb-1.5">Completed successfully</p>
      )}
      {isActive && (
        <p className="text-[11px] text-gray-500 mb-1.5 flex items-center gap-1.5">
          <Loader2 className="h-3 w-3 animate-spin text-gray-400" />
          {agent.thinking || "In progress..."}
        </p>
      )}
      {isError && agent.error && (
        <p className="text-[11px] text-red-600 mb-1.5">{agent.error}</p>
      )}

      {/* Skills / role metadata */}
      {!isIdle && (
        <p className="text-[9px] font-semibold text-gray-400 uppercase tracking-wider">
          {agent.role}
        </p>
      )}
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
  const [showChainSelector, setShowChainSelector] = useState(false);
  const [isCancelled, setIsCancelled] = useState(false);
  const { agents, isRunning, completedCount, totalDuration } = pipelineState;

  const handleCancel = () => { setIsCancelled(true); onCancelPipeline?.(); };
  const isComplete = !isRunning && agents.length > 0 && completedCount === agents.length;
  const hasErrors = agents.some((a) => a.status === "error");
  const allCompleted = [...completedPipelineTypes, workflowType];
  const availablePipelines = PIPELINE_OPTIONS.filter((p) => !allCompleted.includes(p.type));
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
              <Square className="h-3 w-3" /> Pause
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

      {/* Agent cards */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
        {agents.map((agent, idx) => (
          <AgentCard key={agent.id} agent={agent} index={idx} />
        ))}

        {/* Chain pipeline */}
        {isComplete && availablePipelines.length > 0 && onChainPipeline && (
          <div className="pt-2">
            <button
              onClick={() => setShowChainSelector(!showChainSelector)}
              className="w-full flex items-center justify-between rounded-xl border border-gray-200 bg-white hover:bg-gray-50 px-4 py-3 text-left transition-all"
            >
              <div className="flex items-center gap-2">
                <ArrowRight className="h-3.5 w-3.5 text-gray-400" />
                <span className="text-[12px] font-semibold text-gray-700">Chain to next pipeline</span>
              </div>
              <span className="text-[10px] text-gray-400">{showChainSelector ? "▲" : "▼"}</span>
            </button>
            <AnimatePresence>
              {showChainSelector && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  className="overflow-hidden mt-1.5 space-y-1"
                >
                  {availablePipelines.map((pipeline) => (
                    <button
                      key={pipeline.type}
                      onClick={() => { onChainPipeline(pipeline.type); setShowChainSelector(false); }}
                      className="w-full flex items-center justify-between rounded-xl border border-gray-200 bg-white hover:border-[#1B2A4A] hover:bg-blue-50 px-4 py-3 text-left transition-all"
                    >
                      <div>
                        <p className="text-[12px] font-semibold text-gray-900">{pipeline.label}</p>
                        <p className="text-[10px] text-gray-400">{pipeline.description}</p>
                      </div>
                      <ArrowRight className="h-3.5 w-3.5 text-gray-400 flex-shrink-0" />
                    </button>
                  ))}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}

        {(isComplete || isCancelled) && (
          <button
            onClick={() => { setIsCancelled(false); onRunAnother?.(); }}
            className="w-full flex items-center justify-center gap-2 rounded-xl border border-gray-200 bg-white hover:bg-gray-50 px-4 py-2.5 text-[11px] font-medium text-gray-600 transition-all"
          >
            <RotateCcw className="h-3.5 w-3.5" /> New Pipeline
          </button>
        )}
      </div>

      {/* Follow-up input removed — not needed */}
    </div>
  );
}
