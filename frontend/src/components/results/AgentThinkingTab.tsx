"use client";

import { useEffect, useState } from "react";
import { Activity } from "lucide-react";
import type { AgentRunState, PipelineRunState, ClarifyRound, WaveGroup } from "@/types/index";
import type { GateEventRow } from "@/lib/api";
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
  clarifyQuestions?: import("@/types/index").ClarifyQuestion[];
  onSubmitClarify?: (responses: ClarifyResponse[]) => void;
  onSkipClarify?: () => void;
  /** Cancel the active pipeline from the inline Steps clarify (Phase 42-02 §A2 re-home). */
  onCancelWorkflow?: () => void;
  /** KAN-101 — spec revision cycle counter. When > 0, a violet "Spec Revision
   *  Cycle N" banner renders above the agent spine to indicate that update_specs
   *  fired and the specify→plan→analyze sub-pipeline is re-running. Generic —
   *  keyed on the counter value, never a workflow/agent-name literal (SC-001). */
  specRevisionCount?: number;
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

// The Deep-Planner card was RETIRED from the Steps overview (Phase 39 plan 02,
// human ruling) — the mock's clean overview has no planner card; its spine is the
// pipeline agents with gate strips. The planner's PROCEED/CLARIFY verdict still
// drives the run elsewhere; it is simply not surfaced as a card on this spine.

