"use client";

// ─────────────────────────────────────────────────────────────────────────────
// Phase 39 plan 02 (RUNUI-06/08) — AgentDetailPanel: the Steps tab's L2 view.
// A 2-column agent detail — the full execution on the LEFT (reasoning · artifact ·
// tool calls · full input · agent output) and a `position:sticky` "Context
// received" panel on the RIGHT, built from the agent's LIVE `contextSources`
// (ND-D — never the mock's hardcoded source sizes; SC-001 — never a
// workflow/agent-name literal). It reuses the sub-sections that previously lived
// inside the retired flat AgentTimelineCard (INV-3: single implementation). The
// construction fan-out renders as ONE integrated block with build tasks NESTED
// UNDER their waves (INV-12: the former separate WaveTreePanel "Wave / Subagent
// tree" is retired here — single representation, no dual view).
// Token-reskinned off the Phase-32 tokens (no gray-* palette).
// ─────────────────────────────────────────────────────────────────────────────

import { useEffect, useRef, useState } from "react";
import {
  Brain, Wrench, ChevronDown, ChevronLeft, ChevronRight, CheckCircle2, XCircle,
  Clock, Cpu, FileText, Copy, Check, Eye, EyeOff, AlertTriangle, Pencil,
  Layers, Zap, FileCode, BookText, GitBranch, ArrowDown, CheckCircle2 as CheckBadge,
} from "lucide-react";
import type { AgentRunState, ContextSource, ToolCallEntry, ValidationIssue, WaveGroup } from "@/types/index";
import { formatDuration, formatTokenCount } from "@/lib/runStats";
import { discriminateArtifact, AnalysisPreview, parseSpecSections, parseSpecOverview, parseTasks } from "./artifactPreview";
import { ArtifactVersionPicker } from "./ArtifactVersionPicker";
import { ReadOnlyVersionBanner } from "@/components/preview/ReadOnlyVersionBanner";

// ─── Shared context-source formatting (INV-12 — the single derivation the sticky
//     panel + any future consumer share; was inline in the retired ContextSourcesRow).
// KAN-129: extended to handle "run_input" and "context_block" source types added
// by KAN-102 — these carry a backend `label` field (e.g. "prompt.md",
// "Template: ibm-carbon") that was previously ignored, causing all first-agent
// sources to render as "artifact". SC-001: dispatch on generic type field only,
// never on agent/workflow name.
export function formatContextSource(src: ContextSource): { name: string; meta: string } {
  const name =
    src.type === "summary"
      ? (src.agent_name || src.agent_id || "Agent")
      : src.type === "run_input"
      ? (src.label || "prompt.md")
      : src.type === "context_block"
      ? (src.label || "context")
      : (src.artifact_type || "artifact");
  const rawSize =
    src.type === "summary" ? src.summary_length
    : src.type === "artifact" ? src.artifact_size_chars
    : src.type === "run_input" || src.type === "context_block" ? src.size_chars
    : null;
  const sizeK = rawSize != null ? `${(rawSize / 1000).toFixed(1)}k` : null;
  const compression =
    src.type === "summary" &&
    src.summary_length != null &&
    src.full_output_length != null &&
    src.full_output_length > 0
      ? Math.round((1 - src.summary_length / src.full_output_length) * 100)
      : null;
  const meta = [sizeK, compression != null && compression > 0 ? `-${compression}%` : null]
    .filter(Boolean).join(" · ") || "context";
  return { name, meta };
}

// ─── Settled artifact-card derivation (42-09, RUNUI-07/08) ────────────────────
// The mock's per-agent artifact card (pages/sections · tasks · checks) + handoff
// line render in the settled L2 detail between the reasoning block and the tool
// calls. The card TYPE is chosen by the SHARED name-free discriminator
// (`discriminateArtifact` — spec/tasks/analysis by the artifact's own wrapper
// tag, never a workflow/agent-name literal — SC-001). Every branch keys on
// GENERIC in-state data; nothing keys on the agent's id/name. Cards are
// CONDITIONAL — an agent whose output carries no recognized artifact tag (and a
// tasks agent whose body contains no `## Task N:` rows) renders NO card. All data
// flows on the FRONTEND-ONLY path (the artifact body / validation* / dagEdges) —
// zero backend/golden/transport dependency.

/** Run-scoped pipeline data the handoff line consumes. The artifact CARDS take no
 *  run state: their content is the artifact on screen (ISS-087). */
export interface ArtifactCardData {
  dagEdges?: Array<{ from: string; to: string; artifact_type: string }>;
}

/** The derived descriptor: which card to show, its data, and the handoff target. */
export interface ArtifactCardModel {
  /** Name-free discriminator result (spec/tasks/analysis) or null → no card. */
  kind: "spec" | "tasks" | "analysis" | null;
  /** pages/sections card (spec output present). */
  showPages: boolean;
  /** tasks card (tasks output whose body contains at least one `## Task N:` row). */
  showTasks: boolean;
  /** checks card (analysis output). */
  showChecks: boolean;
  /** tasks-card rows parsed from the artifact body (empty unless showTasks). */
  tasks: Array<{ number: number; title: string }>;
  /** "N planned" count — the size of the plan on screen. */
  taskCount: number;
  /** checks-card verdict: pass/fail derived from validationPassed/validationIssues. */
  checksPassed: boolean;
  checksIssueCount: number;
  /** handoff target — producer→consumer from dagEdges, else next-agent name; null when last & no edge. */
  handoff: { label: string | null; to: string } | null;
}

/** Handoff: the producer edge for this agent from dagEdges (label + consumer
 *  name), else the next agent by order (SC-001 — only the live agent NAME, never
 *  a workflow/agent-id literal); null when this is the last agent with no edge. */
