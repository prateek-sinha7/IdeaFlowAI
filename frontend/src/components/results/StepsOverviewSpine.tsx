"use client";

// ─────────────────────────────────────────────────────────────────────────────
// Phase 39 plan 02 (RUNUI-06/08) — StepsOverviewSpine: the Steps tab's L1 view.
// A glanceable overview — a status line + segmented progress bar (both derived
// from the LIVE pipelineState/agents, SC-001/ND-D), the reused ClarificationsCard,
// and a COMPACT navigable agent spine (one row per visible agent → opens L2).
// Between the rows it renders the run's gate strips: an inline "Awaiting you"
// gate/clarify card (the REUSED InlineGateActions / InlineClarifyActions — same
// submit channels, INV-12) while a gate is live, an "approved by you" strip once
// it settles. A failed run closes with a "Pipeline halted" banner. Token-
// reskinned off the Phase-32 tokens (no gray-* palette).
// ─────────────────────────────────────────────────────────────────────────────

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, ChevronRight, ChevronsRight, XCircle, ListChecks, RotateCw, ShieldAlert, RefreshCw, GitBranch, CornerUpLeft, AlertTriangle, Wrench } from "lucide-react";
import type { AgentRunState, ClarifyRound, PipelineRunState } from "@/types/index";
import type { GateEventRow } from "@/lib/api";
import { InlineGateActions } from "@/components/chat/InlineGateActions";
import { InlineClarifyActions } from "@/components/chat/InlineClarifyActions";
import type { GateContext } from "@/components/chat/RunChatLane";
import type { ClarifyQuestion } from "@/types/index";
import type { ClarifyResponse } from "@/components/chat/InlineClarifyActions";
import { ClarificationsCard } from "./ClarificationsCard";
import { formatDuration, formatTokenCount, sumWorkers } from "@/lib/runStats";
import { routes } from "@/lib/routes";

// ─── Divert-link spine row — same source/target relationship
// RevisionFamilyView's DivertBadge renders as a Run-History breadcrumb,
// surfaced here inline in the Steps spine: "target" (this run was continued
// INTO by a divert) prepends "Continued from {A}" before the agent rows;
// "source" (this run diverted OUT) appends "Diverted to {X}" after them —
// same shape a -> b -> c -> {X} / {A} -> x -> y -> z the relationship
// actually has.
export interface StepsDivertLink {
  direction: "source" | "target";
  otherRunId: string;
  otherTitle: string;
}

function DivertLinkRow({ link }: { link: StepsDivertLink }) {
  const router = useRouter();
  const Icon = link.direction === "source" ? GitBranch : CornerUpLeft;
  const text = link.direction === "source"
    ? `Diverted to ${link.otherTitle} →`
    : `← Continued from ${link.otherTitle}`;
  return (
    <button
      type="button"
      data-testid="steps-divert-link-row"
      onClick={() => router.push(routes.runStream(link.otherRunId))}
      aria-label={link.direction === "source" ? `Diverted to ${link.otherTitle}, open triggered run` : `Continued from ${link.otherTitle}, open originating run`}
      className="w-full flex items-center gap-2.5 rounded-[11px] border border-transparent px-3 py-2.5 mb-1.5 text-left transition-colors hover:bg-surface-warm cursor-pointer"
    >
      <span className="w-[18px] h-[18px] flex-none rounded-full border-[1.5px] border-brand-border bg-brand-fill grid place-items-center">
        <Icon className="h-2.5 w-2.5 text-brand" />
      </span>
      <span className="min-w-0 flex-1 truncate leading-[1.4] text-[13px] font-medium font-[Manrope] text-brand">{text}</span>
      <ChevronRight className="h-4 w-4 flex-none text-line-faint" />
    </button>
  );
}

// Live per-row activity word (RUNUI-xx) — derived from the SAME toolCalls/
// thinkingText the Thinking tab already reads, no new event/store plumbing.
// A quoted live snippet of the actual thinking text was tried first and
// dropped — variable-length content swapping in/out read as jitter no matter
// how it was boxed. A short, FIXED vocabulary of verbs (each shimmering,
// bold) is stable by construction: the words never change length or content,
// only which one is showing.
// Capped vocabulary — Thinking / Reading / Writing / Calling tools only.
function describeToolCall(tool: string): string {
  if (tool === "write_file" || tool === "edit_file") return "Writing…";
  if (tool === "read_file") return "Reading…";
  return "Calling tools…";
}

// thinkingText ACCUMULATES and never clears — once an agent has thought at
// all, "is there thinking text?" is true for the rest of the run, so it was
// masking tool calls that often start+finish inside one polling tick. A tool
// call's own `timestamp` (set when it's issued) is used to hold its verb on
// screen for a short window after it lands, so a fast write_file/read_file
// is actually visible instead of instantly buried under "Thinking…".
const TOOL_RESULT_HOLD_MS = 1800;

/** The in-flight task for the agent running a build loop, when there is one.
 *  `task_loop_progress` (task_loop.py:319-329) carries `task_number`,
 *  `total_tasks` and `agent_id`; the agent id is what lets this line belong to
 *  ONE row rather than every row. Sub-agent GROUPS (parallel_group / fanout)
 *  do not emit this event — they emit subagent_spawned/subagent_result, which
 *  carry no parent id and so cannot be attributed here. */
