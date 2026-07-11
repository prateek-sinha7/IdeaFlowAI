"use client";

import { useState } from "react";
import {
  Brain, ChevronDown, Zap, CheckCircle2, XCircle, Activity,
} from "lucide-react";
import type { AgentRunState, PipelineRunState, ClarifyRound, WaveGroup } from "@/types/index";
import { TokenUsageSummary } from "@/components/workflow/TokenUsageSummary";
// Phase 39 plan 02 — the three-level Steps navigation lives in these extracted
// views. The former flat AgentTimelineCard list + PipelineHeader + inline
// sub-sections (ToolCallsSection / InputPromptSection / OutputPreviewSection /
// ContextSourcesRow) are RETIRED here and re-homed inside AgentDetailPanel
// (INV-3 — single implementation, no dual list).
import { StepsOverviewSpine } from "./StepsOverviewSpine";
import { AgentDetailPanel } from "./AgentDetailPanel";
import { TaskDetailPanel } from "./TaskDetailPanel";
import { StartingPointCard } from "./StartingPointCard";
// The inline gate/clarify affordances are REUSED (SC-2, INV-12) — mounted inside
// StepsOverviewSpine. The type imports below reference
// @/components/chat/InlineGateActions / InlineClarifyActions (same submit channels).
import type { ClarifyResponse } from "@/components/chat/InlineClarifyActions";

interface AgentThinkingTabProps {
  agents: AgentRunState[];
  pipelineState?: PipelineRunState;
  waves?: WaveGroup[];
  runInput?: string;
  originalBriefRootRunId?: string;
  revisionParentVersion?: number;
  clarifications?: ClarifyRound[];
  clarificationsLoading?: boolean;
  laneGate?: import("@/components/chat/RunChatLane").GateContext;
  onApproveGate?: (gateKey: string, editedContent?: string) => void;
  onRejectGate?: (gateKey: string) => void;
  onRedoGate?: (gateKey: string, instructions: string) => void;
  onUpdateSpecsGate?: (gateKey: string, report: string) => void;
  clarifyQuestions?: import("@/components/preview/QuestionnairePanel").ClarifyQuestion[];
  onSubmitClarify?: (responses: ClarifyResponse[]) => void;
  onSkipClarify?: () => void;
}

