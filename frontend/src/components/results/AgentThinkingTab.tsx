"use client";

import { useEffect, useRef, useState } from "react";
import {
  Brain, Wrench, ChevronDown, ChevronRight, Zap, CheckCircle2,
  XCircle, Clock, Cpu, FileText, Database,
  Layers, Activity, Eye, EyeOff, Copy, Check,
  AlertTriangle, Pencil,
} from "lucide-react";
import type { AgentRunState, ContextSource, ToolCallEntry, PipelineRunState, ValidationIssue, ClarifyRound } from "@/types/index";
import { PrototypePipelineView } from "./PrototypePipelineView";
import { TokenUsageSummary } from "@/components/workflow/TokenUsageSummary";
import { StartingPointCard } from "./StartingPointCard";
import { ClarificationsCard } from "./ClarificationsCard";

interface AgentThinkingTabProps {
  agents: AgentRunState[];
  pipelineState?: PipelineRunState;
  // Workstream C2 (POR §5 D3+D4) — timeline narrative surfaces. All optional and
  // default-undefined so every existing call site renders byte-unchanged.
  runInput?: string;               // raw run input for StartingPointCard (C1 parse)
  originalBriefRootRunId?: string; // revision-only lineage → lazy Original-brief fetch
  revisionParentVersion?: number;  // "revision of v{n-1}" chip
  clarifications?: ClarifyRound[]; // reopen-fetched rounds; live falls back to pipelineState
  clarificationsLoading?: boolean; // reopen fetch in flight → aria-busy
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
function PipelineHeader({ pipelineState, workflowLabel }: { pipelineState?: PipelineRunState; workflowLabel?: string }) {
  if (!pipelineState) return null;
  const { isRunning, completedCount, agents, totalDuration, executionGate } = pipelineState;
  const total = agents.length;
  const progress = total > 0 ? (completedCount / total) * 100 : 0;
  const hasErrors = agents.some(a => a.status === "error");

  return (
    <div className="flex-shrink-0 px-4 pt-4 pb-3 border-b border-gray-100 bg-white">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${
            isRunning ? "bg-[#1B2A4A] animate-pulse" :
            hasErrors ? "bg-red-400" :
            "bg-[#1B2A4A]"
          }`} />
          <span className="text-[11px] font-semibold text-gray-700 uppercase tracking-wider">
            {workflowLabel || (isRunning ? "Pipeline Running" : hasErrors ? "Completed with errors" : "Pipeline Complete")}
          </span>
        </div>
        <div className="flex items-center gap-3">
          {executionGate && (
            <span className={`text-[9px] font-bold px-2 py-0.5 rounded-full ${
              executionGate === "PROCEED"
                ? "bg-[#E8EDF5] text-[#1B2A4A] border border-[#1B2A4A]/20"
                : "bg-amber-50 text-amber-700 border border-amber-200"
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
      {/* Progress bar — matches prototype style */}
      {total > 0 && (
        <div className="flex items-center gap-1">
          {agents.map((a, i) => (
            <div key={i} className={`h-1.5 flex-1 rounded-full transition-all ${
              a.status === "done" ? "bg-[#1B2A4A]" :
              a.status === "running" || a.status === "thinking" ? "bg-[#1B2A4A] animate-pulse" :
              a.status === "error" ? "bg-red-400" :
              "bg-gray-200"
            }`} />
          ))}
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

// ─── Revision instruction card ────────────────────────────────────────────────
// Extracts and highlights the actual revision request from the full input prompt
// (which can be 60-100k chars of HTML). Makes it immediately visible at the top.
function RevisionInstructionCard({ prompt }: { prompt: string }) {
  const match = prompt.match(/===\s*REVISION REQUEST\s*===\s*\n([\s\S]*?)\n===\s*END REQUEST\s*===/i);
  if (!match) return null;
  const instruction = match[1].trim();
  return (
    <div className="mb-3 rounded-xl border-2 border-[#1B2A4A]/30 bg-[#1B2A4A]/5 px-3 py-2.5">
      <div className="flex items-center gap-1.5 mb-1.5">
        <Pencil className="h-3 w-3 text-[#1B2A4A]" />
        <span className="text-[9px] font-bold text-[#1B2A4A] uppercase tracking-widest">Revision Request</span>
      </div>
      <p className="text-[11px] text-[#1B2A4A] font-medium leading-relaxed">{instruction}</p>
    </div>
  );
}

// ─── Edit summary card ─────────────────────────────────────────────────────────
// Derives a concise summary of what was changed from the tool calls list.
function EditSummaryCard({ toolCalls }: { toolCalls: ToolCallEntry[] }) {
  const edits = toolCalls.filter(tc => tc.tool === "edit_file");
  const writes = toolCalls.filter(tc => tc.tool === "write_file");
  const reads = toolCalls.filter(tc => tc.tool === "read_file" || tc.tool === "grep");
  if (edits.length === 0 && writes.length === 0) return null;
  return (
    <div className="mb-3 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2.5">
      <div className="flex items-center gap-1.5 mb-1.5">
        <CheckCircle2 className="h-3 w-3 text-emerald-600" />
        <span className="text-[9px] font-bold text-emerald-700 uppercase tracking-widest">Changes Applied</span>
      </div>
      <div className="flex flex-wrap gap-2">
        {edits.length > 0 && (
          <span className="text-[10px] font-semibold text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded-full">
            {edits.length} surgical edit{edits.length !== 1 ? "s" : ""}
          </span>
        )}
        {writes.length > 0 && (
          <span className="text-[10px] font-semibold text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded-full">
            {writes.length} full rewrite{writes.length !== 1 ? "s" : ""}
          </span>
        )}
        {reads.length > 0 && (
          <span className="text-[10px] text-emerald-600 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">
            {reads.length} read/scan{reads.length !== 1 ? "s" : ""}
          </span>
        )}
      </div>
    </div>
  );
}

// ─── Validation result card ────────────────────────────────────────────────────
// Shows the post-revision validation outcome (html_static + html_render).
function ValidationResultCard({ passed, issues }: { passed?: boolean; issues?: ValidationIssue[] }) {
  const [open, setOpen] = useState(false);
  if (passed === undefined && (!issues || issues.length === 0)) return null;
  const hasIssues = issues && issues.length > 0;
  const isPassed = passed === true && !hasIssues;
  return (
    <div className={`mb-3 rounded-xl border px-3 py-2.5 ${isPassed ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50"}`}>
      <button onClick={() => hasIssues && setOpen(v => !v)} className="w-full flex items-center gap-1.5 text-left">
        {isPassed
          ? <CheckCircle2 className="h-3 w-3 text-emerald-600 flex-shrink-0" />
          : <AlertTriangle className="h-3 w-3 text-amber-600 flex-shrink-0" />}
        <span className={`text-[9px] font-bold uppercase tracking-widest ${isPassed ? "text-emerald-700" : "text-amber-700"}`}>
          Validation {isPassed ? "Passed" : passed === false ? "Blocked" : "Issues Found"}
        </span>
        {hasIssues && (
          <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-medium ml-1 ${isPassed ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>
            {issues!.length} issue{issues!.length !== 1 ? "s" : ""}
          </span>
        )}
        {hasIssues && <ChevronDown className={`h-3 w-3 text-gray-400 ml-auto transition-transform ${open ? "rotate-180" : ""}`} />}
      </button>
      {open && hasIssues && (
        <div className="mt-2 space-y-1">
          {issues!.map((issue, i) => (
            <div key={i} className="flex items-start gap-1.5 rounded-lg bg-white border border-amber-100 px-2.5 py-1.5">
              <span className={`text-[8px] font-bold uppercase px-1 py-0.5 rounded flex-shrink-0 mt-0.5 ${
                issue.severity === "CRITICAL" ? "bg-red-100 text-red-700" :
                issue.severity === "HIGH" ? "bg-orange-100 text-orange-700" :
                issue.severity === "MEDIUM" ? "bg-amber-100 text-amber-700" :
                "bg-gray-100 text-gray-600"
              }`}>{issue.severity}</span>
              <p className="text-[10px] text-gray-700 leading-snug">{issue.message}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Context sources row ──────────────────────────────────────────────────────
export function ContextSourcesRow({ sources }: { sources: ContextSource[] }) {
  return (
    <div className="mb-3 rounded-xl border border-[#1B2A4A]/20 bg-[#E8EDF5]/60 px-3 py-2.5">
      <div className="flex items-center gap-1.5 mb-2">
        <Database className="h-3 w-3 text-[#1B2A4A]" />
        <span className="text-[9px] font-bold text-[#1B2A4A] uppercase tracking-widest">Context Received</span>
        <span className="text-[9px] bg-[#1B2A4A]/10 text-[#1B2A4A] px-1.5 py-0.5 rounded-full font-medium ml-auto">{sources.length} source{sources.length !== 1 ? "s" : ""}</span>
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
            <div key={i} className="flex items-center gap-1.5 bg-white border border-[#1B2A4A]/20 shadow-sm rounded-lg px-2.5 py-1.5">
              <Layers className="h-2.5 w-2.5 text-[#1B2A4A] flex-shrink-0" />
              <span className="text-[10px] font-semibold text-[#1B2A4A] truncate max-w-[140px]">{label}</span>
              {size && <span className="text-[9px] text-[#1B2A4A]/60 font-mono">{size}</span>}
              {compression != null && compression > 0 && (
                <span className="text-[9px] bg-[#1B2A4A]/10 text-[#1B2A4A] px-1 rounded font-medium">-{compression}%</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Tool calls section ───────────────────────────────────────────────────────
export function ToolCallsSection({ toolCalls }: { toolCalls: ToolCallEntry[] }) {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  // Collapse the whole section by default when there are many tool calls
  const [sectionOpen, setSectionOpen] = useState(toolCalls.length <= 5);
  return (
    <div className="mb-3">
      <button
        onClick={() => setSectionOpen(v => !v)}
        className="flex items-center gap-1.5 mb-2 w-full text-left hover:text-gray-600 transition-colors"
      >
        <Wrench className="h-3 w-3 text-gray-400 flex-shrink-0" />
        <span className="text-[9px] font-bold text-gray-400 uppercase tracking-widest">Tool Calls</span>
        <span className="text-[9px] bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded-full font-medium">{toolCalls.length}</span>
        <ChevronDown className={`h-3 w-3 text-gray-300 ml-auto flex-shrink-0 transition-transform ${sectionOpen ? "rotate-180" : ""}`} />
      </button>
      {sectionOpen && (
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
                        {JSON.stringify(tc.args, null, 2)}
                      </pre>
                    </div>
                  )}
                  {tc.result != null && (
                    <div className="px-3 py-2">
                      <p className="text-[9px] font-semibold text-[#1B2A4A] uppercase tracking-wider mb-1">Result</p>
                      <pre className="text-[9px] text-gray-600 font-mono whitespace-pre-wrap leading-relaxed max-h-[200px] overflow-y-auto">
                        {tc.result}
                      </pre>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Input prompt section ─────────────────────────────────────────────────────
export function InputPromptSection({ prompt }: { prompt: string }) {
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
          <pre className="text-[9px] text-gray-600 whitespace-pre-wrap leading-relaxed p-3 max-h-[500px] overflow-y-auto font-mono bg-white">
            {prompt}
          </pre>
        </div>
      )}
    </div>
  );
}

// ─── Output preview section ───────────────────────────────────────────────────
export function OutputPreviewSection({ output, agentId }: { output: string; agentId: string }) {
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
          <pre className="text-[9px] text-gray-600 whitespace-pre-wrap leading-relaxed p-3 max-h-[500px] overflow-y-auto font-mono bg-gray-50">
            {output}
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
    <div ref={refCallback} className={`rounded-xl border overflow-hidden transition-all ${
      isRunning ? `${color.border} shadow-sm` :
      isDone ? "border-gray-100" :
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
        {/* Avatar — matches prototype phase icon style */}
        <div className={`w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 ${
          isRunning ? `${color.bg} ${color.text}` :
          isDone ? "bg-[#E8EDF5] text-[#1B2A4A]" :
          isError ? "bg-red-50 text-red-500" :
          "bg-gray-100 text-gray-400"
        }`}>
          {isDone ? <CheckCircle2 className="h-4 w-4" /> :
           isError ? <XCircle className="h-4 w-4" /> :
           agent.icon && agent.icon !== "🤖" ? <span className="text-[13px]">{agent.icon}</span> :
           <span className="text-[11px] font-bold">{initials}</span>}
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
        <div className={`px-4 py-2 border-t ${color.border} ${color.bg}/30`}>
          <div className="flex items-center gap-1.5 mb-1">
            <Brain className={`h-3 w-3 ${color.text}`} />
            <span className={`text-[9px] font-bold uppercase tracking-widest ${color.text}`}>Reasoning (live)</span>
          </div>
          <p className="text-[10px] text-gray-700 leading-relaxed font-mono max-h-[200px] overflow-y-auto">
            {agent.thinkingText}
            <span className="animate-pulse">▌</span>
          </p>
        </div>
      )}

      {/* Expanded body */}
      {expanded && hasContent && (
        <div className="border-t border-gray-100 px-4 py-3 bg-white space-y-0">
          {/* KAN-81: revision-specific diagnostics shown first */}
          {agent.inputPrompt && <RevisionInstructionCard prompt={agent.inputPrompt} />}
          {agent.toolCalls && agent.toolCalls.length > 0 && (
            <EditSummaryCard toolCalls={agent.toolCalls} />
          )}
          <ValidationResultCard passed={agent.validationPassed} issues={agent.validationIssues} />
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
  );
}

// Token usage is rendered via the shared TokenUsageSummary card (see main export),
// replacing the former bespoke TokenSummary so all pipelines use one component.

// ─── Main export ──────────────────────────────────────────────────────────────
export function AgentThinkingTab({ agents, pipelineState, runInput, originalBriefRootRunId, revisionParentVersion, clarifications, clarificationsLoading }: AgentThinkingTabProps) {
  const runningRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    runningRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [agents]);

  // Workstream C2 — the run input / clarify rounds are also first-class timeline
  // data, so a run with only inputs (no agents yet) must NOT short-circuit to the
  // EmptyState. Additive to the existing conditions (both props new/optional).
  const resolvedClarifications = clarifications ?? pipelineState?.clarifications;
  const hasAnyData = pipelineState?.plannerStatus ||
    agents.some(a => a.thinkingText || (a.toolCalls?.length ?? 0) > 0 || a.inputPrompt || a.status !== "idle") ||
    !!runInput || (resolvedClarifications?.length ?? 0) > 0;

  if (!hasAnyData) return <EmptyState />;

  // ── Spec Kit prototype pipeline: use rich visualization ──────────────────
  const isPrototypePipeline = agents.some(a =>
    ["prototype-specify", "prototype-plan", "prototype-analyze", "prototype-build", "prototype-validate"].includes(a.id)
  );
  if (isPrototypePipeline) {
    // Workstream C2 (byv FIX-1): the prototype pipeline must ALSO show the run's
    // Starting point → Clarifications preamble ABOVE the phase view (both live-
    // after-build-starts AND every reopen). Reuse the SAME already-authored cards
    // and prop expressions as the main render below — no re-authoring, no new props.
    return (
      <div className="flex flex-col h-full overflow-hidden">
        <div className="flex-shrink-0 px-4 py-4 space-y-3">
          <StartingPointCard
            input={runInput}
            originalBriefRootRunId={originalBriefRootRunId}
            revisionParentVersion={revisionParentVersion}
          />
          <ClarificationsCard clarifications={resolvedClarifications} loading={clarificationsLoading} />
        </div>
        <div className="flex-1 min-h-0">
          <PrototypePipelineView agents={agents} pipelineState={pipelineState} />
        </div>
      </div>
    );
  }

  const visibleAgents = agents.filter(a => a.status !== "idle" || (a.inputPrompt || (a.toolCalls?.length ?? 0) > 0));

  // Derive a friendly pipeline label from agent ids (matches PrototypePipelineView style)
  const pipelineLabel = (() => {
    const ids = agents.map(a => a.id);
    if (ids.some(id => id.includes("user_stories") || id.includes("domain-analyst") || id.includes("epic-architect") || id.includes("backlog"))) return "User Stories Pipeline";
    if (ids.some(id => id.includes("ppt") || id.includes("presentation"))) return "Presentation Pipeline";
    if (ids.some(id => id.includes("app-builder") || id.includes("sdlc"))) return "App Builder Pipeline";
    if (ids.some(id => id.includes("mulesoft"))) return "Mulesoft Migration Pipeline";
    if (ids.some(id => id.includes("dotnet"))) return ".NET Migration Pipeline";
    if (ids.some(id => id === "prototype-revision-agent")) return "Prototype Revision Pipeline";
    return "Pipeline";
  })();

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <PipelineHeader pipelineState={pipelineState} workflowLabel={pipelineLabel} />

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {/* Workstream C2 (POR §5 D3) — the run's starting point, BEFORE the Planner */}
        <StartingPointCard
          input={runInput}
          originalBriefRootRunId={originalBriefRootRunId}
          revisionParentVersion={revisionParentVersion}
        />

        {/* Planner step */}
        {pipelineState && (
          <PlannerCard pipelineState={pipelineState} />
        )}

        {/* Workstream C2 (POR §5 D4) — the clarify exchange, AFTER the Planner */}
        <ClarificationsCard clarifications={resolvedClarifications} loading={clarificationsLoading} />

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

        {/* All done state — matches prototype complete indicator */}
        {pipelineState && !pipelineState.isRunning && visibleAgents.length > 0 &&
          visibleAgents.every(a => a.status === "done" || a.status === "error") && (
          <div className="flex items-center gap-2 py-2">
            <div className="w-6 h-6 rounded-full bg-[#1B2A4A] flex items-center justify-center flex-shrink-0">
              <CheckCircle2 className="h-3.5 w-3.5 text-white" />
            </div>
            <span className="text-[11px] font-semibold text-[#1B2A4A]">Pipeline complete</span>
            {pipelineState.totalDuration != null && (
              <span className="text-[10px] text-gray-400">in {pipelineState.totalDuration.toFixed(1)}s</span>
            )}
          </div>
        )}
      </div>

      {pipelineState && (
        <div className="flex-shrink-0 border-t border-gray-100 px-4 py-2 bg-gray-50/50">
          <TokenUsageSummary pipelineState={pipelineState} modelId={pipelineState.modelId} />
        </div>
      )}
    </div>
  );
}