function deriveHandoff(
  agent: AgentRunState,
  index: number,
  agents: AgentRunState[],
  dagEdges?: Array<{ from: string; to: string; artifact_type: string }>,
): { label: string | null; to: string } | null {
  const edge = dagEdges?.find(e => e.from === agent.id);
  if (edge) {
    const toAgent = agents.find(a => a.id === edge.to);
    return { label: edge.artifact_type || null, to: toAgent?.name ?? edge.to };
  }
  const next = agents[index + 1];
  return next ? { label: null, to: next.name } : null;
}

/** Pure derivation (exported for the test): pick the card kind via the shared
 *  discriminator, derive its data from in-state fields, and resolve the handoff.
 *  Keys ONLY on generic state/props — never `agent.id`/`agent.name`.
 *  ISS-085: `agent.output` must be the version ON SCREEN, not necessarily the
 *  newest — the artifact's TYPE is a property of that artifact, so an older
 *  version of a different shape has to reach its own renderer. */
export function deriveArtifactCardModel(
  agent: AgentRunState,
  index: number,
  agents: AgentRunState[],
  data: ArtifactCardData,
): ArtifactCardModel {
  const kind = discriminateArtifact(agent.output || "");

  // tasks card — the plan's own rows, parsed from the artifact body ON SCREEN.
  // ISS-087: this read the build agent's `task_progress` completed-task stream, so a
  // card labelled "N planned" rendered the number COMPLETED (wrong even at the latest
  // version) and stayed pinned to the run while the version picker moved everything
  // around it. The plan's size is a property of the plan, so it comes from the plan.
  // A `<tasks>` body with no `## Task N:` rows → NO card (generic degrade).
  const plannedTasks = kind === "tasks" ? parseTasks(agent.output || "") : [];
  const showTasks = plannedTasks.length > 0;
  const tasks = plannedTasks.map(t => ({ number: t.number, title: t.title }));
  const taskCount = plannedTasks.length;

  // checks card — an analysis-artifact agent; badge from validation* (structured).
  const showChecks = kind === "analysis";
  const checksIssueCount = agent.validationIssues?.length ?? 0;
  const checksPassed = agent.validationPassed === true && checksIssueCount === 0;

  // pages/sections card — a spec-artifact agent.
  const showPages = kind === "spec";

  return {
    kind,
    showPages,
    showTasks,
    showChecks,
    tasks,
    taskCount,
    checksPassed,
    checksIssueCount,
    handoff: deriveHandoff(agent, index, agents, data.dagEdges),
  };
}

