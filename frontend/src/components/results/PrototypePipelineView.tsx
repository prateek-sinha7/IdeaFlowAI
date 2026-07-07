"use client";

/**
 * PrototypePipelineView — Rich visualization of the Spec Kit prototype pipeline.
 *
 * Shows the full Approach 2+3 flow in the Thinking tab:
 *   Phase 1: Spec Writer  → spec document rendered as a page map
 *   Phase 2: Task Planner → task list rendered as a checklist
 *   Phase 3: Build Agent  → build progress with task-by-task status
 *   Phase 4: Validate     → validation results
 *
 * Parses <spec>...</spec> and <tasks>...</tasks> from agent outputs
 * and renders them as interactive visual cards.
 */

import { useState } from "react";
import {
  FileText, ListChecks, Hammer, CheckCircle2, XCircle,
  ChevronDown, ChevronRight, Zap, Clock, Cpu,
  Map, Layout, ArrowRight,
  Loader2, Circle, Brain,
} from "lucide-react";
import type { AgentRunState } from "@/types/index";
import {
  ContextSourcesRow,
  ToolCallsSection,
  InputPromptSection,
  OutputPreviewSection,
} from "./AgentThinkingTab";

// ─── Types ────────────────────────────────────────────────────────────────────

interface SpecPage {
  id: string;
  route: string;
  purpose: string;
}

interface ParsedSpec {
  title: string;
  overview?: string;
  pages: SpecPage[];
  raw: string;
}

interface ParsedTask {
  number: number;
  title: string;
  goal: string;
  requirements: string[];
}

interface ParsedTasks {
  tasks: ParsedTask[];
  raw: string;
}

// ─── Parsers ──────────────────────────────────────────────────────────────────

