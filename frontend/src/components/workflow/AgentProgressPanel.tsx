"use client";

import { useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { CheckCircle2, Loader2, Circle, AlertCircle, RotateCcw, Clock, FileText, Presentation, Layout, ArrowRight } from "lucide-react";
import type { AgentRunState, PipelineRunState, WorkflowType } from "@/types/index";

interface AgentProgressPanelProps {
  pipelineState: PipelineRunState;
  workflowType: WorkflowType;
  onViewResults?: () => void;
  onRunAnother?: () => void;
  onFollowUp?: (message: string) => void;
  onChainPipeline?: (type: WorkflowType) => void;
  completedPipelineTypes?: WorkflowType[];
}

const STATUS_ICON = { idle: Circle, thinking: Loader2, running: Loader2, done: CheckCircle2, error: AlertCircle };
const STATUS_COLOR = { idle: "text-[#87867f]", thinking: "text-blue-500", running: "text-blue-500", done: "text-green-600", error: "text-red-500" };

const PIPELINE_OPTIONS: { type: WorkflowType; label: string; icon: typeof FileText; color: string }[] = [
  { type: "ppt", label: "Presentation", icon: Presentation, color: "text-amber-600 bg-amber-50 border-amber-200" },
  { type: "user_stories", label: "User Stories", icon: FileText, color: "text-blue-600 bg-blue-50 border-blue-200" },
  { type: "prototype", label: "Prototype", icon: Layout, color: "text-emerald-600 bg-emerald-50 border-emerald-200" },
];

export function AgentProgressPanel({ pipelineState, workflowType, onViewResults, onRunAnother, onFollowUp, onChainPipeline, completedPipelineTypes = [] }: AgentProgressPanelProps) {
  const [showChainSelector, setShowChainSelector] = useState(false);
  const { agents, isRunning, completedCount, totalDuration } = pipelineState;
  const isComplete = !isRunning && agents.length > 0 && completedCount === agents.length;
  const hasErrors = agents.some((a) => a.status === "error");
  const errorAgents = agents.filter((a) => a.status === "error");

  // Available pipelines = all 3 minus already completed ones (including current)
  const allCompleted = [...completedPipelineTypes, workflowType];
  const availablePipelines = PIPELINE_OPTIONS.filter((p) => !allCompleted.includes(p.type));

  return (
    <div className="flex h-full flex-col bg-white">
      {/* Header */}
      <div className="px-5 py-4 border-b border-[#e8e6dc]">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-[#141413]">
              {isRunning ? "Running Pipeline" : isComplete ? "Pipeline Complete" : hasErrors ? "Pipeline Error" : "Agent Progress"}
            </h2>
            <p className="text-[11px] text-[#87867f] mt-0.5">
              {isRunning && `${completedCount}/${agents.length} agents completed`}
              {isComplete && totalDuration && `Finished in ${totalDuration.toFixed(1)}s`}
              {hasErrors && !isRunning && `${errorAgents.length} agent(s) failed`}
            </p>
          </div>
          {isRunning && (
            <div className="flex items-center gap-1.5 text-[10px] text-blue-600 bg-blue-50 rounded-full px-2.5 py-1 border border-blue-100">
              <Loader2 className="h-3 w-3 animate-spin" /> Processing
            </div>
          )}
          {isComplete && !hasErrors && (
            <div className="flex items-center gap-1.5 text-[10px] text-green-700 bg-green-50 rounded-full px-2.5 py-1 border border-green-100">
              <CheckCircle2 className="h-3 w-3" /> Done
            </div>
          )}
        </div>
      </div>

      {/* Error Banner */}
      {hasErrors && !isRunning && (
        <div className="mx-5 mt-4 rounded-xl border border-red-200 bg-red-50 p-4">
          <div className="flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5" />
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
            const StatusIcon = STATUS_ICON[agent.status];
            const statusColor = STATUS_COLOR[agent.status];
            const isActive = agent.status === "running" || agent.status === "thinking";
            return (
              <motion.div key={agent.id} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: idx * 0.02 }}
                className={`flex items-start gap-3 rounded-lg px-3 py-2.5 transition-all ${
                  isActive ? "bg-blue-50 border border-blue-100" :
                  agent.status === "error" ? "bg-red-50 border border-red-100" :
                  "border border-transparent"
                }`}>
                <StatusIcon className={`h-4 w-4 flex-shrink-0 mt-0.5 ${statusColor} ${isActive ? "animate-spin" : ""}`} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm">{agent.icon}</span>
                    <span className={`text-[12px] font-medium ${agent.status === "idle" ? "text-[#87867f]" : agent.status === "error" ? "text-red-700" : "text-[#141413]"}`}>{agent.name}</span>
                  </div>
                  {isActive && agent.thinking && <p className="text-[10px] text-blue-600/70 mt-0.5 truncate ml-6">{agent.thinking}</p>}
                  {agent.status === "error" && agent.error && (
                    <p className="text-[10px] text-red-600 mt-1 ml-6 leading-relaxed">{agent.error}</p>
                  )}
                </div>
                {agent.duration !== null && (
                  <span className="text-[9px] text-[#87867f] flex items-center gap-0.5 flex-shrink-0">
                    <Clock className="h-2.5 w-2.5" />{agent.duration.toFixed(1)}s
                  </span>
                )}
              </motion.div>
            );
          })}
        </div>
      </div>

      {/* Actions — shown when pipeline completes */}
      {isComplete && (
        <div className="px-5 py-3 border-t border-[#e8e6dc] space-y-2">
          {/* Chain Pipeline Selector */}
          {availablePipelines.length > 0 && onChainPipeline && (
            <div>
              <button
                onClick={() => setShowChainSelector(!showChainSelector)}
                className="w-full flex items-center justify-center gap-2 rounded-xl bg-[#c96442]/10 border border-[#c96442]/20 text-[#c96442] px-4 py-2.5 text-xs font-medium hover:bg-[#c96442]/15 transition-all"
              >
                <ArrowRight className="h-3.5 w-3.5" /> Continue with Another Pipeline
              </button>
              <AnimatePresence>
                {showChainSelector && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    className="mt-2 space-y-1.5 overflow-hidden"
                  >
                    <p className="text-[9px] text-[#87867f] px-1">Uses output from this pipeline as context:</p>
                    {availablePipelines.map((pipeline) => {
                      const Icon = pipeline.icon;
                      return (
                        <button
                          key={pipeline.type}
                          onClick={() => { onChainPipeline(pipeline.type); setShowChainSelector(false); }}
                          className={`w-full flex items-center gap-3 rounded-lg border px-3 py-2.5 text-left hover:shadow-sm transition-all ${pipeline.color}`}
                        >
                          <Icon className="h-4 w-4 flex-shrink-0" />
                          <div className="flex-1">
                            <p className="text-[11px] font-semibold">{pipeline.label}</p>
                            <p className="text-[9px] opacity-70">Build on previous results</p>
                          </div>
                          <ArrowRight className="h-3 w-3 opacity-50" />
                        </button>
                      );
                    })}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )}

          {/* Go Home */}
          <button onClick={onRunAnother} className="w-full flex items-center justify-center gap-2 rounded-xl bg-[#faf9f5] border border-[#e8e6dc] text-[#5e5d59] px-4 py-2 text-xs font-medium hover:bg-[#f0eee6] transition-all">
            <RotateCcw className="h-3.5 w-3.5" /> Start Fresh
          </button>
        </div>
      )}
    </div>
  );
}