// ─── Empty state ──────────────────────────────────────────────────────────────
function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4 text-center px-8">
      <div className="relative">
        <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-brand/8 to-brand/4 flex items-center justify-center">
          <Activity className="h-7 w-7 text-brand/30" />
        </div>
        <div className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-surface-paper flex items-center justify-center">
          <div className="w-1.5 h-1.5 rounded-full bg-line-faint" />
        </div>
      </div>
      <div>
        <p className="text-[13px] font-semibold text-ink-700 mb-1">Pipeline trace</p>
        <p className="text-[11px] text-ink-300 leading-relaxed max-w-[200px]">
          Start a pipeline to see real-time agent reasoning, tool calls, and context flow.
        </p>
      </div>
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
      <div className="absolute left-0 top-3 flex flex-col items-center">
        <div className={`w-6 h-6 rounded-full flex items-center justify-center border-2 z-10 ${
          isRunning ? "border-brand/40 bg-brand-fill animate-pulse" :
          isDone ? "border-brand bg-brand" :
          "border-status-failed bg-status-failed-fill"
        }`}>
          {isDone ? <CheckCircle2 className="h-3 w-3 text-white" /> :
           isError ? <XCircle className="h-3 w-3 text-status-failed" /> :
           <Brain className="h-3 w-3 text-brand" />}
        </div>
        <div className="w-px flex-1 bg-line-border mt-1" style={{ minHeight: 20 }} />
      </div>

      <div className={`rounded-xl border overflow-hidden transition-all ${
        isRunning ? "border-brand/20 shadow-sm" : "border-line-faint-row"
      }`}>
        <button
          onClick={() => setExpanded(v => !v)}
          aria-expanded={expanded}
          className="w-full flex items-center gap-3 px-4 py-3 bg-surface-white hover:bg-surface-warm/50 transition-colors text-left"
        >
          <div className="w-7 h-7 rounded-lg bg-brand-fill flex items-center justify-center flex-shrink-0">
            <Brain className="h-3.5 w-3.5 text-brand" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <p className="text-[12px] font-semibold text-ink-900">Deep Planner</p>
              {plannerStatus === "timeout" && (
                <span className="text-[9px] bg-status-amber-fill text-status-amber border border-status-amber-border px-1.5 py-0.5 rounded-full font-medium">TIMEOUT</span>
              )}
            </div>
            <p className="text-[10px] text-ink-300 truncate">
              {plannerSummary ? `Intent: ${plannerSummary.slice(0, 60)}` : "Analyzing brief & planning execution…"}
            </p>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            {executionGate && (
              <span className={`text-[9px] font-bold px-2 py-0.5 rounded-full ${
                executionGate === "PROCEED" ? "bg-brand-fill text-brand" : "bg-status-amber-fill text-status-amber"
              }`}>
                {executionGate}
              </span>
            )}
            {isRunning && <Zap className="h-3.5 w-3.5 text-brand animate-pulse" />}
            <ChevronDown className={`h-3.5 w-3.5 text-ink-300 transition-transform ${expanded ? "rotate-180" : ""}`} />
          </div>
        </button>

        {expanded && plannerSummary && (
          <div className="border-t border-line-faint-row px-4 py-3 bg-gradient-to-b from-brand-fill/40 to-surface-white">
            <p className="text-[10px] font-semibold text-brand uppercase tracking-wider mb-1.5">Inferred intent</p>
            <p className="text-[11px] text-ink-700 leading-relaxed">{plannerSummary}</p>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Main export ──────────────────────────────────────────────────────────────
export function AgentThinkingTab({
  agents, pipelineState, waves, runInput, originalBriefRootRunId, revisionParentVersion,
  clarifications, clarificationsLoading,
  laneGate, onApproveGate, onRejectGate, onRedoGate, onUpdateSpecsGate,
  clarifyQuestions, onSubmitClarify, onSkipClarify,
}: AgentThinkingTabProps) {
  // ── The three-level Steps navigation (mirrors the mock's stepView/taskView) ──
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [selectedTaskIndex, setSelectedTaskIndex] = useState<number | null>(null);

  const resolvedClarifications = clarifications ?? pipelineState?.clarifications;
  const hasAnyData = pipelineState?.plannerStatus ||
    agents.some(a => a.thinkingText || (a.toolCalls?.length ?? 0) > 0 || a.inputPrompt || a.status !== "idle") ||
    !!runInput || (resolvedClarifications?.length ?? 0) > 0;

  if (!hasAnyData) return <EmptyState />;

  // SC-001: no workflow-name gate. Every workflow renders through this generic
  // overview → detail drill-down (the former isPrototypePipeline branch is gone).
  // The overview spine shows the FULL ordered pipeline (idle agents render as
  // pending / "Not run" rings), mirroring the mock's spine — the halted banner's
  // "N did not run" count derives from those idle rows (ND-D).

  // ── L2 construction data (dual-source, STEPS-ARTIFACT-DERIVATION §2/§3) ──
  const resolvedWaves = waves ?? [];
  const completedTaskCount = pipelineState?.protoCompletedTaskCount ?? 0;
  const waveTaskUniverse = new Set(resolvedWaves.flatMap(w => w.taskIds));
  const totalTasks = waveTaskUniverse.size > 0 ? waveTaskUniverse.size : completedTaskCount;
  const constructionIdx = agents.findIndex(a => /build|construct/i.test(a.id));
  const constructionAgent = constructionIdx >= 0 ? agents[constructionIdx] : undefined;
  const laterAgentStarted = constructionIdx >= 0 &&
    agents.slice(constructionIdx + 1).some(a => a.status !== "idle");
  const constructionComplete = constructionAgent
    ? constructionAgent.status === "done" && (laterAgentStarted || pipelineState?.isRunning === false)
    : pipelineState?.isRunning === false;
  const hasConstruction = resolvedWaves.length > 0 || pipelineState?.protoCompletedTaskCount != null;

  const selectedAgent = selectedAgentId ? agents.find(a => a.id === selectedAgentId) : undefined;
  const isConstructionSelected = !!selectedAgent && constructionAgent?.id === selectedAgent.id;

  // ── L3 task status (KAN-99 N-1 cap, mirrors ConstructionBlock) ──
  const displayedDone = constructionComplete ? totalTasks : Math.min(completedTaskCount, Math.max(0, totalTasks - 1));
  const taskStatusFor = (i: number): "done" | "running" | "pending" =>
    i < displayedDone ? "done" : (!constructionComplete && i === displayedDone ? "running" : "pending");
  const showTaskDetail = selectedTaskIndex != null && isConstructionSelected;

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex-1 overflow-y-auto px-6 py-6">
        {showTaskDetail && selectedAgent ? (
          // ── L3 — single construction task detail ──
          <TaskDetailPanel
            taskIndex={selectedTaskIndex!}
            agentName={selectedAgent.name}
            status={taskStatusFor(selectedTaskIndex!)}
            task={pipelineState?.protoCompletedTasks?.find(t => t.number === selectedTaskIndex! + 1)}
            toolCalls={selectedAgent.toolCalls}
            onBack={() => setSelectedTaskIndex(null)}
          />
        ) : selectedAgent ? (
          // ── L2 — agent detail ──
          <AgentDetailPanel
            agent={selectedAgent}
            onBack={() => setSelectedAgentId(null)}
            construction={isConstructionSelected && hasConstruction ? {
              completedCount: completedTaskCount,
              totalTasks,
              isComplete: constructionComplete,
              waves: resolvedWaves,
              tasks: pipelineState?.protoCompletedTasks,
            } : undefined}
            onOpenTask={isConstructionSelected ? (i) => setSelectedTaskIndex(i) : undefined}
          />
        ) : (
          // ── L1 — overview ──
          <div className="max-w-[760px] mx-auto space-y-3">
            <StartingPointCard
              input={runInput}
              originalBriefRootRunId={originalBriefRootRunId}
              revisionParentVersion={revisionParentVersion}
            />
            {pipelineState && <PlannerCard pipelineState={pipelineState} />}

            <StepsOverviewSpine
              agents={agents}
              pipelineState={pipelineState}
              clarifications={resolvedClarifications}
              clarificationsLoading={clarificationsLoading}
              onOpenAgent={(id) => { setSelectedAgentId(id); setSelectedTaskIndex(null); }}
              laneGate={laneGate}
              onApproveGate={onApproveGate}
              onRejectGate={onRejectGate}
              onRedoGate={onRedoGate}
              onUpdateSpecsGate={onUpdateSpecsGate}
              clarifyQuestions={clarifyQuestions}
              onSubmitClarify={onSubmitClarify}
              onSkipClarify={onSkipClarify}
            />
          </div>
        )}
      </div>

      {pipelineState && (
        <div className="flex-shrink-0 border-t border-line-faint-row px-4 py-2 bg-surface-warm/50">
          <TokenUsageSummary pipelineState={pipelineState} modelId={pipelineState.modelId} />
        </div>
      )}
    </div>
  );
}