function taskProgressLine(
  agent: AgentRunState,
  pipeline?: { protoCurrentTask?: number; protoTotalTasks?: number; protoTaskAgentId?: string },
): string | null {
  if (!pipeline?.protoTaskAgentId || pipeline.protoTaskAgentId !== agent.id) return null;
  const current = pipeline.protoCurrentTask ?? 0;
  const total = pipeline.protoTotalTasks ?? 0;
  if (current <= 0) return null;
  return total > 0 ? `Executing task ${current} of ${total}…` : `Executing task ${current}…`;
}

/** "Wave 5/50" — the parent step's progress through its wave, derived from the
 *  child worker rows (never from a second parent re-render — a wave clones one
 *  agent N times, all sharing the parent's agent_id, INV per this component's
 *  agent_id-keyed row). `waveTotal` is read off any worker entry (the backend
 *  stamps the same value on every worker of a wave); falls back to the number
 *  of workers seen so far when absent.
 *
 *  A wave_scheduler step can run several SEQUENTIAL waves (wave_scheduler.py's
 *  `for wave_index, wave in enumerate(waves)`), so `waveWorkers` can carry
 *  entries from more than one `waveIndex`. When it does, the line is scoped to
 *  the current (in-flight, else latest) wave's workers only — otherwise a
 *  finished wave 0 and an in-flight wave 1 would sum into one misleading
 *  count — and prefixed "Wave {n} · " to say which wave that is. */
function waveProgressLine(agent: AgentRunState): string | null {
  const workers = agent.waveWorkers;
  if (!workers || workers.length === 0) return null;
  const waveIndices = Array.from(
    new Set(workers.map((w) => w.waveIndex).filter((v): v is number => v != null)),
  );
  const multiWave = waveIndices.length > 1;
  const currentWaveIndex = multiWave
    ? workers.find((w) => w.status !== "done")?.waveIndex ?? Math.max(...waveIndices)
    : undefined;
  const scoped = currentWaveIndex != null ? workers.filter((w) => w.waveIndex === currentWaveIndex) : workers;
  const total = scoped.find((w) => w.waveTotal != null)?.waveTotal ?? scoped.length;
  const done = scoped.filter((w) => w.status === "done").length;
  const current = Math.min(done + (scoped.some((w) => w.status === "running") ? 1 : 0), total) || 1;
  return currentWaveIndex != null ? `Wave ${currentWaveIndex + 1} · ${current}/${total}` : `Wave ${current}/${total}`;
}

// Exported for unit test only — the component-level path needs @testing-library,
// and this is a pure function of (agent, now, pipeline).
export function liveActivityLine(
  agent: AgentRunState,
  nowMs: number,
  pipeline?: { protoCurrentTask?: number; protoTotalTasks?: number; protoTaskAgentId?: string },
): string | null {
  const calls = agent.toolCalls ?? [];
  const last = calls.length > 0 ? calls[calls.length - 1] : null;

  // Highest priority: naming the task in flight beats any generic verb. A build
  // loop makes constant tool calls, so a tool verb would otherwise mask it.
  const taskLine = taskProgressLine(agent, pipeline);
  if (taskLine) return taskLine;

  if (last && last.result === null) return describeToolCall(last.tool);

  if (last) {
    const sinceCall = nowMs - Date.parse(last.timestamp || "");
    if (Number.isFinite(sinceCall) && sinceCall >= 0 && sinceCall < TOOL_RESULT_HOLD_MS) {
      return describeToolCall(last.tool);
    }
  }

  // `output` is checked ALONGSIDE `thinkingText`, not instead of it. The engine
  // emits `agent_thinking` only for extended-thinking providers
  // (execution_engine/engine.py:4076-4082), so for most models `thinkingText`
  // stays empty for the whole run while `agent_chunk` fills `output`. Keying the
  // line on `thinkingText` alone meant any agent that streamed ordinary output
  // and called no tools fell through to "Starting…" and stayed there while its
  // text was visibly arriving on screen. AgentDetailPanel.tsx:971-978 documents
  // the same finding and applies the same output fallback.
  // A reasoning stream and an output stream are DIFFERENT states and must not
  // share a verb. `thinkingText` is the model reasoning before it answers;
  // `output` is the answer itself already streaming to screen. Collapsing both
  // into "Thinking…" told the user the agent was still deliberating while its
  // text was visibly landing.
  // OUTPUT IS CHECKED FIRST, and the order is load-bearing. Both fields
  // accumulate and neither ever clears (see the thinkingText note above), so
  // priority here is really "which state did the agent reach LAST". An agent
  // reasons and then answers, so any output at all means reasoning is over.
  // Checking thinkingText first would pin an extended-thinking model on
  // "Thinking…" for its whole run while its answer streamed underneath — the
  // same wrong-state bug this line already had for non-thinking models.
  if ((agent.output ?? "").trim()) return "Writing…";
  if ((agent.thinkingText ?? "").trim()) return "Thinking…";
  if (last) return describeToolCall(last.tool);

  return "Starting…";
}

// Re-renders once a second so liveActivityLine's tool-call hold window actually
// expires even if no other event happens to arrive in between — without this the
// "now" reading would only refresh whenever the agent prop itself changed.
//
// Returns the timestamp rather than rendering nothing and letting the caller read
// `Date.now()` inline: calling `Date.now()` during render is impure
// (react-hooks/purity) because it makes the render output depend on something
// other than props/state. Sourcing "now" from state that the interval advances
// keeps render a pure function of state with the identical refresh cadence.
function useNow(intervalMs: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}

