"use client";

import { useRef, useState } from "react";
import { motion } from "motion/react";
import { CheckCircle2, Loader2, Circle, AlertCircle, RotateCcw, Send, Sparkles, Clock } from "lucide-react";
import type { AgentRunState, PipelineRunState, WorkflowType } from "@/types/index";

interface AgentProgressPanelProps {
  pipelineState: PipelineRunState;
  workflowType: WorkflowType;
  onViewResults?: () => void;
  onRunAnother?: () => void;
  onFollowUp?: (message: string) => void;
}

const STATUS_ICON = { idle: Circle, thinking: Loader2, running: Loader2, done: CheckCircle2, error: AlertCircle };
const STATUS_COLOR = { idle: "text-[#87867f]", thinking: "text-blue-500", running: "text-blue-500", done: "text-green-600", error: "text-red-500" };

export function AgentProgressPanel({ pipelineState, workflowType, onViewResults, onRunAnother, onFollowUp }: AgentProgressPanelProps) {
  const [followUpInput, setFollowUpInput] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const { agents, isRunning, completedCount, totalDuration } = pipelineState;
  const isComplete = !isRunning && agents.length > 0 && completedCount === agents.length;
  const hasErrors = agents.some((a) => a.status === "error");
  const errorAgents = agents.filter((a) => a.status === "error");

  const handleSendFollowUp = () => { if (!followUpInput.trim()) return; onFollowUp?.(followUpInput.trim()); setFollowUpInput(""); };

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
          {hasErrors && !isRunning && (
            <div className="flex items-center gap-1.5 text-[10px] text-red-600 bg-red-50 rounded-full px-2.5 py-1 border border-red-100">
              <AlertCircle className="h-3 w-3" /> Error
            </div>
          )}
        </div>
      </div>

      {/* Error Banner — shown when pipeline has errors */}
      {hasErrors && !isRunning && (
        <div className="mx-5 mt-4 rounded-xl border border-red-200 bg-red-50 p-4">
          <div className="flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-red-800">Pipeline encountered an error</p>
              <p className="text-xs text-red-600 mt-1 leading-relaxed">
                {errorAgents.map((a) => a.error || `${a.name} failed`).join(". ")}
              </p>
              <div className="flex gap-2 mt-3">
                <button onClick={onRunAnother} className="text-[11px] font-medium text-red-700 bg-white border border-red-200 rounded-lg px-3 py-1.5 hover:bg-red-50 transition-all">
                  Try Again
                </button>
              </div>
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

      {/* Actions */}
      {isComplete && (
        <div className="px-5 py-3 border-t border-[#e8e6dc] space-y-2">
          <button onClick={onViewResults} className="w-full flex items-center justify-center gap-2 rounded-xl bg-green-50 border border-green-200 text-green-700 px-4 py-2.5 text-xs font-medium hover:bg-green-100 transition-all">
            <CheckCircle2 className="h-3.5 w-3.5" /> View Results
          </button>
          <button onClick={onRunAnother} className="w-full flex items-center justify-center gap-2 rounded-xl bg-[#faf9f5] border border-[#e8e6dc] text-[#5e5d59] px-4 py-2 text-xs font-medium hover:bg-[#f0eee6] transition-all">
            <RotateCcw className="h-3.5 w-3.5" /> Run Another Pipeline
          </button>
        </div>
      )}

      {/* Follow-up */}
      <div className="px-4 py-3 border-t border-[#e8e6dc]">
        <div className="flex items-center gap-2">
          <div className="flex-1 flex items-center gap-2 rounded-xl border border-[#e8e6dc] bg-[#faf9f5] px-3 py-2.5 focus-within:border-[#c96442]/40 transition-colors">
            <Sparkles className="h-3 w-3 text-[#87867f] flex-shrink-0" />
            <input ref={inputRef} type="text" value={followUpInput} onChange={(e) => setFollowUpInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") handleSendFollowUp(); }}
              placeholder="Steer agents or ask follow-up..." className="flex-1 bg-transparent text-[11px] text-[#141413] placeholder-[#87867f] focus:outline-none" />
          </div>
          <button onClick={handleSendFollowUp} disabled={!followUpInput.trim()} className="flex items-center justify-center rounded-xl bg-[#c96442] text-white p-2.5 transition-all disabled:opacity-30 disabled:cursor-not-allowed">
            <Send className="h-3 w-3" />
          </button>
        </div>
      </div>
    </div>
  );
}