// ─── Main export ──────────────────────────────────────────────────────────────
export function AgentThinkingTab({
  agents, pipelineState, waves, runInput, originalBriefRootRunId, revisionParentVersion,
  clarifications, clarificationsLoading,
  laneGate, onApproveGate, onRejectGate, onRedoGate, onUpdateSpecsGate,
  clarifyQuestions, onSubmitClarify, onSkipClarify, onCancelWorkflow,
  specRevisionCount = 0,
}: AgentThinkingTabProps) {
  // ── The three-level Steps navigation (mirrors the mock's stepView/taskView) ──
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [selectedTaskIndex, setSelectedTaskIndex] = useState<number | null>(null);

  // ── Gate-events fetch (RUNUI-06) — the run's governance-gate rows drive the
  // "Review gate — {gate} · approved" strips interleaved in the overview spine.
  // REUSES the existing getRunGateEvents endpoint (the Audit tab's source) — no
  // new endpoint, no useWorkflow field. Tolerant: any failure → no strips.
  const runId = pipelineState?.pipelineRunId;
  const [gateEvents, setGateEvents] = useState<GateEventRow[]>([]);
  useEffect(() => {
    if (!runId) { setGateEvents([]); return; }
    let cancelled = false;
    (async () => {
      try {
        const { getRunGateEvents, getToken } = await import("@/lib/api");
        const res = await getRunGateEvents(getToken() || "", runId);
        if (!cancelled) setGateEvents(res.gate_events ?? []);
      } catch {
        if (!cancelled) setGateEvents([]);
      }
    })();
    return () => { cancelled = true; };
  }, [runId]);

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

  // ── L2 construction data (task_progress + wave_*/subagent_* reconciled into
  //    ONE nested block — STEPS-ARTIFACT-DERIVATION §2/§3) ──
  const resolvedWaves = waves ?? [];
  const completedTaskCount = pipelineState?.protoCompletedTaskCount ?? 0;
  const waveTaskUniverse = new Set(resolvedWaves.flatMap(w => w.taskIds));
  // KAN-153: prefer the authoritative total from task_loop_progress events
  // (protoTotalTasks), which is known as soon as the build loop starts its
  // first iteration — before any task completes. Falls back to wave universe
  // size (from fan-out events) or the running completed count for non-task_loop
  // pipelines. This makes ALL tasks visible upfront as "pending".
  const totalTasks = (pipelineState?.protoTotalTasks ?? 0) > 0
    ? pipelineState!.protoTotalTasks!
    : waveTaskUniverse.size > 0 ? waveTaskUniverse.size : completedTaskCount;
  const constructionIdx = agents.findIndex(a => /build|construct/i.test(a.id));
  const constructionAgent = constructionIdx >= 0 ? agents[constructionIdx] : undefined;
  const laterAgentStarted = constructionIdx >= 0 &&
    agents.slice(constructionIdx + 1).some(a => a.status !== "idle");
  // constructionComplete: the build agent's DONE badge may arrive (agent_complete)
  // before the fix-loop finishes its last sub-task, causing the validation agent to
  // start immediately (laterAgentStarted=true). Guard against that race: only treat
  // the construction as complete when EITHER:
  //   a) the pipeline has fully stopped (isRunning===false), OR
  //   b) a later agent has started AND all expected sub-tasks are confirmed done
  //      via task_progress (completedTaskCount >= totalTasks).
  // This keeps the KAN-99 N-1 cap in force until the last task_progress fires.
  const allTasksDone = totalTasks > 0 && completedTaskCount >= totalTasks;
  const constructionComplete = constructionAgent
    ? constructionAgent.status === "done" && (
        pipelineState?.isRunning === false ||
        (laterAgentStarted && allTasksDone)
      )
    : pipelineState?.isRunning === false;

  const selectedAgent = selectedAgentId ? agents.find(a => a.id === selectedAgentId) : undefined;
  // The construction section (nested waves → tasks) belongs to the build/construct
  // agent's L2 detail — shown whenever that agent is selected, even before any wave
  // arrives (the block renders a "No subagents yet." empty affordance until then).
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
            onBack={() => setSelectedTaskIndex(null)}
          />
        ) : selectedAgent ? (
          // ── L2 — agent detail ──
          <AgentDetailPanel
            agent={selectedAgent}
            onBack={() => setSelectedAgentId(null)}
            construction={isConstructionSelected ? {
              completedCount: completedTaskCount,
              totalTasks,
              isComplete: constructionComplete,
              waves: resolvedWaves,
              // KAN-153: merge planned titles (from protoPlannedTasks) with completed
              // task data (from protoCompletedTasks). Completed data wins for tasks
              // that have already finished (carries summary etc.). Planned data fills
              // in titles for tasks not yet complete, so they show their real name
              // instead of "Task N" placeholder.
              tasks: (() => {
                const planned = pipelineState?.protoPlannedTasks ?? [];
                const completed = pipelineState?.protoCompletedTasks ?? [];
                if (planned.length === 0) return completed;
                if (completed.length === 0) return planned.map(p => ({ ...p, summary: "" }));
                const completedByNum = new Map(completed.map(t => [t.number, t]));
                return planned.map(p => completedByNum.get(p.number) ?? { number: p.number, title: p.title, summary: "" });
              })(),
            } : undefined}
            onOpenTask={isConstructionSelected ? (i) => setSelectedTaskIndex(i) : undefined}
            agents={agents}
            agentIndex={agents.findIndex(a => a.id === selectedAgent.id)}
            protoCompletedTasks={pipelineState?.protoCompletedTasks}
            protoCompletedTaskCount={pipelineState?.protoCompletedTaskCount}
            dagEdges={pipelineState?.dagEdges}
          />
        ) : (
          // ── L1 — overview (mock order: stepper progress → starting-point /
          //    planner → Clarifications → agent spine + gate strips). ──
          <StepsOverviewSpine
            agents={agents}
            pipelineState={pipelineState}
            clarifications={resolvedClarifications}
            clarificationsLoading={clarificationsLoading}
            onOpenAgent={(id) => { setSelectedAgentId(id); setSelectedTaskIndex(null); }}
            gateEvents={gateEvents}
            topSlot={
              <StartingPointCard
                input={runInput}
                originalBriefRootRunId={originalBriefRootRunId}
                revisionParentVersion={revisionParentVersion}
              />
            }
            laneGate={laneGate}
            onApproveGate={onApproveGate}
            onRejectGate={onRejectGate}
            onRedoGate={onRedoGate}
            onUpdateSpecsGate={onUpdateSpecsGate}
            clarifyQuestions={clarifyQuestions}
            onSubmitClarify={onSubmitClarify}
            onSkipClarify={onSkipClarify}
            onCancelWorkflow={onCancelWorkflow}
            specRevisionCount={specRevisionCount}
          />
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