function AgentActivityLine({
  agent,
  pipelineState,
}: {
  agent: AgentRunState;
  pipelineState?: PipelineRunState;
}) {
  const now = useNow(1000);
  const line = liveActivityLine(agent, now, pipelineState);
  if (!line) return null;

  return (
    <span className="flex items-center gap-1.5 text-[12.5px] font-[Manrope]">
      {line === "Starting…" ? (
        <span className="text-ink-400">{line}</span>
      ) : (
        // leading-none clipped the glyph's ascenders/descenders at some zoom
        // levels (background-clip: text is sensitive to a too-tight line box)
        // — a normal line-height gives it room; items-center on the parent
        // still keeps it vertically centered against the name.
        <span key={line} className="slide-in-right shimmer-text py-0.5 leading-normal font-bold">{line}</span>
      )}
    </span>
  );
}

export interface StepsOverviewSpineProps {
  agents: AgentRunState[];
  pipelineState?: PipelineRunState;
  clarifications?: ClarifyRound[];
  clarificationsLoading?: boolean;
  onOpenAgent: (agentId: string) => void;
  /** Rendered AFTER the pipeline-stepper progress and BEFORE the Clarifications
   *  card — the repositioned Starting-point card (the single live-data surface the
   *  mock's clean overview omits; kept below the stepper, never above it — mock
   *  overview order, Hexaware Run.dc.html :294-354). */
  topSlot?: React.ReactNode;
  /** The run's governance-gate rows (from getRunGateEvents) — an approved gate is
   *  rendered as a "Review gate — {gate} · Approved" strip AFTER the agent row it
   *  maps to (by the event's `step` field), matching the mock's settled spine. */
  gateEvents?: GateEventRow[];
  // Reused inline gate / clarify (SC-2, INV-12 — same submit channels)
  laneGate?: GateContext;
  onApproveGate?: (gateKey: string, editedContent?: string) => void;
  onRejectGate?: (gateKey: string) => void;
  onRedoGate?: (gateKey: string, instructions: string) => void;
  onUpdateSpecsGate?: (gateKey: string, report: string) => void;
  clarifyQuestions?: ClarifyQuestion[];
  onSubmitClarify?: (responses: ClarifyResponse[]) => void;
  onSkipClarify?: () => void;
  /** Cancel the active pipeline from the inline Steps clarify (Phase 42-02 §A2 re-home). */
  onCancelWorkflow?: () => void;
  /** KAN-101 — spec revision cycle counter. When > 0, a violet "Spec Revision
   *  Cycle N" banner renders above the agent rows to give the user context that
   *  update_specs fired and specify→plan→analyze is re-running. Generic, keyed on
   *  the counter value (SC-001 — never a workflow/agent-name literal). */
  specRevisionCount?: number;
  /** This run's divert relationship (if any) to another run — see StepsDivertLink. */
  divertLink?: StepsDivertLink | null;
}

// The "Awaiting you" card chrome from the mock (brand-tinted, focus-ring shadow).
// Positioning only. The gate and clarify components each render their OWN card
// now (border, radius, brand-filled ask block, shadow) so the ask reads as the
// card's opening rather than as a row inside someone else's chrome — wrapping
// them in a second bordered card gave every prompt two frames and two headers.
function AwaitingCard({ children }: { children: React.ReactNode }) {
  return <div className="mb-3 ml-2">{children}</div>;
}

// The inline "Awaiting you" review-gate card — the REUSED generic InlineGateActions
// (same approve_review submit channel + KAN-100 terminal fence, INV-12) under the
// mock's gate-card chrome. Rendered inline after the paused agent's row when the
// gate maps to a visible agent, else as a fallback at the foot of the spine so an
// active gate is NEVER lost (correctness — the gate must stay reachable).
function GateAwaitingCard({
  laneGate, isRunning, reviewsPriorStepName, onApprove, onReject, onRedo, onUpdateSpecs,
}: {
  laneGate: GateContext;
  isRunning: boolean;
  /** BUG A11-2 — see InlineGateActions' own prop doc. */
  reviewsPriorStepName?: string | null;
  onApprove: (gateKey: string, editedContent?: string) => void;
  onReject?: (gateKey: string) => void;
  onRedo?: (gateKey: string, instructions: string) => void;
  onUpdateSpecs?: (gateKey: string, report: string) => void;
}) {
  return (
    <AwaitingCard>
        {/* The "Review gate — {agent} / Awaiting you" header row is gone: the
            card's own ask block opens with "Waiting on you" over the actual
            question, and names the agent on the evidence label below it. Two
            headers saying the same thing pushed the question below the fold. */}
        <InlineGateActions
          agentId={laneGate.agentId}
          agentName={laneGate.agentName}
          output={laneGate.output}
          gateKey={laneGate.gateKey}
          redoable={laneGate.redoable}
          updateSpecsEligible={laneGate.updateSpecsEligible}
          artifactKind={laneGate.artifactKind}
          revisionCycle={laneGate.revisionCycle}
          revisionInFlight={laneGate.revisionInFlight}
          isPipelineRunning={isRunning}
          approveLabel={laneGate.approveLabel}
          reviewsPriorStepName={reviewsPriorStepName}
          onApprove={onApprove}
          onReject={onReject ?? (() => {})}
          onRedo={onRedo}
          onUpdateSpecs={onUpdateSpecs}
        />
    </AwaitingCard>
  );
}

