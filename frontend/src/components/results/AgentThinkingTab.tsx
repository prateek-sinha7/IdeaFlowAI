"use client";

import { useEffect, useRef, useState } from "react";
import {
  Brain, Wrench, ChevronDown, ChevronRight, Zap, CheckCircle2,
  XCircle, Clock, Cpu, FileText, Database,
  Layers, Activity, Eye, EyeOff, Copy, Check,
} from "lucide-react";
import type { AgentRunState, ContextSource, ToolCallEntry, PipelineRunState } from "@/types/index";
import { PrototypePipelineView } from "./PrototypePipelineView";
import { TokenUsageSummary } from "@/components/workflow/TokenUsageSummary";

interface AgentThinkingTabProps {
  agents: AgentRunState[];
  pipelineState?: PipelineRunState;
}

// ─── Agent accent — single on-brand color (design system navy #1B2A4A) ─────────
// Replaces the former per-agent rainbow so the trace matches the rest of the app.
// Status uses the same navy: in-progress and done are distinguished by icon
// (pulse vs check) and fill, not hue. error=red, clarify=amber are kept separate.
const AGENT_ACCENT = {
  bg: "bg-[#E8EDF5]",
  text: "text-[#1B2A4A]",
  border: "border-[#1B2A4A]/20",
  dot: "bg-[#1B2A4A]",
  glow: "",
};

// ─── Empty state ──────────────────────────────────────────────────────────────
function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4 text-center px-8">
      <div className="relative">
        <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-[#1B2A4A]/8 to-[#1B2A4A]/4 flex items-center justify-center">
          <Activity className="h-7 w-7 text-[#1B2A4A]/30" />
        </div>
        <div className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-gray-200 flex items-center justify-center">
          <div className="w-1.5 h-1.5 rounded-full bg-gray-400" />
        </div>
      </div>
      <div>
        <p className="text-[13px] font-semibold text-gray-700 mb-1">Pipeline Trace</p>
        <p className="text-[11px] text-gray-400 leading-relaxed max-w-[200px]">
          Start a pipeline to see real-time agent reasoning, tool calls, and context flow.
        </p>
      </div>
    </div>
  );
}

// ─── Pipeline header bar ──────────────────────────────────────────────────────
function PipelineHeader({ pipelineState }: { pipelineState?: PipelineRunState }) {
  if (!pipelineState) return null;
  const { isRunning, completedCount, agents, totalDuration, plannerStatus, executionGate } = pipelineState;
  const total = agents.length;
  const progress = total > 0 ? (completedCount / total) * 100 : 0;
  const hasErrors = agents.some(a => a.status === "error");

  return (
    <div className="flex-shrink-0 px-4 pt-4 pb-3 border-b border-gray-100 bg-white">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${isRunning ? "bg-[#1B2A4A] animate-pulse" : hasErrors ? "bg-red-400" : "bg-[#1B2A4A]"}`} />
          <span className="text-[11px] font-semibold text-gray-700 uppercase tracking-wider">
            {isRunning ? "Pipeline Running" : hasErrors ? "Completed with errors" : "Pipeline Complete"}
          </span>
        </div>
        <div className="flex items-center gap-3">
          {executionGate && (
            <span className={`text-[9px] font-bold px-2 py-0.5 rounded-full ${
              executionGate === "PROCEED" ? "bg-[#E8EDF5] text-[#1B2A4A] border border-[#1B2A4A]/20" : "bg-amber-50 text-amber-700 border border-amber-200"
            }`}>
              {executionGate === "PROCEED" ? "✓ PROCEED" : "⚡ CLARIFY"}
            </span>
          )}
          {totalDuration != null && (
            <span className="text-[10px] text-gray-400 flex items-center gap-1">
              <Clock className="h-3 w-3" />{totalDuration.toFixed(1)}s
            </span>
          )}
        </div>
      </div>
      {total > 0 && (
        <div className="flex items-center gap-2">
          <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${hasErrors ? "bg-red-400" : "bg-gradient-to-r from-[#1B2A4A] to-blue-500"}`}
              style={{ width: `${progress}%` }}
            />
          </div>
          <span className="text-[10px] text-gray-500 flex-shrink-0">{completedCount}/{total}</span>
        </div>
      )}
    </div>
  );
}

