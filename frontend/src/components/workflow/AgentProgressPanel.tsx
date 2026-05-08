"use client";

import { useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { CheckCircle2, Loader2, Circle, AlertCircle, RotateCcw, Clock, FileText, Presentation, Layout, ArrowRight, StopCircle } from "lucide-react";
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

const STATUS_ICON = { idle: Circle, thinking: Loader2, running: Loader2, done: CheckCircle2, error: AlertCircle };
const STATUS_COLOR = {
  idle: "text-gray-300",
  thinking: "text-blue-500",
  running: "text-blue-500",
  done: "text-emerald-500",
  error: "text-red-500",
};

const STATUS_DOT: Record<string, string> = {
  idle: "bg-gray-300",
  thinking: "bg-blue-500 animate-pulse",
  running: "bg-blue-500 animate-pulse",
  done: "bg-emerald-500",
  error: "bg-red-500",
};

const PIPELINE_OPTIONS: { type: WorkflowType; label: string; icon: typeof FileText }[] = [
  { type: "ppt", label: "Presentation", icon: Presentation },
  { type: "user_stories", label: "User Stories", icon: FileText },
  { type: "prototype", label: "Prototype", icon: Layout },
];

export function AgentProgressPanel({ pipelineState, workflowType, onViewResults, onRunAnother, onFollowUp, onChainPipeline, completedPipelineTypes = [], onCancelPipeline }: AgentProgressPanelProps) {
  const [showChainSelector, setShowChainSelector] = useState(false);
  const [isCancelled, setIsCancelled] = useState(false);
  const { agents, isRunning, completedCount, totalDuration } = pipelineState;

  const handleCancel = () => {
    setIsCancelled(true);
    onCancelPipeline?.();
  };
  const isComplete = !isRunning && agents.length > 0 && completedCount === agents.length;
  const hasErrors = agents.some((a) => a.status === "error");
  const errorAgents = agents.filter((a) => a.status === "error");

  const allCompleted = [...completedPipelineTypes, workflowType];
  const availablePipelines = PIPELINE_OPTIONS.filter((p) => !allCompleted.includes(p.type));

  return (
    <div className="flex h-full flex-col bg-white">
      {/* Header */}
      <div className="px-5 py-4 border-b border-gray-200">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-gray-900">
              {isCancelled ? "Pipeline Stopped" : isRunning ? "Running Pipeline" : isComplete ? "Pipeline Complete" : hasErrors ? "Pipeline Error" : "Agent Progress"}
            </h2>
            <p className="text-[11px] text-gray-500 mt-0.5">
              {isCancelled && "Execution was cancelled by user"}
              {!isCancelled && isRunning && `${completedCount}/${agents.length} agents completed`}
              {!isCancelled && isComplete && totalDuration && `Finished in ${totalDuration.toFixed(1)}s`}
              {!isCancelled && hasErrors && !isRunning && `${errorAgents.length} agent(s) failed`}
            </p>
          </div>
          {isRunning && !isCancelled && (
            <button
              onClick={handleCancel}
              className="flex items-center gap-1.5 text-[11px] font-medium text-gray-500 hover:text-gray-900 hover:bg-gray-100 rounded-lg px-3 py-1.5 transition-all border border-gray-200 hover:border-gray-300"
              title="Stop pipeline execution"
            >
              <StopCircle className="h-3.5 w-3.5" /> Stop Pipeline
            </button>
          )}
          {!isRunning && !isCancelled && isComplete && !hasErrors && (
            <div className="flex items-center gap-1.5 text-[10px] text-emerald-700 bg-emerald-50 rounded-full px-2.5 py-1 border border-emerald-100">
              <CheckCircle2 className="h-3 w-3" /> Done
            </div>
          )}
          {isCancelled && (
            <div className="flex items-center gap-1.5 text-[10px] text-gray-600 bg-gray-100 rounded-full px-2.5 py-1 border border-gray-200">
              <StopCircle className="h-3 w-3" /> Stopped
            </div>
          )}
        </div>
      </div>

      {/* Cancelled Banner */}
      {isCancelled && (
        <div className="mx-5 mt-4 rounded-lg border border-gray-200 bg-gray-50 p-4">
          <div className="flex items-start gap-3">
            <StopCircle className="h-4 w-4 text-gray-500 flex-shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-800">Pipeline execution stopped</p>
              <p className="text-xs text-gray-500 mt-1">You stopped the pipeline before it completed. No output was generated.</p>
              <button
                onClick={() => { setIsCancelled(false); onRunAnother?.(); }}
                className="mt-3 flex items-center gap-1.5 text-[11px] font-medium text-gray-700 bg-white border border-gray-200 rounded-lg px-3 py-1.5 hover:bg-gray-50 transition-all"
              >
                <RotateCcw className="h-3 w-3" /> Start a New Pipeline
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Error Banner */}
      {hasErrors && !isRunning && (
        <div className="mx-5 mt-4 rounded-lg border border-red-200 bg-red-50 p-4">
          <div className="flex items-start gap-3">
            <AlertCircle className="h-4 w-4 text-red-500 flex-shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-red-800">Pipeline encountered an error</p>
              <p className="text-xs text-red-600 mt-1 leading-relaxed">
                {errorAgents.map((a) => a.error || `${a.name} failed`).join(". ")}
              </p>
              <button onClick={onRunAnother} className="mt-3 text-[11px] font-medium text-red-700 bg-white border border-red-200 rounded-lg px-3 py-1.5 hover:bg-red-50 transition-all">
                Try Again
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Agent Timeline */}
      <div className="flex-1 overflow-y-auto px-5 py-4">
        <div className="space-y-1">
          {agents.map((agent, idx) => {
            const isActive = agent.status === "running" || agent.status === "thinking";
            return (
              <motion.div
                key={agent.id}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: idx * 0.02 }}
                className={`flex items-center gap-3 px-4 py-2.5 rounded-lg transition-all ${
                  isActive ? "bg-blue-50 border border-blue-100" :
                  agent.status === "error" ? "bg-red-50 border border-red-100" :
                  "border border-transparent"
                }`}
              >
                {/* Status dot */}
                <div className={`w-2 h-2 rounded-full flex-shrink-0 ${STATUS_DOT[agent.status] || "bg-gray-300"}`} />

                <div className="flex-1 min-w-0">
                  <p className={`text-[12px] font-medium ${
                    agent.status === "idle" ? "text-gray-400" :
                    agent.status === "error" ? "text-red-700" :
                    "text-gray-900"
                  }`}>{agent.name}</p>
                  {isActive && agent.thinking && (
                    <p className="text-[10px] text-blue-600 mt-0.5 truncate">{agent.thinking}</p>
                  )}
                  {isActive && !agent.thinking && (
                    <p className="text-[10px] text-blue-600 mt-0.5">Processing...</p>
                  )}
                  {agent.status === "error" && agent.error && (
                    <p className="text-[10px] text-red-600 mt-1 leading-relaxed">{agent.error}</p>
                  )}
                </div>

                {agent.duration !== null && (
                  <span className="text-[9px] text-gray-400 flex items-center gap-0.5 flex-shrink-0">
                    <Clock className="h-2.5 w-2.5" />{agent.duration.toFixed(1)}s
                  </span>
                )}
                {agent.status === "done" && (
                  <CheckCircle2 className="h-4 w-4 text-emerald-500 flex-shrink-0" />
                )}
                {agent.status === "error" && (
                  <AlertCircle className="h-4 w-4 text-red-500 flex-shrink-0" />
                )}
              </motion.div>
            );
          })}
        </div>
      </div>

      {/* Actions — shown when pipeline completes */}
      {isComplete && (
        <div className="px-5 py-3 border-t border-gray-200 space-y-2">
          {/* Chain Pipeline Selector */}
          {availablePipelines.length > 0 && onChainPipeline && (
            <div>
              <button
                onClick={() => setShowChainSelector(!showChainSelector)}
                className="w-full flex items-center justify-center gap-2 rounded-lg bg-blue-50 border border-blue-200 text-blue-600 px-4 py-2.5 text-xs font-medium hover:bg-blue-100 transition-all"
              >
                <ArrowRight className="h-3.5 w-3.5" /> Chain to Next Pipeline
              </button>
              <AnimatePresence>
                {showChainSelector && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    className="mt-2 space-y-1.5 overflow-hidden"
                  >
                    <p className="text-[9px] text-gray-500 px-1">Uses output from this pipeline as context:</p>
                    {availablePipelines.map((pipeline) => {
                      const Icon = pipeline.icon;
                      return (
                        <button
                          key={pipeline.type}
                          onClick={() => { onChainPipeline(pipeline.type); setShowChainSelector(false); }}
                          className="w-full flex items-center gap-3 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2.5 text-left hover:bg-gray-100 hover:border-gray-300 transition-all"
                        >
                          <Icon className="h-4 w-4 text-gray-500 flex-shrink-0" />
                          <div className="flex-1">
                            <p className="text-[11px] font-semibold text-gray-900">{pipeline.label}</p>
                            <p className="text-[9px] text-gray-500">Build on previous results</p>
                          </div>
                          <ArrowRight className="h-3 w-3 text-gray-400" />
                        </button>
                      );
                    })}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )}

          {/* Start a New Pipeline */}
          <button onClick={onRunAnother} className="w-full flex items-center justify-center gap-2 rounded-lg bg-gray-100 border border-gray-200 text-gray-600 px-4 py-2 text-xs font-medium hover:bg-gray-200 transition-all">
            <RotateCcw className="h-3.5 w-3.5" /> Start a New Pipeline
          </button>
        </div>
      )}
    </div>
  );
}