// The settled "Review gate — {gate} · approved by you · Approved" strip, from a
// live approved gate-event row (Hexaware Run.dc.html :345-351). Interleaved after
// the agent row the gate maps to (event.step === agent.id).
function GateApprovedStrip({ gate }: { gate: string }) {
  return (
    <div className="flex items-center gap-2.5 mb-3 ml-2 px-3.5 py-2.5 border border-brand-border bg-brand-violet-tint rounded-[11px]">
      <div className="w-[26px] h-[26px] flex-none rounded-[7px] bg-surface-near-black grid place-items-center">
        <ListChecks className="h-3.5 w-3.5 text-brand-on-dark" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="m-0 text-[12px] font-semibold text-ink-900 font-[Manrope]">Review gate — {gate}</p>
        <p className="mt-0.5 m-0 text-[11px] text-[#8A86B0]">Paused for review · approved by you</p>
      </div>
      <span className="inline-flex items-center gap-1.5 text-[10px] font-semibold text-ink-700 font-[Manrope]"><Check className="h-3 w-3 text-ink-900" />Approved</span>
    </div>
  );
}

// KAN-123: Inline "Blocked by the security gate" explanation card rendered after
// a failed agent row whose error signal indicates a security / exec / hook block.
// Keyed on generic error-string signals (SC-001 — never an agent-id/name literal).
function SecurityGateBlockedCard({ error }: { error: string }) {
  const isScan = /secret|credential|\bscan\b/i.test(error);
  const isExec = /exec.*denied|exec.*off|code.*denied/i.test(error);
  const body = isScan
    ? "A secret or credential was detected in the agent\u2019s write payload. The workspace\u2019s security policy blocked the write and halted the run before any data was persisted."
    : isExec
    ? "The agent requested code execution, but \u2018exec\u2019 is off for this workspace. The security gate blocked the operation and halted the run before any code ran."
    : "The security gate blocked this step\u2019s operation. Check the Audit tab for the full record including detector, match, and action details.";
  return (
    <div className="mb-3 ml-2 overflow-hidden rounded-[12px] border border-status-failed-border bg-status-failed-fill">
      <div className="flex items-center gap-2.5 border-b border-status-failed-border px-3.5 py-2.5">
        <div className="w-[26px] h-[26px] flex-none rounded-[7px] bg-status-failed grid place-items-center">
          <ShieldAlert className="h-3.5 w-3.5 text-white" strokeWidth={1.8} />
        </div>
        <p className="m-0 flex-1 font-sans text-[12px] font-semibold text-status-failed-strong">Blocked by the security gate</p>
      </div>
      <p className="px-3.5 py-3 font-serif text-[12px] leading-[1.6] text-ink-700">{body}</p>
    </div>
  );
}

/** Returns true when the agent error string indicates a security/exec/hook block
 *  (generic signal check — SC-001, no agent-id literal). */
function isSecurityBlock(error: string | null): boolean {
  if (!error) return false;
  return /security.*gate|blocked.*security|exec.*denied|exec.*off|secret.*scan|secret.*blocked|credential.*blocked|hook.*block/i.test(error);
}

// wave_skipped — a wave that ran and dispatched ZERO tasks. Rendered as an
// explicit amber attention card, never a green check: the whole point is that
// "succeeded while doing nothing" was previously invisible.
function WaveSkippedCard({ reason }: { reason: string }) {
  return (
    <div data-testid="wave-skipped-card" className="mb-3 ml-2 overflow-hidden rounded-[12px] border border-status-amber-border bg-status-amber-fill">
      <div className="flex items-center gap-2.5 px-3.5 py-2.5">
        <div className="w-[26px] h-[26px] flex-none rounded-[7px] bg-status-amber grid place-items-center">
          <AlertTriangle className="h-3.5 w-3.5 text-white" strokeWidth={1.8} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="m-0 font-sans text-[12px] font-semibold text-status-amber">Wave skipped — no tasks to run</p>
          {reason && <p className="mt-0.5 m-0 text-[11px] text-ink-700">{reason}</p>}
        </div>
      </div>
    </div>
  );
}

// wave_repair — the engine detected and re-dispatched tasks a prior wave pass
// dropped. A warning, not a failure: the run recovered on its own.
function WaveRepairRow({ count }: { count: number }) {
  return (
    <div data-testid="wave-repair-row" className="flex items-center gap-2 mb-3 ml-2 px-3.5 py-2 rounded-[11px] border border-status-amber-border bg-status-amber-fill">
      <Wrench className="h-3.5 w-3.5 flex-none text-status-amber" />
      <span className="text-[11.5px] text-status-amber font-[Manrope]">{count} dropped task{count !== 1 ? "s" : ""} repaired</span>
    </div>
  );
}