function parseSpec(output: string): ParsedSpec | null {
  const match = output.match(/<spec>([\s\S]*?)<\/spec>/i);
  if (!match) return null;
  const raw = match[1].trim();

  // Extract title
  const titleMatch = raw.match(/^#\s+(?:Prototype Specification:\s*)?(.+)/m);
  const title = titleMatch ? titleMatch[1].trim() : "Prototype Specification";

  // Extract overview
  const overviewMatch = raw.match(/##\s+Overview\s*\n([\s\S]*?)(?=\n##|\n$|$)/);
  const overview = overviewMatch ? overviewMatch[1].trim().slice(0, 200) : undefined;

  // Extract pages from ## Pages & Navigation section
  const pagesSection = raw.match(/##\s+Pages[^#]*([\s\S]*?)(?=\n##|$)/);
  const pages: SpecPage[] = [];
  if (pagesSection) {
    const pageLines = pagesSection[1].matchAll(/[-*]\s+\*?\*?([^*\n]+)\*?\*?\s*[—–-]\s*([^\n]+)/g);
    for (const m of pageLines) {
      const idRoute = m[1].trim();
      const purpose = m[2].trim();
      const routeMatch = idRoute.match(/`(#\/[^`]+)`/);
      const idMatch = idRoute.match(/\*\*([^*]+)\*\*/);
      pages.push({
        id: idMatch ? idMatch[1] : idRoute.replace(/`.*`/, "").trim(),
        route: routeMatch ? routeMatch[1] : "",
        purpose: purpose.slice(0, 80),
      });
    }
  }

  // Fallback: extract from Page Specifications section
  if (pages.length === 0) {
    const specSections = raw.matchAll(/###\s+([^\n(]+)\s*\(`(#\/[^`]+)`\)/g);
    for (const m of specSections) {
      pages.push({ id: m[1].trim(), route: m[2].trim(), purpose: "" });
    }
  }

  return { title, overview, pages, raw };
}

function parseTasks(output: string): ParsedTasks | null {
  // Try <tasks>...</tasks> wrapper first, fall back to raw output
  const match = output.match(/<tasks>([\s\S]*?)<\/tasks>/i);
  const raw = match ? match[1].trim() : output.trim();

  // Must have at least one ## Task N: block to be valid
  if (!raw.match(/##\s+Task\s+\d+/)) return null;

  const tasks: ParsedTask[] = [];
  const taskBlocks = raw.split(/(?=##\s+Task\s+\d+)/);

  for (const block of taskBlocks) {
    const numMatch = block.match(/##\s+Task\s+(\d+)[:\s]+(.+)/);
    if (!numMatch) continue;
    const number = parseInt(numMatch[1]);
    const title = numMatch[2].trim().replace(/\*\*/g, "");

    const goalMatch = block.match(/\*\*Goal\*\*:\s*(.+)/);
    const goal = goalMatch ? goalMatch[1].trim() : "";

    // Try multiple requirement section names
    const reqSection = block.match(/\*\*(?:Key requirements|Requirements|Output|Components)\*\*:([\s\S]*?)(?=\n##|\n\*\*|$)/);
    const requirements: string[] = [];
    if (reqSection) {
      const reqs = reqSection[1].matchAll(/[-*]\s+(.+)/g);
      for (const r of reqs) requirements.push(r[1].trim().slice(0, 100));
    }

    tasks.push({ number, title, goal, requirements });
  }

  if (tasks.length === 0) return null;
  return { tasks, raw };
}

// ─── Phase cards ──────────────────────────────────────────────────────────────

function PhaseCard({
  number, icon: Icon, label, color, status, children, defaultOpen = false,
}: {
  number: number;
  icon: React.ElementType;
  label: string;
  color: { bg: string; text: string; border: string };
  status: "idle" | "running" | "done" | "error";
  children?: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className={`rounded-xl border overflow-hidden transition-all ${
      status === "running" ? `${color.border} shadow-sm` :
      status === "done" ? "border-gray-100" :
      status === "error" ? "border-red-100" :
      "border-gray-100 opacity-50"
    }`}>
      <button
        onClick={() => children && setOpen(v => !v)}
        className={`w-full flex items-center gap-3 px-4 py-3 text-left transition-colors ${
          children ? "hover:bg-gray-50/50 cursor-pointer" : "cursor-default"
        } bg-white`}
      >
        {/* Phase number + icon */}
        <div className={`w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 ${
          status === "running" ? `${color.bg} ${color.text}` :
          status === "done" ? "bg-[#E8EDF5] text-[#1B2A4A]" :
          status === "error" ? "bg-red-50 text-red-500" :
          "bg-gray-100 text-gray-400"
        }`}>
          {status === "done" ? <CheckCircle2 className="h-4 w-4" /> :
           status === "error" ? <XCircle className="h-4 w-4" /> :
           status === "running" ? <Icon className="h-4 w-4" /> :
           <Icon className="h-4 w-4" />}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">Phase {number}</span>
            {status === "running" && (
              <span className={`flex items-center gap-1 text-[9px] font-bold px-1.5 py-0.5 rounded-full ${color.bg} ${color.text}`}>
                <Zap className="h-2.5 w-2.5" />LIVE
              </span>
            )}
          </div>
          <p className={`text-[12px] font-semibold ${status === "idle" ? "text-gray-400" : "text-gray-900"}`}>
            {label}
          </p>
        </div>

        {children && (
          <ChevronDown className={`h-4 w-4 text-gray-400 flex-shrink-0 transition-transform ${open ? "rotate-180" : ""}`} />
        )}
      </button>

      {open && children && (
        <div className="border-t border-gray-100">
          {children}
        </div>
      )}
    </div>
  );
}

// ─── Agent detail section — FR-015 data (prompt, context, tools, output) ─────
// Renders the full thinking-tab detail for one prototype phase agent, using the
// same shared sub-components as AgentThinkingTab's generic view (INV-12).
function AgentDetailSection({ agent }: { agent: AgentRunState }) {
  const hasDetail =
    (agent.contextSources && agent.contextSources.length > 0) ||
    (agent.toolCalls && agent.toolCalls.length > 0) ||
    agent.inputPrompt ||
    (agent.status === "done" && agent.output && agent.output.trim().length > 0) ||
    (agent.status === "thinking" && agent.thinkingText);

  if (!hasDetail) return null;

  return (
    <div className="border-t border-gray-100 px-4 py-3 bg-white space-y-0">
      {/* Live thinking stream */}
      {(agent.status === "running" || agent.status === "thinking") && agent.thinkingText && (
        <div className="mb-3 rounded-lg bg-[#E8EDF5]/50 px-3 py-2">
          <div className="flex items-center gap-1.5 mb-1">
            <Brain className="h-3 w-3 text-[#1B2A4A]" />
            <span className="text-[9px] font-bold uppercase tracking-widest text-[#1B2A4A]">Reasoning (live)</span>
          </div>
          <p className="text-[10px] text-gray-700 leading-relaxed font-mono max-h-[200px] overflow-y-auto">
            {agent.thinkingText}
            <span className="animate-pulse">▌</span>
          </p>
        </div>
      )}
      {agent.contextSources && agent.contextSources.length > 0 && (
        <ContextSourcesRow sources={agent.contextSources} />
      )}
      {agent.toolCalls && agent.toolCalls.length > 0 && (
        <ToolCallsSection toolCalls={agent.toolCalls} />
      )}
      {agent.inputPrompt && (
        <InputPromptSection prompt={agent.inputPrompt} />
      )}
      {agent.status === "done" && agent.output && agent.output.trim().length > 0 && (
        <div className="mt-3 pt-3 border-t border-gray-100">
          <OutputPreviewSection output={agent.output} agentId={agent.id} />
        </div>
      )}
    </div>
  );
}



function SpecVisualization({ spec }: { spec: ParsedSpec }) {
  const [showRaw, setShowRaw] = useState(false);

  return (
    <div className="px-4 py-3 space-y-3 bg-white">
      {/* Title */}
      <div className="flex items-center gap-2">
        <FileText className="h-3.5 w-3.5 text-[#1B2A4A] flex-shrink-0" />
        <p className="text-[12px] font-bold text-gray-900">{spec.title}</p>
      </div>

      {/* Overview */}
      {spec.overview && (
        <p className="text-[11px] text-gray-500 leading-relaxed">{spec.overview}</p>
      )}

      {/* Page map */}
      {spec.pages.length > 0 && (
        <div>
          <div className="flex items-center gap-1.5 mb-2">
            <Map className="h-3 w-3 text-gray-400" />
            <span className="text-[9px] font-bold text-gray-400 uppercase tracking-widest">
              {spec.pages.length} Pages
            </span>
          </div>
          <div className="grid grid-cols-1 gap-1.5">
            {spec.pages.map((page, i) => (
              <div key={i} className="flex items-start gap-2.5 rounded-lg bg-[#E8EDF5] border border-[#E8EDF5] px-3 py-2">
                <div className="w-5 h-5 rounded-md bg-[#E8EDF5] flex items-center justify-center flex-shrink-0 mt-0.5">
                  <Layout className="h-2.5 w-2.5 text-[#1B2A4A]" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] font-semibold text-[#1B2A4A]">{page.id}</span>
                    {page.route && (
                      <span className="text-[9px] font-mono text-[#1B2A4A] bg-[#E8EDF5] px-1.5 py-0.5 rounded">{page.route}</span>
                    )}
                  </div>
                  {page.purpose && (
                    <p className="text-[10px] text-[#1B2A4A] mt-0.5 leading-snug">{page.purpose}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Raw spec toggle */}
      <button
        onClick={() => setShowRaw(v => !v)}
        className="flex items-center gap-1.5 text-[9px] font-semibold text-gray-400 uppercase tracking-widest hover:text-gray-600 transition-colors"
      >
        <ChevronRight className={`h-3 w-3 transition-transform ${showRaw ? "rotate-90" : ""}`} />
        Full Spec Document
      </button>
      {showRaw && (
        <pre className="text-[9px] text-gray-600 whitespace-pre-wrap leading-relaxed bg-gray-50 rounded-lg p-3 max-h-[500px] overflow-y-auto font-mono border border-gray-100">
          {spec.raw}
        </pre>
      )}
    </div>
  );
}

// ─── Task list visualization ──────────────────────────────────────────────────

function TaskListVisualization({ tasks, currentTaskIndex, allDone }: {
  tasks: ParsedTask[];
  currentTaskIndex: number;
  allDone: boolean;
}) {
  return (
    <div className="px-4 py-3 space-y-2 bg-white">
      <div className="flex items-center gap-1.5 mb-1">
        <ListChecks className="h-3.5 w-3.5 text-[#1B2A4A]" />
        <span className="text-[11px] font-bold text-gray-700">{tasks.length} Build Tasks</span>
        <span className="text-[9px] text-gray-400 ml-auto">
          {allDone ? `${tasks.length}/${tasks.length} done` : currentTaskIndex >= 0 ? `${currentTaskIndex}/${tasks.length} done` : ""}
        </span>
      </div>

      {tasks.map((task, i) => {
        const isDone = allDone || i < currentTaskIndex;
        const isActive = !allDone && i === currentTaskIndex;

        return (
          <div key={i} className={`flex items-start gap-2.5 rounded-lg px-3 py-2 border transition-all ${
            isDone ? "bg-[#E8EDF5] border-[#E8EDF5]" :
            isActive ? "bg-[#E8EDF5] border-[#1B2A4A]/20 shadow-sm" :
            "bg-gray-50 border-gray-100 opacity-60"
          }`}>
            <div className="flex-shrink-0 mt-0.5">
              {isDone ? <CheckCircle2 className="h-4 w-4 text-[#1B2A4A]" /> :
               isActive ? <Loader2 className="h-4 w-4 text-[#1B2A4A] animate-spin" /> :
               <Circle className="h-4 w-4 text-gray-300" />}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className={`text-[9px] font-bold uppercase tracking-wider ${
                  isDone ? "text-[#1B2A4A]" : isActive ? "text-[#1B2A4A]" : "text-gray-400"
                }`}>Task {task.number}</span>
              </div>
              <p className={`text-[11px] font-semibold leading-snug ${
                isDone ? "text-[#1B2A4A]" : isActive ? "text-[#1B2A4A]" : "text-gray-500"
              }`}>{task.title}</p>
              {task.goal && (
                <p className={`text-[10px] mt-0.5 leading-snug ${
                  isDone ? "text-[#1B2A4A]" : isActive ? "text-[#1B2A4A]" : "text-gray-400"
                }`}>{task.goal}</p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

interface PrototypePipelineViewProps {
  agents: AgentRunState[];
  pipelineState?: import("@/types/index").PipelineRunState;
}

export function PrototypePipelineView({ agents, pipelineState }: PrototypePipelineViewProps) {
  // Find each phase agent
  const specAgent = agents.find(a => a.id === "prototype-specify");
  const planAgent = agents.find(a => a.id === "prototype-plan");
  const analyzeAgent = agents.find(a => a.id === "prototype-analyze");
  const buildAgent = agents.find(a => a.id === "prototype-build");
  const validateAgent = agents.find(a => a.id === "prototype-validate");

  // Parse spec from spec agent output
  const spec = specAgent?.output ? parseSpec(specAgent.output) : null;

  // Parse tasks from plan agent output
  const tasksData = planAgent?.output ? parseTasks(planAgent.output) : null;

  // Determine current build task from real-time task_progress events
  // pipelineState.protoCompletedTaskCount is updated by report_task_complete tool calls
  const realtimeCompletedCount = pipelineState?.protoCompletedTaskCount ?? 0;
  const buildIsRunning = buildAgent?.status === "running" || buildAgent?.status === "thinking";
  const totalTasks = tasksData?.tasks.length ?? 0;

  // Phase statuses
  const getStatus = (agent?: AgentRunState): "idle" | "running" | "done" | "error" => {
    if (!agent) return "idle";
    if (agent.status === "running" || agent.status === "thinking") return "running";
    if (agent.status === "done") return "done";
    if (agent.status === "error") return "error";
    return "idle";
  };

  const specStatus = getStatus(specAgent);
  const planStatus = getStatus(planAgent);
  const analyzeStatus = getStatus(analyzeAgent);
  const buildStatus = getStatus(buildAgent);
  const validateStatus = getStatus(validateAgent);

  // FIX-2 (byv): the backend emits agent_complete{prototype-build} at the END of
  // EACH build task (INV-3 parity-locked), so buildStatus flips to "done"
  // TRANSIENTLY between tasks while the run is still going. Derive a TRUE terminal
  // signal: build is done AND either a later phase started (validateStatus left
  // "idle") OR the whole run has ended (pipelineState.isRunning === false). Build
  // may be the LAST agent (no validate phase), so isRunning === false is the
  // load-bearing clause. A transient between-task "done" MUST NOT mark all complete.
  const buildTrulyDone =
    buildStatus === "done" &&
    (validateStatus !== "idle" || pipelineState?.isRunning === false);

  // Real-time: use the actual completed count from tool calls.
  // Truly done → all tasks complete. Running OR the transient between-task "done"
  // window → show the real completed count, but CAPPED at totalTasks-1 so the
  // last task stays in "active" (spinner) state until buildTrulyDone — otherwise
  // the last task_progress event (fired BEFORE the build agent's fix-loop and
  // agent_complete) would mark all tasks checked while the agent is still running
  // (KAN-99). Idle → -1.
  const currentTaskIndex = buildTrulyDone
    ? totalTasks
    : buildIsRunning || (buildStatus === "done" && !buildTrulyDone)
    ? Math.min(realtimeCompletedCount, Math.max(0, totalTasks - 1))
    : -1;

  // Token totals
  const totalTokens = agents.reduce((s, a) => s + (a.totalTokens ?? 0), 0);
  const totalDuration = agents.reduce((s, a) => s + (a.duration ?? 0), 0);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex-shrink-0 px-4 pt-4 pb-3 border-b border-gray-100 bg-white">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${
              agents.some(a => a.status === "running" || a.status === "thinking") ? "bg-[#1B2A4A] animate-pulse" :
              agents.some(a => a.status === "error") ? "bg-red-400" :
              agents.some(a => a.status === "done") ? "bg-[#1B2A4A]" : "bg-gray-300"
            }`} />
            <span className="text-[11px] font-semibold text-gray-700 uppercase tracking-wider">
              Prototype Pipeline
            </span>
          </div>
          <div className="flex items-center gap-3 text-[10px] text-gray-400">
            {totalTokens > 0 && (
              <span className="flex items-center gap-1">
                <Cpu className="h-3 w-3" />{(totalTokens / 1000).toFixed(1)}k tokens
              </span>
            )}
            {totalDuration > 0 && (
              <span className="flex items-center gap-1">
                <Clock className="h-3 w-3" />{totalDuration.toFixed(0)}s
              </span>
            )}
          </div>
        </div>

        {/* Phase progress bar */}
        <div className="flex items-center gap-1">
          {[specStatus, planStatus, analyzeStatus, buildStatus, validateStatus].map((s, i) => (
            <div key={i} className={`h-1.5 flex-1 rounded-full transition-all ${
              s === "done" ? "bg-[#1B2A4A]" :
              s === "running" ? "bg-[#1B2A4A] animate-pulse" :
              s === "error" ? "bg-red-400" :
              "bg-gray-200"
            }`} />
          ))}
        </div>
      </div>

      {/* Phase cards */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">

        {/* Phase 1: Spec Writer */}
        <PhaseCard
          number={1}
          icon={FileText}
          label="Spec Writer — Specification"
          color={{ bg: "bg-[#E8EDF5]", text: "text-[#1B2A4A]", border: "border-[#1B2A4A]/20" }}
          status={specStatus}
          defaultOpen={specStatus === "done" && !!spec}
        >
          {specStatus === "running" && (
            <div className="px-4 py-3 bg-[#E8EDF5]/50 flex items-center gap-2">
              <Loader2 className="h-3.5 w-3.5 text-[#1B2A4A] animate-spin" />
              <p className="text-[11px] text-[#1B2A4A]">Analyzing brief and writing specification…</p>
            </div>
          )}
          {spec && <SpecVisualization spec={spec} />}
          {specStatus === "done" && !spec && (
            <div className="px-4 py-3 text-[11px] text-gray-500">Spec generated — no structured pages found.</div>
          )}
          {specAgent && <AgentDetailSection agent={specAgent} />}
        </PhaseCard>

        {/* Connector */}
        {(planStatus !== "idle" || specStatus === "done") && (
          <div className="flex items-center gap-2 pl-4">
            <ArrowRight className="h-3.5 w-3.5 text-gray-300" />
            <span className="text-[9px] text-gray-400">Spec passed to Task Planner</span>
          </div>
        )}

        {/* Phase 2: Task Planner */}
        <PhaseCard
          number={2}
          icon={ListChecks}
          label="Task Planner — Build Decomposition"
          color={{ bg: "bg-[#E8EDF5]", text: "text-[#1B2A4A]", border: "border-[#1B2A4A]/20" }}
          status={planStatus}
          defaultOpen={planStatus === "done"}
        >
          {planStatus === "running" && (
            <div className="px-4 py-3 bg-[#E8EDF5]/50 flex items-center gap-2">
              <Loader2 className="h-3.5 w-3.5 text-[#1B2A4A] animate-spin" />
              <p className="text-[11px] text-[#1B2A4A]">Decomposing spec into atomic build tasks…</p>
            </div>
          )}
          {tasksData && (
            <TaskListVisualization
              tasks={tasksData.tasks}
              currentTaskIndex={buildStatus === "idle" ? -1 : currentTaskIndex}
              allDone={buildTrulyDone}
            />
          )}
          {planStatus === "done" && !tasksData && planAgent?.output && (
            <div className="px-4 py-3 bg-white">
              <p className="text-[10px] text-gray-500 mb-2">Task list generated (raw format):</p>
              <pre className="text-[9px] text-gray-600 whitespace-pre-wrap leading-relaxed bg-gray-50 rounded-lg p-3 max-h-[500px] overflow-y-auto font-mono border border-gray-100">
                {planAgent.output}
              </pre>
            </div>
          )}
          {planAgent && <AgentDetailSection agent={planAgent} />}
        </PhaseCard>

        {/* Connector */}
        {(analyzeStatus !== "idle" || planStatus === "done") && (
          <div className="flex items-center gap-2 pl-4">
            <ArrowRight className="h-3.5 w-3.5 text-gray-300" />
            <span className="text-[9px] text-gray-400">Spec & tasks passed to Analyzer</span>
          </div>
        )}

        {/* Phase 3: Spec Kit Analyzer */}
        <PhaseCard
          number={3}
          icon={CheckCircle2}
          label="Spec Kit Analyzer — Quality Analysis"
          color={{ bg: "bg-[#E8EDF5]", text: "text-[#1B2A4A]", border: "border-[#1B2A4A]/20" }}
          status={analyzeStatus}
          defaultOpen={analyzeStatus === "done" && !!analyzeAgent?.output}
        >
          {analyzeStatus === "running" && (
            <div className="px-4 py-3 bg-[#E8EDF5]/50 flex items-center gap-2">
              <Loader2 className="h-3.5 w-3.5 text-[#1B2A4A] animate-spin" />
              <p className="text-[11px] text-[#1B2A4A]">Analyzing spec and task list for consistency and gaps…</p>
            </div>
          )}
          {analyzeStatus === "done" && analyzeAgent?.output && (
            <div className="px-4 py-3 bg-white">
              <p className="text-[10px] text-gray-500 mb-1">Analysis complete — awaiting or approved.</p>
              <pre className="text-[9px] text-gray-600 whitespace-pre-wrap leading-relaxed bg-gray-50 rounded-lg p-3 max-h-[200px] overflow-y-auto font-mono border border-gray-100">
                {analyzeAgent.output.replace(/<\/?analysis>/gi, "").trim().slice(0, 1500)}
              </pre>
            </div>
          )}
          {analyzeAgent && <AgentDetailSection agent={analyzeAgent} />}
        </PhaseCard>

        {/* Connector */}
        {(buildStatus !== "idle" || analyzeStatus === "done") && (
          <div className="flex items-center gap-2 pl-4">
            <ArrowRight className="h-3.5 w-3.5 text-gray-300" />
            <span className="text-[9px] text-gray-400">
              {tasksData ? `${tasksData.tasks.length} tasks passed to Build Agent` : "Tasks passed to Build Agent"}
            </span>
          </div>
        )}

        {/* Phase 4: Build Agent */}
        <PhaseCard
          number={4}
          icon={Hammer}
          label="Build Agent — Incremental Construction"
          color={{ bg: "bg-[#E8EDF5]", text: "text-[#1B2A4A]", border: "border-[#1B2A4A]/20" }}
          status={buildStatus}
          defaultOpen={buildStatus === "running" || buildStatus === "done"}
        >
          {(buildIsRunning || (buildStatus === "done" && !buildTrulyDone)) && tasksData && (
            <div className="px-4 py-3 bg-[#E8EDF5]/50 space-y-2">
              <div className="flex items-center gap-2">
                <Loader2 className="h-3.5 w-3.5 text-[#1B2A4A] animate-spin" />
                <p className="text-[11px] text-[#1B2A4A] font-medium">
                  {realtimeCompletedCount > 0
                    ? `Completed ${realtimeCompletedCount}/${tasksData.tasks.length} tasks…`
                    : "Building prototype…"}
                </p>
              </div>
              {/* Show current active task */}
              {tasksData.tasks[realtimeCompletedCount] && (
                <div className="rounded-lg bg-[#E8EDF5] border border-[#1B2A4A]/20 px-3 py-2">
                  <p className="text-[10px] font-bold text-[#1B2A4A]">
                    Task {tasksData.tasks[realtimeCompletedCount].number}: {tasksData.tasks[realtimeCompletedCount].title}
                  </p>
                  <p className="text-[10px] text-[#1B2A4A] mt-0.5">
                    {tasksData.tasks[realtimeCompletedCount].goal}
                  </p>
                </div>
              )}
              {/* Mini progress bar */}
              <div className="flex items-center gap-1.5">
                {tasksData.tasks.map((_, i) => (
                  <div key={i} className={`h-1.5 flex-1 rounded-full ${
                    i < realtimeCompletedCount ? "bg-[#1B2A4A]" :
                    i === realtimeCompletedCount ? "bg-[#1B2A4A] animate-pulse" :
                    "bg-gray-200"
                  }`} />
                ))}
              </div>
            </div>
          )}
          {buildTrulyDone && (
            <div className="px-4 py-3 bg-white">
              <div className="flex items-center gap-2 mb-2">
                <CheckCircle2 className="h-3.5 w-3.5 text-[#1B2A4A]" />
                <p className="text-[11px] font-semibold text-[#1B2A4A]">
                  {tasksData ? `All ${tasksData.tasks.length} tasks completed` : "Build complete"}
                </p>
              </div>
              {tasksData && (
                <div className="flex gap-1">
                  {tasksData.tasks.map((_, i) => (
                    <div key={i} className="h-1.5 flex-1 rounded-full bg-[#1B2A4A]" />
                  ))}
                </div>
              )}
            </div>
          )}
          {buildStatus === "running" && !tasksData && (
            <div className="px-4 py-3 bg-[#E8EDF5]/50 flex items-center gap-2">
              <Loader2 className="h-3.5 w-3.5 text-[#1B2A4A] animate-spin" />
              <p className="text-[11px] text-[#1B2A4A]">Building prototype…</p>
            </div>
          )}
          {buildAgent && <AgentDetailSection agent={buildAgent} />}
        </PhaseCard>

        {/* Connector */}
        {(validateStatus !== "idle" || buildStatus === "done") && (
          <div className="flex items-center gap-2 pl-4">
            <ArrowRight className="h-3.5 w-3.5 text-gray-300" />
            <span className="text-[9px] text-gray-400">HTML passed to Validation Agent</span>
          </div>
        )}

        {/* Phase 5: Validation */}
        <PhaseCard
          number={5}
          icon={CheckCircle2}
          label="Validation Agent — P0/P1 Checks"
          color={{ bg: "bg-[#E8EDF5]", text: "text-[#1B2A4A]", border: "border-[#1B2A4A]/20" }}
          status={validateStatus}
        >
          {validateStatus === "running" && (
            <div className="px-4 py-3 bg-[#E8EDF5]/50 flex items-center gap-2">
              <Loader2 className="h-3.5 w-3.5 text-[#1B2A4A] animate-spin" />
              <p className="text-[11px] text-[#1B2A4A]">Running P0/P1 structural validation…</p>
            </div>
          )}
          {validateStatus === "done" && validateAgent?.output && (
            <div className="px-4 py-3 bg-white">
              <p className="text-[11px] text-[#1B2A4A] leading-relaxed whitespace-pre-wrap">
                {validateAgent.output}
              </p>
            </div>
          )}
          {validateAgent && <AgentDetailSection agent={validateAgent} />}
        </PhaseCard>

        {/* Complete */}
        {validateStatus === "done" && (
          <div className="flex items-center gap-2 py-2 pl-4">
            <div className="w-6 h-6 rounded-full bg-[#1B2A4A] flex items-center justify-center flex-shrink-0">
              <CheckCircle2 className="h-3.5 w-3.5 text-white" />
            </div>
            <span className="text-[11px] font-semibold text-[#1B2A4A]">
              Prototype complete — {totalDuration > 0 ? `${totalDuration.toFixed(0)}s` : ""}
            </span>
          </div>
        )}
      </div>

      {/* Token footer */}
      {totalTokens > 0 && (
        <div className="flex-shrink-0 border-t border-gray-100 px-4 py-2.5 bg-gray-50/50">
          <div className="flex items-center justify-between text-[10px] text-gray-500">
            <div className="flex items-center gap-1.5">
              <Cpu className="h-3 w-3 text-gray-400" />
              <span>Total tokens</span>
            </div>
            <span className="font-semibold text-gray-700">{(totalTokens / 1000).toFixed(1)}k</span>
          </div>
        </div>
      )}
    </div>
  );
}