// ─── Reasoning card (violet) ──────────────────────────────────────────────────
function ReasoningCard({ text, live, label = "Reasoning" }: { text: string; live: boolean; label?: string }) {
  const [open, setOpen] = useState(true);
  const bodyRef = useRef<HTMLParagraphElement>(null);
  // Follow the streaming tail while live (a terminal-style auto-scroll to bottom).
  useEffect(() => {
    if (live && open && bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [text, live, open]);
  return (
    <div className="rounded-[11px] border border-[#E4E0F5] bg-[#F4F2FB] overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        aria-expanded={open}
        className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-left"
      >
        <span className="w-[22px] h-[22px] flex-none rounded-md bg-brand-fill grid place-items-center">
          <Brain className="h-3 w-3 text-[#6E5EDA]" />
        </span>
        <span className="flex-1 text-[10px] font-semibold uppercase tracking-[0.1em] text-[#5A4FC0]">
          {live ? `${label} (live)` : label}
        </span>
        <ChevronDown className={`h-3.5 w-3.5 text-[#9A93C8] transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <p ref={bodyRef} className="m-0 px-11 pb-3 text-[13px] leading-[1.6] text-[#4A4680] font-[Heebo] whitespace-pre-wrap max-h-[340px] overflow-y-auto">
          {text}
          {live && <span className="animate-pulse">▌</span>}
        </p>
      )}
    </div>
  );
}

// ─── Tool calls (card, collapsed) ─────────────────────────────────────────────
export function ToolCallsSection({ toolCalls }: { toolCalls: ToolCallEntry[] }) {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const [sectionOpen, setSectionOpen] = useState(toolCalls.length <= 5);
  return (
    <div className="mt-3 bg-surface-card border border-line-border rounded-[11px] overflow-hidden">
      <button
        onClick={() => setSectionOpen(v => !v)}
        aria-expanded={sectionOpen}
        className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-left"
      >
        <span className="w-[22px] h-[22px] flex-none rounded-md bg-[#EFEDE6] grid place-items-center">
          <Wrench className="h-3 w-3 text-ink-500" />
        </span>
        <span className="text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-500">Tool calls</span>
        <span className="text-[10.5px] text-ink-200 font-mono">{toolCalls.length}</span>
        <span className="flex-1" />
        <ChevronDown className={`h-3.5 w-3.5 text-ink-300 transition-transform ${sectionOpen ? "rotate-180" : ""}`} />
      </button>
      {sectionOpen && (
        <div className="px-3 pb-2.5 space-y-1.5">
          {toolCalls.map((tc, i) => (
            <div key={i} className="rounded-[9px] border border-line-faint-row overflow-hidden bg-surface-white">
              <button
                onClick={() => setExpandedIdx(expandedIdx === i ? null : i)}
                className="w-full flex items-center gap-2.5 px-3 py-2 text-left"
              >
                <span className="w-5 h-5 flex-none rounded-[5px] border border-line-control bg-surface-warm grid place-items-center">
                  <ChevronRight className="h-2.5 w-2.5 text-ink-500" />
                </span>
                <span className="text-[12.5px] font-medium text-ink-800">{tc.tool}</span>
                <span className="text-[12px] text-ink-300 truncate flex-1 min-w-0">
                  {Object.entries(tc.args || {}).map(([k, v]) => `${k}: ${String(v).slice(0, 24)}`).join(", ") || "no args"}
                </span>
                <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded-full flex-none ${tc.result != null ? "bg-brand-fill text-brand" : "bg-status-amber-fill text-status-amber animate-pulse"}`}>
                  {tc.result != null ? "ok" : "…"}
                </span>
              </button>
              {expandedIdx === i && (
                <div className="border-t border-line-faint-row bg-surface-warm/60">
                  {Object.keys(tc.args || {}).length > 0 && (
                    <div className="px-3 py-2 border-b border-line-faint-row">
                      <p className="text-[9px] font-semibold text-ink-400 uppercase tracking-wider mb-1">Arguments</p>
                      <pre className="text-[9px] text-ink-600 font-mono whitespace-pre-wrap leading-relaxed">{JSON.stringify(tc.args, null, 2)}</pre>
                    </div>
                  )}
                  {tc.result != null && (
                    <div className="px-3 py-2">
                      <p className="text-[9px] font-semibold text-brand uppercase tracking-wider mb-1">Result</p>
                      <pre className="text-[9px] text-ink-600 font-mono whitespace-pre-wrap leading-relaxed max-h-[200px] overflow-y-auto">{tc.result}</pre>
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

// ─── Full input prompt (paper) ────────────────────────────────────────────────
export function InputPromptSection({ prompt }: { prompt: string }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(prompt);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div className="mt-2.5 bg-surface-paper border border-line-divider rounded-[11px] overflow-hidden">
      <button onClick={() => setOpen(v => !v)} aria-expanded={open} className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-left">
        <span className="w-[22px] h-[22px] flex-none rounded-md bg-line-border grid place-items-center">
          <FileText className="h-3 w-3 text-ink-500" />
        </span>
        <span className="text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-500">Full input prompt</span>
        <span className="text-[10.5px] text-ink-200 font-mono">{prompt.length.toLocaleString()} chars</span>
        <span className="flex-1" />
        <ChevronDown className={`h-3.5 w-3.5 text-ink-300 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div>
          <div className="flex items-center justify-end px-3.5 pt-1">
            <button onClick={handleCopy} className="flex items-center gap-1 text-[9px] text-ink-400 hover:text-ink-600 transition-colors">
              {copied ? <Check className="h-3 w-3 text-brand" /> : <Copy className="h-3 w-3" />}
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
          <pre className="m-0 px-11 pb-3 text-[12px] leading-[1.6] text-ink-500 whitespace-pre-wrap font-[Heebo] max-h-[500px] overflow-y-auto">{prompt}</pre>
        </div>
      )}
    </div>
  );
}

// ─── Agent output (violet) ────────────────────────────────────────────────────
export function OutputPreviewSection({ output }: { output: string }) {
  const [open, setOpen] = useState(false);
  const isHtml = /<!DOCTYPE|<html/i.test(output) || output.includes("<artifact>");
  const preview = isHtml ? "[HTML artifact — click to expand]" : output.slice(0, 160) + (output.length > 160 ? "…" : "");
  return (
    <div className="mt-2.5 bg-[#F4F2FB] border border-[#E4E0F5] rounded-[11px] overflow-hidden">
      <button onClick={() => setOpen(v => !v)} aria-expanded={open} className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-left">
        <span className="w-[22px] h-[22px] flex-none rounded-md bg-brand-fill grid place-items-center">
          {open ? <EyeOff className="h-3 w-3 text-[#5A4FC0]" /> : <Eye className="h-3 w-3 text-[#5A4FC0]" />}
        </span>
        <span className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[#5A4FC0]">Agent output</span>
        <span className="text-[10.5px] text-[#9A93C8] font-mono">{(output.length / 1000).toFixed(1)}k chars</span>
        <span className="flex-1" />
        <ChevronDown className={`h-3.5 w-3.5 text-[#9A93C8] transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      <p className={`m-0 px-11 pb-3 text-[12px] leading-[1.6] text-[#4A4680] whitespace-pre-wrap font-[Heebo] ${open ? "max-h-[500px] overflow-y-auto" : "line-clamp-2"}`}>
        {open ? output : preview}
      </p>
    </div>
  );
}

// ─── Revision instruction (violet emphasis) ───────────────────────────────────
function RevisionInstructionCard({ prompt }: { prompt: string }) {
  const match = prompt.match(/===\s*REVISION REQUEST\s*===\s*\n([\s\S]*?)\n===\s*END REQUEST\s*===/i);
  if (!match) return null;
  return (
    <div className="mb-3 rounded-[11px] border-2 border-brand/30 bg-brand/5 px-3 py-2.5">
      <div className="flex items-center gap-1.5 mb-1.5">
        <Pencil className="h-3 w-3 text-brand" />
        <span className="text-[9px] font-bold text-brand uppercase tracking-widest">Revision request</span>
      </div>
      <p className="text-[11px] text-brand font-medium leading-relaxed">{match[1].trim()}</p>
    </div>
  );
}

// ─── Edit summary (from tool calls) ───────────────────────────────────────────
function EditSummaryCard({ toolCalls }: { toolCalls: ToolCallEntry[] }) {
  const edits = toolCalls.filter(tc => tc.tool === "edit_file");
  const writes = toolCalls.filter(tc => tc.tool === "write_file");
  if (edits.length === 0 && writes.length === 0) return null;
  return (
    <div className="mb-3 rounded-[11px] border border-status-done-border bg-status-done-fill px-3 py-2.5">
      <div className="flex items-center gap-1.5 mb-1.5">
        <CheckCircle2 className="h-3 w-3 text-status-done" />
        <span className="text-[9px] font-bold text-status-done uppercase tracking-widest">Changes applied</span>
      </div>
      <div className="flex flex-wrap gap-2">
        {edits.length > 0 && <span className="text-[10px] font-semibold text-status-done bg-surface-white px-2 py-0.5 rounded-full">{edits.length} surgical edit{edits.length !== 1 ? "s" : ""}</span>}
        {writes.length > 0 && <span className="text-[10px] font-semibold text-status-done bg-surface-white px-2 py-0.5 rounded-full">{writes.length} full rewrite{writes.length !== 1 ? "s" : ""}</span>}
      </div>
    </div>
  );
}

// ─── Validation result ────────────────────────────────────────────────────────
function ValidationResultCard({ passed, issues }: { passed?: boolean; issues?: ValidationIssue[] }) {
  const [open, setOpen] = useState(false);
  if (passed === undefined && (!issues || issues.length === 0)) return null;
  const hasIssues = issues && issues.length > 0;
  const isPassed = passed === true && !hasIssues;
  return (
    <div className={`mb-3 rounded-[11px] border px-3 py-2.5 ${isPassed ? "border-status-done-border bg-status-done-fill" : "border-status-amber-border bg-status-amber-fill"}`}>
      <button onClick={() => hasIssues && setOpen(v => !v)} className="w-full flex items-center gap-1.5 text-left">
        {isPassed ? <CheckCircle2 className="h-3 w-3 text-status-done flex-none" /> : <AlertTriangle className="h-3 w-3 text-status-amber flex-none" />}
        <span className={`text-[9px] font-bold uppercase tracking-widest ${isPassed ? "text-status-done" : "text-status-amber"}`}>
          Validation {isPassed ? "passed" : passed === false ? "blocked" : "issues found"}
        </span>
        {hasIssues && <span className="text-[9px] px-1.5 py-0.5 rounded-full font-medium ml-1 bg-surface-white text-status-amber">{issues!.length} issue{issues!.length !== 1 ? "s" : ""}</span>}
        {hasIssues && <ChevronDown className={`h-3 w-3 text-ink-300 ml-auto transition-transform ${open ? "rotate-180" : ""}`} />}
      </button>
      {open && hasIssues && (
        <div className="mt-2 space-y-1">
          {issues!.map((issue, i) => (
            <div key={i} className="flex items-start gap-1.5 rounded-lg bg-surface-white border border-status-amber-border px-2.5 py-1.5">
              <span className="text-[8px] font-bold uppercase px-1 py-0.5 rounded flex-none mt-0.5 bg-status-amber-fill text-status-amber">{issue.severity}</span>
              <p className="text-[10px] text-ink-700 leading-snug">{issue.message}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Construction block (waves + NESTED navigable per-task rows → L3) ──────────
// The mock's single integrated "Construction · waves & subagents · N/N done"
// block: build TASKS are NESTED UNDER the wave that produced them. This retires
// the former DUAL representation (a flat task list PLUS a separate WaveTreePanel
// "Wave / Subagent tree") — INV-12, one representation only.
//
// Task↔wave mapping (ND-P): a wave carries `taskIds` (backend strings) while the
// completed tasks carry a `number`. We join on the trailing integer of each
// taskId. When that join cleanly covers every displayed task, each task nests
// under its own wave; otherwise ALL tasks nest under a single wave group (still
// ONE integrated block) — the registered mapping limitation. Every task row keeps
// the `construction-task-row` testid + opens the L3 TaskDetailPanel via onOpenTask.
//
// Per-task DURATION (ND-O): protoCompletedTasks carries {number,title,summary}
// with NO per-task timing, so a nested task row shows no duration — never a
// fabricated one.

type CTaskStatus = "done" | "running" | "pending";
interface CTask { index: number; number: number; title?: string; status: CTaskStatus; }
interface CGroup { key: string; waveIndex: number | null; kind: string | null; status: string | null; tasks: CTask[]; }

/** Task numbers a wave references, parsed from the trailing integer of each taskId. */
function waveTaskNumbers(w: WaveGroup): Set<number> {
  return new Set(
    w.taskIds
      .map(id => { const m = /(\d+)\s*$/.exec(id); return m ? parseInt(m[1], 10) : NaN; })
      .filter(n => Number.isFinite(n)),
  );
}

/** A wave that fanned out to >1 concurrent subagent ran its tasks in parallel. */
function waveKind(w: WaveGroup): string {
  return w.workers.length > 1 ? "parallel" : "sequential";
}

/** Group the displayed tasks under their wave (clean map) or, failing a clean
 *  join, under a single wave group (ND-P fallback) — always ONE integrated block. */
function buildConstructionGroups(waves: WaveGroup[], tasks: CTask[]): CGroup[] {
  const ordered = [...waves].sort((a, b) => a.waveIndex - b.waveIndex);
  if (ordered.length === 0) {
    // No wave lifecycle reported — one group, tasks nested, no wave chrome.
    return [{ key: "all", waveIndex: null, kind: null, status: null, tasks }];
  }
  const parsed = ordered.map(w => ({ w, nums: waveTaskNumbers(w) }));
  const groupFor = (n: number) => parsed.findIndex(p => p.nums.has(n));
  const cleanMap = tasks.length > 0 && tasks.every(t => groupFor(t.number) >= 0);
  if (!cleanMap) {
    // Mapping unclean (taskIds don't cover the completed-task set) — ND-P fallback:
    // ALL tasks nest under a single group, chrome borrowed from the first wave.
    const first = ordered[0];
    return [{ key: `wave-${first.waveIndex}`, waveIndex: first.waveIndex, kind: waveKind(first), status: first.status, tasks }];
  }
  return parsed
    .map(p => ({
      key: `wave-${p.w.waveIndex}`,
      waveIndex: p.w.waveIndex,
      kind: waveKind(p.w),
      status: p.w.status,
      tasks: tasks.filter(t => p.nums.has(t.number)),
    }))
    .filter(g => g.tasks.length > 0);
}

/** Normalize a wave lifecycle status into its display label + token chip. */
function waveStatusChip(status: string): { label: string; cls: string } {
  const s = (status || "").toLowerCase();
  if (s.includes("cancel")) return { label: "cancelled", cls: "bg-status-amber/10 text-status-amber" };
  if (s.includes("fail") || s.includes("error")) return { label: "failed", cls: "bg-status-failed/10 text-status-failed" };
  if (s.includes("complete") || s.includes("done") || s.includes("success")) return { label: "completed", cls: "bg-status-done/10 text-status-done" };
  if (s.includes("run") || s.includes("spawn") || s.includes("progress") || s.includes("start")) return { label: "running", cls: "bg-status-running/10 text-status-running" };
  return { label: "pending", cls: "bg-status-queued/10 text-status-queued" };
}

function ConstructionTaskRow({ task, onOpenTask }: { task: CTask; onOpenTask?: (taskIndex: number) => void }) {
  return (
    <button
      data-testid="construction-task-row"
      onClick={() => onOpenTask?.(task.index)}
      className="w-full flex items-center gap-2.5 rounded-[9px] border border-line-faint-row bg-surface-card px-2.5 py-2.5 text-left hover:border-line-faint transition-colors"
    >
      {task.status === "done" ? (
        <span className="w-[17px] h-[17px] flex-none rounded-full bg-surface-near-black grid place-items-center"><Check className="h-2.5 w-2.5 text-white" /></span>
      ) : task.status === "running" ? (
        <span className="w-[17px] h-[17px] flex-none rounded-full bg-brand-fill border-[1.5px] border-brand grid place-items-center"><span className="w-1.5 h-1.5 rounded-full bg-brand" /></span>
      ) : (
        <span className="w-[17px] h-[17px] flex-none rounded-full border-[1.5px] border-line-control" />
      )}
      <span className="text-[11.5px] text-ink-700">
        <span className="font-mono text-ink-200">Task {task.number}</span>{task.title ? ` · ${task.title}` : ""}
      </span>
      <span className="flex-1" />
      <ChevronRight className="h-[15px] w-[15px] flex-none text-line-faint" />
    </button>
  );
}

function ConstructionBlock({
  completedCount, totalTasks, isComplete, waves, tasks, onOpenTask,
}: {
  completedCount: number;
  totalTasks: number;
  isComplete: boolean;
  waves: WaveGroup[];
  tasks?: Array<{ number: number; title: string; summary: string }>;
  onOpenTask?: (taskIndex: number) => void;
}) {
  const displayedDone = isComplete ? totalTasks : Math.min(completedCount, Math.max(0, totalTasks - 1));
  const pct = totalTasks > 0 ? Math.round((displayedDone / totalTasks) * 100) : 0;
  const titleFor = (i: number) => tasks?.find(t => t.number === i + 1)?.title;

  const displayTasks: CTask[] = Array.from({ length: totalTasks }).map((_, i) => ({
    index: i,
    number: i + 1,
    title: titleFor(i),
    status: i < displayedDone ? "done" : (!isComplete && i === displayedDone ? "running" : "pending"),
  }));
  const groups = buildConstructionGroups(waves, displayTasks);

  return (
    <div data-testid="construction-block" className="mt-3 rounded-[11px] border border-line-border bg-surface-white p-3.5">
      <div className="flex items-center gap-2 mb-1.5">
        <Layers className="h-3.5 w-3.5 text-ink-500" />
        <span className="text-[11px] font-semibold text-ink-800">Construction · waves &amp; subagents</span>
        <span className="flex-1" />
        {totalTasks > 0 && (
          <span data-testid="construction-progress" className="text-[11px] font-mono text-brand">{displayedDone} / {totalTasks} done</span>
        )}
      </div>
      {totalTasks > 0 && (
        <div className="h-[5px] rounded-full bg-brand-fill overflow-hidden mb-3">
          <div className="h-full rounded-full bg-brand transition-all" style={{ width: `${pct}%` }} />
        </div>
      )}

      {totalTasks === 0 ? (
        <p data-testid="construction-empty" className="flex items-center gap-1.5 text-[11px] text-ink-300">
          <GitBranch className="h-3 w-3 flex-none" /> No subagents yet.
        </p>
      ) : (
        <div className="space-y-3">
          {groups.map(group => {
            const chip = group.status ? waveStatusChip(group.status) : null;
            return (
              <div key={group.key}>
                {group.waveIndex != null && (
                  <div className="flex items-center gap-2 mb-1.5">
                    <GitBranch className="h-3 w-3 flex-none text-ink-400" />
                    <span className="text-[11px] font-semibold text-ink-700">Wave {group.waveIndex + 1}</span>
                    {group.kind && <span className="text-[10px] text-ink-200">{group.kind}</span>}
                    <span className="flex-1" />
                    {chip && (
                      <span className={`inline-flex items-center text-[8px] font-semibold uppercase tracking-widest px-1.5 py-0.5 rounded ${chip.cls}`}>
                        {chip.label}
                      </span>
                    )}
                  </div>
                )}
                <div className="ml-1 pl-3.5 border-l-2 border-line-faint-row space-y-1.5">
                  {group.tasks.map(t => (
                    <ConstructionTaskRow key={t.index} task={t} onOpenTask={onOpenTask} />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ─── Sticky "Context received" panel (RIGHT column) ───────────────────────────
function ContextReceivedPanel({ sources }: { sources: ContextSource[] }) {
  return (
    <div className="sticky top-0">
      <div className="bg-surface-warm border border-line-border rounded-[14px] px-4 pt-4 pb-3.5">
        <div className="flex items-center gap-2.5 mb-3.5">
          <span className="w-7 h-7 flex-none rounded-lg bg-[#EFEDE6] grid place-items-center text-ink-500">
            <BookText className="h-[15px] w-[15px]" />
          </span>
          <div className="flex-1 min-w-0">
            <p className="m-0 text-[10px] font-semibold uppercase tracking-[0.11em] text-ink-300">Context received</p>
            <p className="mt-1 text-[11px] text-ink-400 font-mono">{sources.length} source{sources.length !== 1 ? "s" : ""} fed in</p>
          </div>
        </div>
        <div className="flex flex-col gap-1.5">
          {sources.map((src, i) => {
            const { name, meta } = formatContextSource(src);
            return (
              <div key={i} className="flex items-center gap-2.5 bg-surface-white border border-line-border rounded-[10px] px-2.5 py-2">
                <span className="w-7 h-7 flex-none rounded-[7px] bg-brand-fill grid place-items-center text-brand">
                  <FileCode className="h-3.5 w-3.5" />
                </span>
                <div className="flex-1 min-w-0">
                  <p className="m-0 text-[12px] font-semibold text-ink-800 truncate">{name}</p>
                  <p className="mt-0.5 text-[10px] text-ink-200 font-mono">{meta}</p>
                </div>
              </div>
            );
          })}
        </div>
        <p className="mt-3.5 pt-3 border-t border-line-border text-[11px] leading-[1.55] text-ink-200">
          The kernel assembled these into this agent&apos;s prompt before it ran.
        </p>
      </div>
    </div>
  );
}

// ─── Settled artifact cards + handoff line (42-09) ────────────────────────────
// Renders the descriptor from `deriveArtifactCardModel` as the mock's per-agent
// artifact card (pages/sections · tasks · checks) + a handoff line, between the
// reasoning block and the tool calls. Each card renders ONLY when its kind is
// selected AND its data is present (conditional degrade). Text is escaped React
// content (no raw-HTML injection). The KEEP construction card (build agent)
// is a SEPARATE block — never duplicated here. Mock tokens: brand accent #3C2CDA,
// checks green #1F7A4D on #E7F0EA. The pages + coverage bodies REUSE
// SpecPreview/AnalysisPreview (no re-parse) — those parses are flagged BRITTLE
// with their robust versions registered OUT OF SCOPE (F1/F2, see below).
//
// ── Registered OUT-OF-SCOPE follow-ups (42-09, do NOT build here) ─────────────
//   F1 — structured coverage/counts: a `{coverage,counts{P0..P3}}` aggregate on
//        GET /runs/{id}/validation-results (backend/additive, goldens untouched).
//        Until then the checks card's coverage/verdict TEXT is a BRITTLE parse of
//        the analyzer's <analysis> output via AnalysisPreview.
//   F2 — event-free `sections` extractor + /artifacts?kind=sections
//        (backend/additive). Until then the pages/sections card is a BRITTLE parse
//        of the spec agent's <spec> `## ` headings via SpecPreview.
//   Both are backend/additive — OUTSIDE this plan's FRONTEND-ONLY fence
//   (SC-001/LOCK-B): a card needing them means OUT OF SCOPE → flag, never build.
//   Recorded in 42-09-SUMMARY (deferred-items) for the 42-11 phase reconcile.
//
// ISS-085 — this takes the artifact CONTENT on screen, never the agent: rendering
// an older version while these cards re-parsed `agent.output` is what made the
// version picker look inert. `model` carries the un-versioned agent facts.
function SettledArtifactCards({ output, model }: { output: string; model: ArtifactCardModel }) {
  const hasCard = model.showPages || model.showTasks || model.showChecks;
  if (!hasCard) return null;
  const pages = model.showPages ? parseSpecSections(output) : [];
  const pagesOverview = model.showPages ? parseSpecOverview(output) : "";
  return (
    <>
      {/* PAGES / SECTIONS card — the mock's 3-col page-thumbnail grid, built from the
          spec's `## ` headings via parseSpecSections (one parse impl — INV-12).
          BRITTLE (F2): sections are parsed from the spec agent's <spec> output; a
          robust typed extractor is Follow-up F2 (event-free `sections` extractor +
          /artifacts?kind=sections — backend/additive), registered OUT OF SCOPE — do
          NOT build a fetch/endpoint here (SC-001/LOCK-B). */}
      {model.showPages && (
        <div className="mt-3 rounded-[11px] border border-line-border bg-surface-white p-3.5">
          <p className="m-0 mb-[3px] text-[11px] font-semibold text-ink-800">Specification · {pages.length} page{pages.length !== 1 ? "s" : ""}</p>
          {pagesOverview && <p className="m-0 mb-2.5 text-[12px] leading-normal text-ink-400">{pagesOverview}</p>}
          <div className="grid grid-cols-3 gap-2">
            {pages.map((pg, i) => (
              <div key={i} className="rounded-lg overflow-hidden border border-[#EDEBE3] bg-[#FBFAF6]">
                <div className="h-[34px] border-b border-[#EDEBE3] bg-[#F0EEE7] px-[7px] py-1.5">
                  <div className="w-3/5 h-1 rounded-[2px] bg-[#C6C3B9] mb-1" />
                  <div className="w-full h-[3px] rounded-[2px] bg-[#E0DDD3]" />
                </div>
                <p className="m-0 px-2 py-[7px] text-[11px] font-medium text-[#3A3B42] whitespace-nowrap overflow-hidden text-ellipsis font-[Manrope]">{pg.heading}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* TASKS card — "N planned" + a row per task in the plan on screen. */}
      {model.showTasks && (
        <div className="mt-3 rounded-[11px] border border-line-border bg-surface-white p-3.5">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-[11px] font-semibold text-ink-800">Task plan</span>
            <span className="flex-1" />
            <span className="text-[11px] font-mono" style={{ color: "#3C2CDA" }}>{model.taskCount} planned</span>
          </div>
          <div className="space-y-0.5">
            {model.tasks.map(t => (
              <div key={t.number} className="flex items-center gap-2.5 py-1">
                <span className="w-1.5 h-1.5 flex-none rounded-full bg-line-faint" />
                <span className="text-[12px] leading-snug text-ink-700">
                  <span className="font-mono text-ink-200">{t.number}.</span> {t.title}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* CHECKS card — pass/fail verdict badge from validation* + verdict/coverage
          rows via the reused AnalysisPreview.
          BRITTLE (F1): the coverage-%/verdict TEXT is parsed from the analyzer's
          <analysis> output (structured coverage/counts are genuinely absent). The
          robust version is Follow-up F1 (a `{coverage,counts{P0..P3}}` aggregate on
          GET /runs/{id}/validation-results — backend/additive), registered OUT OF
          SCOPE — do NOT add a fetch/endpoint here (SC-001/LOCK-B). */}
      {model.showChecks && (
        <div className="mt-3 rounded-[11px] border border-line-border bg-surface-white p-3.5">
          <div className="flex items-center gap-2 mb-2.5">
            <span className="text-[11px] font-semibold text-ink-800">Governance checks</span>
            <span className="flex-1" />
            {model.checksPassed ? (
              <span
                className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-1 rounded-md"
                style={{ color: "#1F7A4D", background: "#E7F0EA", border: "1px solid #CFE3D6" }}
              >
                <CheckBadge className="h-3 w-3" /> Passed
              </span>
            ) : (
              <span className="inline-flex items-center text-[10px] font-semibold px-2 py-1 rounded-md bg-status-amber-fill text-status-amber border border-status-amber-border">
                {model.checksIssueCount > 0
                  ? `${model.checksIssueCount} issue${model.checksIssueCount !== 1 ? "s" : ""}`
                  : "Review"}
              </span>
            )}
          </div>
          <AnalysisPreview content={output} />
        </div>
      )}

      {/* HANDOFF line — producer→consumer from dagEdges, else next-agent name. */}
      {model.handoff && (
        <div className="flex items-center gap-2.5 mt-3 ml-1">
          <ArrowDown className="h-3.5 w-3.5 flex-none text-line-faint" />
          <span className="text-[11.5px] leading-snug text-ink-200">
            {model.handoff.label
              ? `${model.handoff.label} → ${model.handoff.to}`
              : `Handoff → ${model.handoff.to}`}
          </span>
        </div>
      )}
    </>
  );
}

// ─── Main L2 panel ────────────────────────────────────────────────────────────
export interface AgentDetailPanelProps {
  agent: AgentRunState;
  onBack: () => void;
  construction?: {
    completedCount: number;
    totalTasks: number;
    isComplete: boolean;
    waves: WaveGroup[];
    tasks?: Array<{ number: number; title: string; summary: string }>;
  };
  onOpenTask?: (taskIndex: number) => void;
  // 42-09 — the ordered agent list + this agent's index for the handoff fallback,
  // plus the run's DAG edges for the handoff label. All optional: absent → no
  // handoff (SC-001 generic degrade). The artifact cards need no run state.
  agents?: AgentRunState[];
  agentIndex?: number;
  dagEdges?: Array<{ from: string; to: string; artifact_type: string }>;
  // ISS-065 — the run whose artifact_refs back this agent's output, so an earlier
  // version can be read after an update_specs cycle overwrote it in memory.
  // Optional: absent → no picker, and the panel renders exactly as before.
  runId?: string | null;
}

export function AgentDetailPanel({
  agent, onBack, construction, onOpenTask,
  agents, agentIndex, dagEdges,
  runId,
}: AgentDetailPanelProps) {
  // ISS-065 — the older artifact version currently on screen, if any.
  const [viewed, setViewed] = useState<{ index: number; content: string } | null>(null);
  useEffect(() => { setViewed(null); }, [agent.id]);
  // ISS-085 — this agent AS OF the version on screen. Every consumer of the
  // artifact reads from here, so one selection moves the whole panel; deriving the
  // cards from `agent.output` while the output section read the selected version
  // is what made the picker look like it did nothing. Only `output` is swapped —
  // validation, handoff and task state are run facts, not artifact versions.
  const displayed = viewed ? { ...agent, output: viewed.content } : agent;
  const shownOutput = displayed.output ?? "";
  const isRunning = agent.status === "running" || agent.status === "thinking";
  const isDone = agent.status === "done";
  const isError = agent.status === "error";
  const reasoning = agent.thinkingText || agent.thinking || "";
  const sources = agent.contextSources ?? [];
  // The revision diagnostics ("Revision request" + "Changes applied") are
  // revision-only — the mock's fresh-run detail has no such cards. Gate them on
  // the run carrying an actual revision marker (RevisionInstructionCard self-gates
  // on the same marker; EditSummaryCard is gated here). SC-001: structural marker,
  // never a workflow-name literal.
  const isRevision = /===\s*REVISION REQUEST\s*===/i.test(agent.inputPrompt || "");

  // 42-09 — the settled artifact-card descriptor (kind + data + handoff), keyed on
  // the shared name-free discriminator. Renders conditionally between reasoning and
  // tool calls; the KEEP construction card (build agent) is a separate block.
  const cardModel = deriveArtifactCardModel(
    displayed,
    agentIndex ?? agent.index,
    agents ?? [],
    { dagEdges },
  );

  const metaBits = [
    isDone && agent.duration != null ? formatDuration(agent.duration) : null,
    isDone && agent.totalTokens != null && agent.totalTokens > 0 ? `${formatTokenCount(agent.totalTokens)} tok` : null,
  ].filter(Boolean);

  return (
    <div className="max-w-[1200px] mx-auto">
      {/* Breadcrumb — Steps / {agent} */}
      <button
        onClick={onBack}
        className="inline-flex items-center gap-1.5 text-[12.5px] font-medium text-ink-500 hover:text-ink-900 transition-colors mb-4"
      >
        <ChevronLeft className="h-[15px] w-[15px]" />
        Steps <span className="text-line-faint">/</span> <span className="text-ink-900">{agent.name}</span>
      </button>

      <div className="grid gap-[22px] items-start" style={{ gridTemplateColumns: "1fr 288px" }}>
        {/* LEFT — full execution */}
        <div className="min-w-0">
          <div className="rounded-[11px] border border-line-border bg-surface-white overflow-hidden">
            <div className="flex items-center gap-3 px-4 py-3.5 border-b border-line-faint-row">
              <div className={`w-8 h-8 rounded-xl flex-none grid place-items-center ${
                isRunning ? "bg-brand-fill text-brand" :
                isDone ? "bg-surface-near-black text-white" :
                isError ? "bg-status-failed-fill text-status-failed" :
                "bg-surface-paper text-ink-300"
              }`}>
                {isDone ? <CheckCircle2 className="h-4 w-4" /> :
                 isError ? <XCircle className="h-4 w-4" /> :
                 isRunning ? <Zap className="h-4 w-4" /> :
                 <span className="text-[11px] font-bold">{agent.name.split(" ").map(w => w[0]).slice(0, 2).join("").toUpperCase()}</span>}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <p className="m-0 text-[13.5px] font-semibold text-ink-900 truncate">{agent.name}</p>
                  {isRunning && <span className="inline-flex items-center gap-1 text-[8px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-brand-fill text-brand"><Zap className="h-2.5 w-2.5" />Live</span>}
                  {isDone && <span className="text-[8px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-surface-paper text-ink-500">Done</span>}
                  {isError && <span className="text-[8px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-status-failed-fill text-status-failed">Failed</span>}
                </div>
                <p className="m-0 text-[11px] text-ink-400 truncate">{agent.role}</p>
              </div>
              {/* ISS-065 — per-artifact version picker. Renders nothing unless this
                  agent produced more than one distinct artifact version, so every
                  un-revised run looks exactly as it did before. */}
              <ArtifactVersionPicker
                runId={runId}
                agentId={agent.id}
                selectedIndex={viewed?.index}
                onSelect={setViewed}
              />
              {metaBits.length > 0 && (
                <span className="flex items-center gap-1 text-[11px] text-ink-200 font-mono flex-none">
                  {metaBits.includes(`${formatTokenCount(agent.totalTokens ?? 0)} tok`) && <Cpu className="h-2.5 w-2.5" />}
                  {metaBits.join(" · ")}
                </span>
              )}
            </div>

            <div className="px-4 py-4">
              <div className="pl-4 border-l-2 border-line-divider">
                {/* revision diagnostics (revision runs only — absent on fresh runs) */}
                {isRevision && agent.inputPrompt && <RevisionInstructionCard prompt={agent.inputPrompt} />}
                {isRevision && agent.toolCalls && agent.toolCalls.length > 0 && <EditSummaryCard toolCalls={agent.toolCalls} />}
                <ValidationResultCard passed={agent.validationPassed} issues={agent.validationIssues} />

                {/* reasoning — or the live output stream while running. The engine
                    streams the model's output via agent_chunk (into agent.output) but
                    emits no separate reasoning/thinking stream, so agent.thinkingText is
                    always empty; surface the live output so every running agent
                    (spec-writer, plan, analyze, build…) shows its work instead of a
                    blank cursor. The completed output is shown by OutputPreviewSection.
                    ISS-085 exception: this one card reads `agent.output`, NOT the
                    selected version — it is labelled "(live)" and pinning it to an
                    older version would leave no way to watch the re-run it announces. */}
                {reasoning.trim().length > 0 && <ReasoningCard text={reasoning} live={isRunning} />}
                {reasoning.trim().length === 0 && isRunning && <ReasoningCard text={agent.output || ""} live label="Output" />}

                {/* settled artifact cards (pages/sections · tasks · checks) + handoff
                    line — conditional, generically keyed (42-09). Distinct from the
                    KEEP construction card below. */}
                <SettledArtifactCards output={shownOutput} model={cardModel} />

                {/* construction fan-out (build agent) */}
                {construction && (
                  <ConstructionBlock
                    completedCount={construction.completedCount}
                    totalTasks={construction.totalTasks}
                    isComplete={construction.isComplete}
                    waves={construction.waves}
                    tasks={construction.tasks}
                    onOpenTask={onOpenTask}
                  />
                )}

                {/* tool calls */}
                {agent.toolCalls && agent.toolCalls.length > 0 && <ToolCallsSection toolCalls={agent.toolCalls} />}

                {/* full input */}
                {agent.inputPrompt && <InputPromptSection prompt={agent.inputPrompt} />}

                {/* output — an older artifact version when one is selected, else the
                    agent's live/settled output. ISS-065: the `isDone` gate is widened
                    for `viewed` because the whole point is reading v1 while v3 is
                    being rewritten, i.e. while this agent is back in "running". */}
                {viewed && (
                  <div className="mt-3">
                    <ReadOnlyVersionBanner versionNumber={viewed.index} onBackToLatest={() => setViewed(null)} />
                  </div>
                )}
                {(isDone || viewed) && shownOutput.trim().length > 0 && <OutputPreviewSection output={shownOutput} />}

                {/* failed reason card */}
                {isError && agent.error && (
                  <div className="mt-3 rounded-[10px] bg-status-failed-fill border border-status-failed-border px-3.5 py-3">
                    <p className="m-0 mb-1 text-[11px] font-semibold text-status-failed-strong font-[Manrope]">What went wrong</p>
                    <p className="m-0 text-[12px] leading-[1.55] text-[#6E4A46]">{agent.error}</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* RIGHT — sticky context received */}
        <ContextReceivedPanel sources={sources} />
      </div>
    </div>
  );
}