export function StepsOverviewSpine({
  agents, pipelineState, clarifications, clarificationsLoading, onOpenAgent, topSlot, gateEvents,
  laneGate, onApproveGate, onRejectGate, onRedoGate, onUpdateSpecsGate,
  clarifyQuestions, onSubmitClarify, onSkipClarify, onCancelWorkflow,
  specRevisionCount = 0, divertLink,
}: StepsOverviewSpineProps) {
  // ISS-722 (QA-SG-001): `agents` is the client-built roster, empty until the
  // first roster frame arrives, so this header read "0 / 0" against a live
  // 5-agent run while the notification panel — reading the run record's own
  // agent_count — read "0 of 5". Fall back to that same known count for the
  // window before the roster exists; `agents.length` still wins once it does.
  const total = agents.length || (pipelineState?.agentCount ?? 0);
  const isRunning = pipelineState?.isRunning ?? false;
  // ISS-317: a pipeline that is actively running is never "failed". Gate the
  // derived flag on !isRunning so a leftover per-agent `error` status can never
  // pin this panel on "Run failed" while the header reads "Running".
  //
  // ISS-701 / ISS-764: per-agent status is not a run-level verdict at all. A
  // terminal `degraded` run legitimately carries an `error` agent — that is what
  // degraded MEANS — and a run stopped after one agent errored keeps that status
  // too (useWorkflow.ts's pipeline_cancelled leaves an already-errored agent
  // untouched). OR'ing `agents.some(status === "error")` in here let either case
  // steamroll its own terminal marker and read "Run failed". The run-level
  // markers are mutually exclusive and always stamped by terminalMarkers()
  // (useWorkflow.ts), so `failed` comes from `pipelineState.failed` alone —
  // matching how LaneRunHeader.tsx keeps failed/degraded/cancelled independent.
  const failed = !isRunning && (pipelineState?.failed ?? false);

  // ── FIX-182: construction agent "done" guard ──────────────────────────────
  // agent_complete fires after EACH task-loop iteration, momentarily setting the
  // build agent's status to "done" before the next task_loop_progress fires a new
  // agent_start. Using agent.status === "done" directly causes a premature DONE
  // badge and progress-bar fill. Mirror the constructionComplete logic from
  // AgentThinkingTab so the build agent only shows DONE when all tasks are confirmed
  // done OR the pipeline has stopped. Generic — keyed on id pattern, SC-001.
  const completedTaskCount = pipelineState?.protoCompletedTaskCount ?? 0;
  const protoTotalTasks = pipelineState?.protoTotalTasks ?? 0;
  const totalTasks = protoTotalTasks > 0 ? protoTotalTasks : completedTaskCount;
  const allTasksDone = totalTasks > 0 && completedTaskCount >= totalTasks;
  // The guard exists for a TASK LOOP, where agent_complete fires per iteration.
  // It must therefore apply only where a task loop is actually reporting: the
  // condition it waits on, `allTasksDone`, is derived from task_progress counts.
  //
  // A wave-scheduled step reports waves and subagents instead, so those counts
  // stay 0, `allTasksDone` is permanently false, and the guard withheld DONE
  // from a step that had genuinely finished — an empty circle beside its own
  // duration, and a step missing from the "N / N agents" count, for the whole
  // rest of the run. The id regex alone had matched it, because it was called
  // `pb-build`.
  //
  // Keying on the data leaves every task_loop pipeline byte-identical and stops
  // the guard firing where it has nothing to wait for.
  const hasTaskLoopProgress = totalTasks > 0;
  const constructionIdx = hasTaskLoopProgress
    ? agents.findIndex(a => /build|construct/i.test(a.id))
    : -1;
  const laterAgentStarted = constructionIdx >= 0 &&
    agents.slice(constructionIdx + 1).some(a => a.status !== "idle");
  const constructionAgentIsReallyDone = (idx: number): boolean => {
    if (idx !== constructionIdx) return agents[idx]?.status === "done";
    const agent = agents[idx];
    if (!agent || agent.status !== "done") return false;
    return !isRunning || (laterAgentStarted && allTasksDone);
  };
  const guardedCompletedCount = agents.filter((_, i) => constructionAgentIsReallyDone(i)).length;
  // ── end FIX-182 ───────────────────────────────────────────────────────────

  const statusLabel = failed ? "Run failed" : isRunning ? "Running"
    // Task 11.5 (Req 20): "degraded" MUST NOT read as "Run complete". Both the
    // label text and the non-color indicator below differ from the success state.
    : (pipelineState?.degraded) ? "Run degraded"
    : "Run complete";

  const hasClarify = !!(clarifyQuestions && clarifyQuestions.length > 0 && onSubmitClarify);
  const gateActive = !!laneGate && isRunning && !!onApproveGate;
  const phase =
    failed ? null
    : hasClarify ? { pill: "CLARIFY", label: "Waiting on your answers", live: false }
    : gateActive ? { pill: "REVIEW", label: "Paused for your approval", live: false }
    : isRunning ? { pill: "BUILDING", label: `Pipeline running · ${guardedCompletedCount} / ${total}`, live: true }
    : null;

  const totalDuration = pipelineState?.totalDuration;
  const metaBits = [
    total > 0 ? `${guardedCompletedCount} / ${total} agents` : null,
    totalDuration ? formatDuration(totalDuration) : null,
  ].filter(Boolean).join(" · ");

  // The rows report agent time; the header reports wall clock. Those differ by the time
  // the run spent parked at a review gate, which belongs to no step — so without this line
  // the two can never be reconciled by a reader. `busySeconds` is an interval union, so
  // concurrently dispatched steps are counted once (run faba87c9: five readers overlapping
  // by 199s). Absent on runs recorded before this shipped, hence the guard.
  const busySeconds = pipelineState?.busySeconds ?? 0;
  const waitingSeconds = pipelineState?.waitingSeconds ?? 0;
  const timeSplit = busySeconds >= 1
    ? [
        `${formatDuration(busySeconds)} working`,
        waitingSeconds >= 1 ? `${formatDuration(waitingSeconds)} awaiting review` : null,
      ].filter(Boolean).join(" · ")
    : null;

  const notRun = failed ? agents.filter(a => a.status === "idle").length : 0;
  const failedAgent = agents.find(a => a.status === "error");

  const gateAgentMatches = !!laneGate && agents.some(a => a.id === laneGate.agentId);
  const showGateFallback = !!laneGate && isRunning && !!onApproveGate && !gateAgentMatches;

  // BUG A11-2 — a `before-human` gate's own step has NOT started yet (still
  // "idle": gates run before the step's own strategy dispatch,
  // agents/capabilities/gates/human.py), so review_gate_ready's agentId/output
  // are the GATE's step identity while the content belongs to whichever step
  // ran immediately before it. The wire carries no discriminator for this
  // (engine.py's open_review_gate emit site has none), so it is derived here:
  // the engine is a deterministic SERIAL sequencer (CLAUDE.md), so the nearest
  // preceding "done" agent in this same live roster IS the one whose output
  // review_gate_ready is actually showing (ectx.last_streamed = results[-1]).
  // `undefined` — an ordinary post-step gate (the gated agent has already
  // started/finished): InlineGateActions keeps its existing "What {agentName}
  // wrote" label. `null` — identified as a before-gate but no prior step
  // found (e.g. gate on the very first step): InlineGateActions suppresses
  // the mismatched evidence block instead of mislabeling it.
  const gateTargetIdx = laneGate ? agents.findIndex(a => a.id === laneGate.agentId) : -1;
  const gateIsPreStep = !!laneGate && (gateTargetIdx === -1 || agents[gateTargetIdx].status === "idle");
  const reviewsPriorStepName: string | null | undefined = !gateIsPreStep
    ? undefined
    : (gateTargetIdx > 0 ? agents[gateTargetIdx - 1] : [...agents].reverse().find(a => a.status === "done"))
      ?.name ?? null;
  const approvedGatesByAgent = (gateEvents ?? [])
    .filter(g => g.step && (g.outcome ?? "").toLowerCase().includes("approv"))
    .reduce<Record<string, GateEventRow[]>>((acc, g) => {
      (acc[g.step as string] ||= []).push(g);
      return acc;
    }, {});

  return (
    <div className="max-w-[760px] mx-auto">
      {/* status line + progress */}
      <div className="mb-5">
        <div className="flex items-center gap-2.5 mb-3">
          {failed ? (
            <span className="w-[18px] h-[18px] flex-none rounded-full bg-status-failed grid place-items-center"><XCircle className="h-2.5 w-2.5 text-white" /></span>
          ) : isRunning ? (
            <span className="w-[18px] h-[18px] flex-none rounded-full bg-brand-fill border-[1.5px] border-brand grid place-items-center"><span className="w-1.5 h-1.5 rounded-full bg-brand animate-pulse" /></span>
          ) : pipelineState?.degraded ? (
            // Task 11.5 (Req 20): amber circle + distinct icon — not a colour
            // variant of the success state. AT reads "Run degraded" from statusLabel.
            <span className="w-[18px] h-[18px] flex-none rounded-full bg-[var(--status-amber-fill)] border border-[var(--status-amber-border)] grid place-items-center" aria-hidden="true"><AlertTriangle className="h-2.5 w-2.5 text-status-amber" strokeWidth={2} /></span>
          ) : (
            <span className="w-[18px] h-[18px] flex-none rounded-full bg-surface-near-black grid place-items-center"><Check className="h-2.5 w-2.5 text-white" /></span>
          )}
          {phase ? (
            <>
              <span className="text-[15px] font-semibold text-ink-900 font-[Manrope]">{phase.label}</span>
              <span className="inline-flex items-center gap-1.5 text-[9.5px] font-semibold uppercase tracking-[0.05em] text-brand bg-brand-fill border border-brand-border px-2 py-1 rounded-[6px] font-[Manrope]">
                <span className={`w-1.5 h-1.5 rounded-full bg-brand ${phase.live ? "animate-pulse" : ""}`} />
                {phase.pill}
              </span>
            </>
          ) : (
            <span className="text-[15px] font-semibold text-ink-900 font-[Manrope]">{statusLabel}</span>
          )}
          <span className="flex-1" />
          {metaBits && <span className="text-[11.5px] text-ink-300 font-mono">{metaBits}</span>}
        </div>
        {timeSplit && (
          <div
            data-testid="steps-time-split"
            title="Wall clock, split into time with an agent running and time paused for your review. Concurrent steps count once."
            className="flex justify-end mb-2 text-[11px] text-ink-300 font-mono"
          >
            {timeSplit}
          </div>
        )}
        {/* Progress bar — suppress during clarify (agents are from a different run) */}
        {total > 0 && !hasClarify && (
          <div className="flex gap-[3px] h-[5px] rounded-[3px] overflow-hidden">
            {agents.map((a, i) => (
              <div key={i} className={`flex-1 ${
                constructionAgentIsReallyDone(i) ? "bg-brand" :
                a.status === "running" || a.status === "thinking" ? "bg-brand animate-pulse" :
                a.status === "error" ? "bg-status-failed" :
                a.status === "done" ? "bg-brand" :
                "bg-line-faint"
              }`} />
            ))}
          </div>
        )}
      </div>

      {/* Repositioned live-data card (Starting point) — below the stepper, above
          Clarifications, per the mock's overview order. */}
      {topSlot && <div className="mb-2 space-y-3">{topSlot}</div>}

      {/* Clarifications (reused; renders nothing on a PROCEED run) */}
      <div className="mb-2">
        <ClarificationsCard clarifications={clarifications} loading={clarificationsLoading} />
      </div>

      {/* Clarify — AWAITING you (inline answer UI, reused InlineClarifyActions) */}
      {clarifyQuestions && clarifyQuestions.length > 0 && onSubmitClarify && (
        <AwaitingCard>
          {/* Header row dropped for the same reason as the gate's — the card
              opens with "Before I build" over the real ask. */}
          <InlineClarifyActions questions={clarifyQuestions} onSubmitAnswers={onSubmitClarify} onCancelWorkflow={onCancelWorkflow} />
        </AwaitingCard>
      )}

      {/* KAN-101 — spec revision cycle banner. Shown when update_specs has fired
          (specRevisionCount > 0) so the user knows specify→plan→analyze is re-running.
          Violet to match the old UI's PrototypePipelineView revision banner. Generic —
          keyed on the counter value, never a workflow/agent-name literal (SC-001). */}
      {specRevisionCount > 0 && (
        <div className="flex items-center gap-2.5 mb-3 px-3.5 py-3 rounded-[12px] bg-[#F4F2FB] border border-[#DED9F7]">
          <div className="w-[26px] h-[26px] flex-none rounded-[7px] bg-brand grid place-items-center">
            <RefreshCw className="h-3.5 w-3.5 text-white" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="m-0 text-[12px] font-semibold text-brand font-[Manrope]">Spec Revision Cycle {specRevisionCount}</p>
            <p className="mt-0.5 m-0 text-[11px] text-[#8A86B0]">Spec &amp; plan are being revised based on the analysis report</p>
          </div>
        </div>
      )}

      {/* "Continued from {A}[, step S]" — this run is the divert TARGET, so it
          leads the spine, ahead of its own agent rows (mirrors a -> b -> c ->
          {X} / {A} -> x -> y -> z: the divert is the reason this run exists,
          so it comes first). Shown regardless of hasClarify — it describes a
          different, already-settled run, not this run's own in-flight state. */}
      {divertLink?.direction === "target" && <DivertLinkRow link={divertLink} />}

      {/* compact navigable agent rows + gate strips.
          Defense-in-depth: hide ALL agent rows while the run is paused at clarify.
          The run hasn't started its agent phase yet — any agent visible here belongs
          to a concurrent background run that leaked into the viewport. Showing them
          would confuse the user into thinking this run has already started building. */}
      {!hasClarify && agents.map((agent, agentIdx) => {
        const isDone = constructionAgentIsReallyDone(agentIdx);
        const isRun = agent.status === "running" || agent.status === "thinking";
        const isErr = agent.status === "error";
        const isIdle = agent.status === "idle";
        const isSkipped = agent.status === "skipped";
        const navigable = !isIdle && !isSkipped;
        // A step that ran more than once shows what the LAST pass cost (that is the output
        // on screen) and what ALL of them cost. Before this the row kept only the former,
        // so run faba87c9's Task Planner — seven passes, 17m 22s — read "2m 23s".
        const multiPass = (agent.passCount ?? 0) > 1;
        const rowMeta = [
          agent.duration != null ? formatDuration(agent.duration) : null,
          multiPass && agent.cumulativeDuration ? `${formatDuration(agent.cumulativeDuration)} total` : null,
          // A wave step's usage is its members' sum, live while the wave runs.
          (agent.totalTokens || sumWorkers(agent, "totalTokens")) > 0
            ? `${formatTokenCount(agent.totalTokens || sumWorkers(agent, "totalTokens"))} tok` : null,
        ].filter(Boolean).join(" · ");

        const gateHere = laneGate?.agentId === agent.id;
        const gateAwaiting = gateHere && isRunning && !!onApproveGate;
        const approvedGates = approvedGatesByAgent[agent.id] ?? [];

        // A wave step (e.g. "Screen Builders") — the 51 agent_start/agent_complete
        // events all carry the SAME agent_id (a wave clones one agent N times), so
        // this row stays ONE parent node by construction. The wave progress summary
        // ("Wave 2 · 2/3") renders inline below; the per-worker rows themselves live
        // on the step's L2 detail page, not here (INV-12 — one representation only,
        // this row is the compact spine, not the drill-down).
        const waveLine = isRun ? waveProgressLine(agent) : null;
        const isWaveSkipped = !!agent.waveSkipped;

        return (
          <div key={agent.id}>
            <button
              type="button"
              data-testid="steps-agent-row"
              disabled={!navigable}
              onClick={() => navigable && onOpenAgent(agent.id)}
              className={`w-full flex items-center gap-2.5 rounded-[11px] border px-3 py-2.5 mb-1.5 text-left transition-colors ${
                isRun ? "bg-brand-violet-tint border-brand-border" : "border-transparent"
              } ${
                navigable ? "hover:bg-surface-warm cursor-pointer" : "cursor-default"
              }`}
            >
              {isWaveSkipped ? (
                <span className="w-[18px] h-[18px] flex-none rounded-full bg-status-amber grid place-items-center"><AlertTriangle className="h-2.5 w-2.5 text-white" /></span>
              ) : isDone ? (
                <span className="w-[18px] h-[18px] flex-none rounded-full bg-surface-near-black grid place-items-center"><Check className="h-2.5 w-2.5 text-white" /></span>
              ) : isSkipped ? (
                <span className="w-[18px] h-[18px] flex-none rounded-full border-[1.5px] border-line-faint bg-surface-white grid place-items-center"><ChevronsRight className="h-3 w-3 text-ink-300" /></span>
              ) : isRun ? (
                <span className="w-[18px] h-[18px] flex-none rounded-full bg-brand-fill border-[1.5px] border-brand grid place-items-center shadow-[0_0_0_4px_rgba(60,44,218,0.15)]"><span className="w-1.5 h-1.5 rounded-full bg-brand animate-pulse" /></span>
              ) : isErr ? (
                <span className="w-[18px] h-[18px] flex-none rounded-full bg-status-failed grid place-items-center"><XCircle className="h-2.5 w-2.5 text-white" /></span>
              ) : (
                <span className="w-[18px] h-[18px] flex-none rounded-full border-[1.5px] border-line-faint bg-surface-white" />
              )}
              <span className="min-w-0 flex items-center leading-none gap-1.5">
                <span className={`leading-none text-[13px] font-medium font-[Manrope] ${isIdle || isSkipped ? "text-ink-300" : "text-ink-900"}`}>{agent.name}</span>
                {isRun && (
                  <>
                    <span className="leading-none text-ink-300">·</span>
                    {waveLine && <span className="leading-none text-[11px] font-mono text-brand mr-1">{waveLine}</span>}
                    <AgentActivityLine agent={agent} pipelineState={pipelineState} />
                  </>
                )}
              </span>
              {isWaveSkipped && <span className="text-[9px] text-status-amber bg-status-amber-fill border border-status-amber-border px-1.5 py-0.5 rounded">Skipped — 0 tasks</span>}
              {isIdle && failed && <span className="text-[9px] text-status-amber bg-status-amber-fill border border-status-amber-border px-1.5 py-0.5 rounded">Not run</span>}
              {isSkipped && <span className="text-[9px] text-ink-300 bg-surface-warm border border-line-faint px-1.5 py-0.5 rounded">Skipped</span>}
              {/* A step that ran more than once. Without it a later pass is
                  indistinguishable from the first — the row simply re-runs and the
                  numbers change with no explanation. Reads `passCount` (every dispatch)
                  rather than `visit_count` (conditional loop-backs only), which is why
                  run faba87c9's seven spec-revision runs of the Task Planner were
                  unbadged while the Synthesizer's one loop-back was.
                  Suppressed on the construction agent: its task loop emits an
                  agent_start per TASK (FIX-182 above), so a pass count there would read
                  as eleven re-runs of a step that ran once. The cumulative duration is
                  still correct for it and still shown. */}
              {multiPass && agentIdx !== constructionIdx && (
                <span
                  data-testid="steps-agent-pass"
                  title="This step ran more than once — a conditional route or a revision sent the pipeline back to it"
                  className="text-[9px] text-brand bg-brand-violet-tint border border-brand-border px-1.5 py-0.5 rounded"
                >
                  pass {agent.passCount}
                </span>
              )}
              <span className="flex-1" />
              {rowMeta && <span className="text-[11.5px] text-ink-300 font-mono">{rowMeta}</span>}
              {navigable && <ChevronRight className="h-4 w-4 flex-none text-line-faint" />}
            </button>

            {/* wave_skipped — the wave ran with zero tasks; explicit attention card,
                never folded silently into the "done" check above. */}
            {isWaveSkipped && <WaveSkippedCard reason={agent.waveSkipped!.reason} />}

            {/* wave_repair — dropped tasks the engine caught and re-dispatched. */}
            {agent.waveRepair && <WaveRepairRow count={agent.waveRepair.count} />}

            {/* gate — AWAITING you (reused InlineGateActions, same submit channel) */}
            {gateAwaiting && (
              <GateAwaitingCard
                laneGate={laneGate!}
                isRunning={isRunning}
                reviewsPriorStepName={reviewsPriorStepName}
                onApprove={onApproveGate!}
                onReject={onRejectGate}
                onRedo={onRedoGate}
                onUpdateSpecs={onUpdateSpecsGate}
              />
            )}

            {/* gate — approved by you (settled strips, from live gate events) */}
            {approvedGates.map((g) => (
              <GateApprovedStrip key={g.id} gate={g.gate || "approved"} />
            ))}

            {/* KAN-123: security gate blocked inline card — shows after a failed
                agent whose error string indicates a security/exec/hook block.
                Generic detection (SC-001 — no agent-id literal). */}
            {isErr && isSecurityBlock(agent.error) && (
              <SecurityGateBlockedCard error={agent.error ?? ""} />
            )}
          </div>
        );
      })}

      {/* "Diverted to {X} →" — this run is the divert SOURCE, so it closes the
          spine, after its own agent rows (see the "Continued from" comment
          above for the ordering rationale). */}
      {divertLink?.direction === "source" && <DivertLinkRow link={divertLink} />}

      {/* Fallback: an active gate that maps to no visible agent row still shows. */}
      {showGateFallback && (
        <GateAwaitingCard
          laneGate={laneGate!}
          isRunning={isRunning}
          reviewsPriorStepName={reviewsPriorStepName}
          onApprove={onApproveGate!}
          onReject={onRejectGate}
          onRedo={onRedoGate}
          onUpdateSpecs={onUpdateSpecsGate}
        />
      )}

      {/* Pipeline halted banner (failed) — ND-D live count, never the mock's fixed text */}
      {failed && notRun > 0 && (
        <div className="flex items-center gap-2.5 mt-2 px-3.5 py-3 rounded-[12px] bg-status-failed-fill border border-status-failed-border">
          <RotateCw className="h-4 w-4 flex-none text-status-failed" />
          <span className="text-[12.5px] font-semibold leading-[1.3] text-status-failed-strong font-[Manrope]">
            Pipeline halted — {notRun} agent{notRun !== 1 ? "s" : ""} did not run.
            {failedAgent ? ` Reopen to resume from ${failedAgent.name}.` : " Reopen to resume the run."}
          </span>
        </div>
      )}
    </div>
  );
}