// ─── Planner step card ────────────────────────────────────────────────────────
function PlannerCard({ pipelineState }: { pipelineState: PipelineRunState }) {
  const [expanded, setExpanded] = useState(false);
  const { plannerStatus, plannerSummary, executionGate } = pipelineState;
  if (!plannerStatus || plannerStatus === "idle") return null;

  const isRunning = plannerStatus === "running";
  const isDone = plannerStatus === "complete" || plannerStatus === "timeout";
  const isError = plannerStatus === "error";

  return (
    <div className="relative pl-8">
      {/* Timeline dot */}
      <div className="absolute left-0 top-3 flex flex-col items-center">
        <div className={`w-6 h-6 rounded-full flex items-center justify-center border-2 z-10 ${
          isRunning ? "border-[#1B2A4A]/40 bg-[#E8EDF5] animate-pulse" :
          isDone ? "border-[#1B2A4A] bg-[#1B2A4A]" :
          "border-red-400 bg-red-50"
        }`}>
          {isDone ? <CheckCircle2 className="h-3 w-3 text-white" /> :
           isError ? <XCircle className="h-3 w-3 text-red-500" /> :
           <Brain className="h-3 w-3 text-[#1B2A4A]" />}
        </div>
        <div className="w-px flex-1 bg-gray-200 mt-1" style={{ minHeight: 20 }} />
      </div>

      <div className={`rounded-xl border overflow-hidden transition-all ${
        isRunning ? "border-[#1B2A4A]/20 shadow-sm" : "border-gray-100"
      }`}>
        <button
          onClick={() => setExpanded(v => !v)}
          className="w-full flex items-center gap-3 px-4 py-3 bg-white hover:bg-gray-50/50 transition-colors text-left"
        >
          <div className="w-7 h-7 rounded-lg bg-[#E8EDF5] flex items-center justify-center flex-shrink-0">
            <Brain className="h-3.5 w-3.5 text-[#1B2A4A]" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <p className="text-[12px] font-semibold text-gray-900">Deep Planner</p>
              {plannerStatus === "timeout" && (
                <span className="text-[9px] bg-amber-50 text-amber-600 border border-amber-200 px-1.5 py-0.5 rounded-full font-medium">TIMEOUT</span>
              )}
            </div>
            <p className="text-[10px] text-gray-400 truncate">
              {plannerSummary ? `Intent: ${plannerSummary.slice(0, 60)}` : "Analyzing brief & planning execution…"}
            </p>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            {executionGate && (
              <span className={`text-[9px] font-bold px-2 py-0.5 rounded-full ${
                executionGate === "PROCEED" ? "bg-[#E8EDF5] text-[#1B2A4A]" : "bg-amber-50 text-amber-700"
              }`}>
                {executionGate}
              </span>
            )}
            {isRunning && <Zap className="h-3.5 w-3.5 text-[#1B2A4A] animate-pulse" />}
            <ChevronDown className={`h-3.5 w-3.5 text-gray-400 transition-transform ${expanded ? "rotate-180" : ""}`} />
          </div>
        </button>

        {expanded && plannerSummary && (
          <div className="border-t border-gray-100 px-4 py-3 bg-gradient-to-b from-[#E8EDF5]/40 to-white">
            <p className="text-[10px] font-semibold text-[#1B2A4A] uppercase tracking-wider mb-1.5">Inferred Intent</p>
            <p className="text-[11px] text-gray-700 leading-relaxed">{plannerSummary}</p>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Context sources row ──────────────────────────────────────────────────────
function ContextSourcesRow({ sources }: { sources: ContextSource[] }) {
  return (
    <div className="mb-3">
      <div className="flex items-center gap-1.5 mb-2">
        <Database className="h-3 w-3 text-gray-400" />
        <span className="text-[9px] font-bold text-gray-400 uppercase tracking-widest">Context Received</span>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {sources.map((src, i) => {
          const label = src.type === "summary"
            ? (src.agent_name || src.agent_id || "Agent")
            : (src.artifact_type || "artifact");
          const size = src.type === "summary" && src.summary_length != null
            ? `${(src.summary_length / 1000).toFixed(1)}k`
            : src.type === "artifact" && src.artifact_size_chars != null
            ? `${(src.artifact_size_chars / 1000).toFixed(1)}k`
            : null;
          const compression = src.type === "summary" && src.summary_length != null && src.full_output_length != null && src.full_output_length > 0
            ? Math.round((1 - src.summary_length / src.full_output_length) * 100)
            : null;
          return (
            <div key={i} className="flex items-center gap-1.5 bg-blue-50 border border-blue-100 rounded-lg px-2.5 py-1.5">
              <Layers className="h-2.5 w-2.5 text-blue-500 flex-shrink-0" />
              <span className="text-[10px] font-medium text-blue-700 truncate max-w-[100px]">{label}</span>
              {size && <span className="text-[9px] text-blue-400">{size}</span>}
              {compression != null && compression > 0 && (
                <span className="text-[9px] bg-blue-100 text-blue-600 px-1 rounded font-medium">-{compression}%</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Tool calls section ───────────────────────────────────────────────────────
function ToolCallsSection({ toolCalls }: { toolCalls: ToolCallEntry[] }) {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  return (
    <div className="mb-3">
      <div className="flex items-center gap-1.5 mb-2">
        <Wrench className="h-3 w-3 text-gray-400" />
        <span className="text-[9px] font-bold text-gray-400 uppercase tracking-widest">Tool Calls</span>
        <span className="text-[9px] bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded-full font-medium">{toolCalls.length}</span>
      </div>
      <div className="space-y-1.5">
        {toolCalls.map((tc, i) => (
          <div key={i} className="rounded-lg border border-gray-100 overflow-hidden bg-white">
            <button
              onClick={() => setExpandedIdx(expandedIdx === i ? null : i)}
              className="w-full flex items-center gap-2 px-3 py-2 hover:bg-gray-50 transition-colors text-left"
            >
              <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${tc.result != null ? "bg-[#1B2A4A]" : "bg-amber-400 animate-pulse"}`} />
              <span className="text-[10px] font-mono font-semibold text-[#1B2A4A] flex-1 truncate">{tc.tool}</span>
              <span className="text-[9px] text-gray-400 truncate max-w-[120px]">
                {Object.entries(tc.args || {}).map(([k, v]) => `${k}: ${String(v).slice(0, 20)}`).join(", ") || "no args"}
              </span>
              <ChevronDown className={`h-3 w-3 text-gray-300 flex-shrink-0 transition-transform ${expandedIdx === i ? "rotate-180" : ""}`} />
            </button>
            {expandedIdx === i && (
              <div className="border-t border-gray-100 bg-gray-50/50">
                {Object.keys(tc.args || {}).length > 0 && (
                  <div className="px-3 py-2 border-b border-gray-100">
                    <p className="text-[9px] font-semibold text-gray-400 uppercase tracking-wider mb-1">Arguments</p>
                    <pre className="text-[9px] text-gray-600 font-mono whitespace-pre-wrap leading-relaxed">
                      {JSON.stringify(tc.args, null, 2).slice(0, 400)}
                    </pre>
                  </div>
                )}
                {tc.result != null && (
                  <div className="px-3 py-2">
                    <p className="text-[9px] font-semibold text-[#1B2A4A] uppercase tracking-wider mb-1">Result</p>
                    <pre className="text-[9px] text-gray-600 font-mono whitespace-pre-wrap leading-relaxed max-h-[80px] overflow-y-auto">
                      {tc.result.slice(0, 500)}{tc.result.length > 500 ? "\n…" : ""}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Input prompt section ─────────────────────────────────────────────────────
function InputPromptSection({ prompt }: { prompt: string }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(prompt);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div className="mb-3">
      <button
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-1.5 text-[9px] font-bold text-gray-400 uppercase tracking-widest hover:text-gray-600 transition-colors"
      >
        <FileText className="h-3 w-3" />
        Full Input Prompt
        <ChevronDown className={`h-3 w-3 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="mt-2 rounded-lg border border-gray-100 overflow-hidden">
          <div className="flex items-center justify-between px-3 py-1.5 bg-gray-50 border-b border-gray-100">
            <span className="text-[9px] text-gray-400">{prompt.length.toLocaleString()} chars</span>
            <button onClick={handleCopy} className="flex items-center gap-1 text-[9px] text-gray-400 hover:text-gray-600 transition-colors">
              {copied ? <Check className="h-3 w-3 text-[#1B2A4A]" /> : <Copy className="h-3 w-3" />}
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
          <pre className="text-[9px] text-gray-600 whitespace-pre-wrap leading-relaxed p-3 max-h-[160px] overflow-y-auto font-mono bg-white">
            {prompt.slice(0, 3000)}{prompt.length > 3000 ? "\n…[truncated]" : ""}
          </pre>
        </div>
      )}
    </div>
  );
}

// ─── Output preview section ───────────────────────────────────────────────────
function OutputPreviewSection({ output, agentId }: { output: string; agentId: string }) {
  const [open, setOpen] = useState(false);
  const isHtml = /<!DOCTYPE|<html/i.test(output) || output.includes("<artifact>");
  const preview = isHtml ? "[HTML artifact — click to expand]" : output.slice(0, 120) + (output.length > 120 ? "…" : "");
  return (
    <div>
      <button
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-1.5 text-[9px] font-bold text-gray-400 uppercase tracking-widest hover:text-gray-600 transition-colors"
      >
        {open ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
        Agent Output
        <span className="text-[9px] text-gray-300 font-normal normal-case tracking-normal">
          {(output.length / 1000).toFixed(1)}k chars
        </span>
        <ChevronDown className={`h-3 w-3 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {!open && (
        <p className="mt-1 text-[10px] text-gray-500 leading-relaxed line-clamp-2 font-mono">{preview}</p>
      )}
      {open && (
        <div className="mt-2 rounded-lg border border-gray-100 overflow-hidden">
          <pre className="text-[9px] text-gray-600 whitespace-pre-wrap leading-relaxed p-3 max-h-[200px] overflow-y-auto font-mono bg-gray-50">
            {output.slice(0, 4000)}{output.length > 4000 ? "\n…[truncated]" : ""}
          </pre>
        </div>
      )}
    </div>
  );
}

// ─── Per-agent timeline card ──────────────────────────────────────────────────
interface AgentCardProps {
  agent: AgentRunState;
  isLast: boolean;
  isRunning: boolean;
  refCallback?: (el: HTMLDivElement | null) => void;
}

function AgentTimelineCard({ agent, isLast, isRunning, refCallback }: AgentCardProps) {
  const [expanded, setExpanded] = useState(isRunning);
  const color = AGENT_ACCENT;
  const isDone = agent.status === "done";
  const isError = agent.status === "error";
  const isIdle = agent.status === "idle";
  const initials = agent.name.split(" ").map(w => w[0]).slice(0, 2).join("").toUpperCase();

  // Auto-expand when agent starts running
  useEffect(() => {
    if (isRunning) setExpanded(true);
  }, [isRunning]);

  const hasContent = agent.inputPrompt || (agent.contextSources?.length ?? 0) > 0 ||
    (agent.toolCalls?.length ?? 0) > 0 || agent.thinkingText || (isDone && agent.output);

  return (
    <div ref={refCallback} className="relative pl-8">
      {/* Timeline line */}
      {!isLast && (
        <div className="absolute left-[11px] top-8 bottom-0 w-px bg-gradient-to-b from-gray-200 to-transparent" />
      )}

      {/* Timeline dot */}
      <div className="absolute left-0 top-3">
        <div className={`w-6 h-6 rounded-full flex items-center justify-center border-2 z-10 transition-all ${
          isRunning ? `${color.border} ${color.bg} shadow-md ${color.glow}` :
          isDone ? "border-[#1B2A4A] bg-[#1B2A4A]" :
          isError ? "border-red-400 bg-red-50" :
          "border-gray-200 bg-white"
        }`}>
          {isDone ? <CheckCircle2 className="h-3 w-3 text-white" /> :
           isError ? <XCircle className="h-3 w-3 text-red-500" /> :
           isRunning ? <div className="w-2 h-2 rounded-full bg-current animate-pulse" style={{ color: color.dot.replace("bg-", "") }} /> :
           <div className="w-1.5 h-1.5 rounded-full bg-gray-300" />}
        </div>
      </div>

      {/* Card */}
      <div className={`rounded-xl border overflow-hidden transition-all duration-200 ${
        isRunning ? `${color.border} shadow-md ${color.glow}` :
        isDone ? "border-gray-100 shadow-sm" :
        isError ? "border-red-100" :
        "border-gray-100 opacity-50"
      }`}>
        {/* Header */}
        <button
          onClick={() => hasContent && setExpanded(v => !v)}
          className={`w-full flex items-center gap-3 px-4 py-3 text-left transition-colors ${
            hasContent ? "hover:bg-gray-50/50 cursor-pointer" : "cursor-default"
          } bg-white`}
        >
          {/* Avatar */}
          <div className={`w-8 h-8 rounded-xl flex items-center justify-center text-[11px] font-bold flex-shrink-0 ${
            isIdle ? "bg-gray-100 text-gray-400" : `${color.bg} ${color.text}`
          }`}>
            {agent.icon && agent.icon !== "🤖" ? agent.icon : initials}
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-0.5">
              <p className={`text-[12px] font-semibold truncate ${isIdle ? "text-gray-400" : "text-gray-900"}`}>
                {agent.name}
              </p>
              {isRunning && (
                <span className={`flex items-center gap-1 text-[9px] font-bold px-1.5 py-0.5 rounded-full ${color.bg} ${color.text}`}>
                  <Zap className="h-2.5 w-2.5" />LIVE
                </span>
              )}
              {isDone && (
                <span className="text-[9px] font-bold text-[#1B2A4A] bg-[#E8EDF5] px-1.5 py-0.5 rounded-full">DONE</span>
              )}
              {isError && (
                <span className="text-[9px] font-bold text-red-600 bg-red-50 px-1.5 py-0.5 rounded-full">ERROR</span>
              )}
            </div>
            <p className={`text-[10px] truncate ${isIdle ? "text-gray-300" : "text-gray-400"}`}>{agent.role}</p>
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">
            {/* Token stats */}
            {isDone && agent.totalTokens != null && agent.totalTokens > 0 && (
              <div className="flex items-center gap-1 text-[9px] text-gray-400">
                <Cpu className="h-2.5 w-2.5" />
                <span>{(agent.totalTokens / 1000).toFixed(1)}k</span>
              </div>
            )}
            {isDone && agent.duration != null && (
              <span className="text-[9px] text-gray-400 flex items-center gap-0.5">
                <Clock className="h-2.5 w-2.5" />{agent.duration.toFixed(1)}s
              </span>
            )}
            {hasContent && (
              <ChevronDown className={`h-3.5 w-3.5 text-gray-300 transition-transform ${expanded ? "rotate-180" : ""}`} />
            )}
          </div>
        </button>

        {/* Live thinking stream */}
        {isRunning && agent.thinkingText && (
          <div className={`px-4 py-2 border-t ${color.border} bg-gradient-to-r ${color.bg}/20 to-white`}>
            <div className="flex items-center gap-1.5 mb-1">
              <Brain className={`h-3 w-3 ${color.text}`} />
              <span className={`text-[9px] font-bold uppercase tracking-widest ${color.text}`}>Reasoning (live)</span>
            </div>
            <p className="text-[10px] text-gray-700 leading-relaxed font-mono">
              {agent.thinkingText.slice(-300)}
              <span className="animate-pulse">▌</span>
            </p>
          </div>
        )}

        {/* Expanded body */}
        {expanded && hasContent && (
          <div className="border-t border-gray-100 px-4 py-3 bg-white space-y-0">
            {agent.contextSources && agent.contextSources.length > 0 && (
              <ContextSourcesRow sources={agent.contextSources} />
            )}
            {agent.toolCalls && agent.toolCalls.length > 0 && (
              <ToolCallsSection toolCalls={agent.toolCalls} />
            )}
            {agent.inputPrompt && (
              <InputPromptSection prompt={agent.inputPrompt} />
            )}
            {isDone && agent.output && agent.output.trim().length > 0 && (
              <div className="mt-3 pt-3 border-t border-gray-100">
                <OutputPreviewSection output={agent.output} agentId={agent.id} />
              </div>
            )}
            {isError && agent.error && (
              <div className="mt-2 rounded-lg bg-red-50 border border-red-100 px-3 py-2">
                <p className="text-[10px] text-red-600 font-medium">{agent.error}</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// Token usage is rendered via the shared TokenUsageSummary card (see main export),
// replacing the former bespoke TokenSummary so all pipelines use one component.

// ─── Main export ──────────────────────────────────────────────────────────────
export function AgentThinkingTab({ agents, pipelineState }: AgentThinkingTabProps) {
  const runningRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    runningRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [agents]);

  const hasAnyData = pipelineState?.plannerStatus ||
    agents.some(a => a.thinkingText || (a.toolCalls?.length ?? 0) > 0 || a.inputPrompt || a.status !== "idle");

  if (!hasAnyData) return <EmptyState />;

  // ── Spec Kit prototype pipeline: use rich visualization ──────────────────
  const isPrototypePipeline = agents.some(a =>
    ["prototype-specify", "prototype-plan", "prototype-build", "prototype-validate"].includes(a.id)
  );
  if (isPrototypePipeline) {
    return <PrototypePipelineView agents={agents} pipelineState={pipelineState} />;
  }

  const visibleAgents = agents.filter(a => a.status !== "idle" || (a.inputPrompt || (a.toolCalls?.length ?? 0) > 0));

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <PipelineHeader pipelineState={pipelineState} />

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {/* Planner step */}
        {pipelineState && (
          <PlannerCard pipelineState={pipelineState} />
        )}

        {/* Pipeline start connector */}
        {visibleAgents.length > 0 && pipelineState?.plannerStatus && (
          <div className="pl-8">
            <div className="flex items-center gap-2 py-1">
              <div className="h-px flex-1 bg-gradient-to-r from-gray-200 to-transparent" />
              <span className="text-[9px] text-gray-400 font-medium px-2 py-0.5 bg-gray-100 rounded-full">
                {visibleAgents.length} agent{visibleAgents.length !== 1 ? "s" : ""} dispatched
              </span>
              <div className="h-px flex-1 bg-gradient-to-l from-gray-200 to-transparent" />
            </div>
          </div>
        )}

        {/* Agent cards */}
        {visibleAgents.map((agent, idx) => {
          const isRunning = agent.status === "running" || agent.status === "thinking";
          return (
            <AgentTimelineCard
              key={agent.id}
              agent={agent}
              isLast={idx === visibleAgents.length - 1}
              isRunning={isRunning}
              refCallback={isRunning ? (el) => { runningRef.current = el; } : undefined}
            />
          );
        })}

        {/* All done state */}
        {pipelineState && !pipelineState.isRunning && visibleAgents.length > 0 &&
          visibleAgents.every(a => a.status === "done" || a.status === "error") && (
          <div className="pl-8">
            <div className="flex items-center gap-2 py-2">
              <div className="w-6 h-6 rounded-full bg-[#1B2A4A] flex items-center justify-center flex-shrink-0">
                <CheckCircle2 className="h-3.5 w-3.5 text-white" />
              </div>
              <span className="text-[11px] font-semibold text-[#1B2A4A]">Pipeline complete</span>
              {pipelineState.totalDuration != null && (
                <span className="text-[10px] text-gray-400">in {pipelineState.totalDuration.toFixed(1)}s</span>
              )}
            </div>
          </div>
        )}
      </div>

      {pipelineState && (
        <div className="flex-shrink-0 border-t border-gray-100 px-4 py-3">
          <TokenUsageSummary pipelineState={pipelineState} modelId={pipelineState.modelId} />
        </div>
      )}
    </div>
  );
}
