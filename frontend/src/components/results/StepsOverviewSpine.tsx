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

import { Check, ChevronRight, XCircle, ListChecks, RotateCw, ShieldAlert } from "lucide-react";
import type { AgentRunState, ClarifyRound, PipelineRunState } from "@/types/index";
import type { GateEventRow } from "@/lib/api";
import { InlineGateActions } from "@/components/chat/InlineGateActions";
import { InlineClarifyActions } from "@/components/chat/InlineClarifyActions";
import type { GateContext } from "@/components/chat/RunChatLane";
import type { ClarifyQuestion } from "@/types/index";
import type { ClarifyResponse } from "@/components/chat/InlineClarifyActions";
import { ClarificationsCard } from "./ClarificationsCard";
import { formatDuration, formatTokenCount } from "@/lib/runStats";

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
}

// The "Awaiting you" card chrome from the mock (brand-tinted, focus-ring shadow).
function AwaitingCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-3 ml-2 rounded-[12px] border border-line-border bg-[#FCFAF3] overflow-hidden shadow-[0_0_0_3px_rgba(60,44,218,0.06)]">
      {children}
    </div>
  );
}

// The inline "Awaiting you" review-gate card — the REUSED generic InlineGateActions
// (same approve_review submit channel + KAN-100 terminal fence, INV-12) under the
// mock's gate-card chrome. Rendered inline after the paused agent's row when the
// gate maps to a visible agent, else as a fallback at the foot of the spine so an
// active gate is NEVER lost (correctness — the gate must stay reachable).
function GateAwaitingCard({
  laneGate, isRunning, onApprove, onReject, onRedo, onUpdateSpecs,
}: {
  laneGate: GateContext;
  isRunning: boolean;
  onApprove: (gateKey: string, editedContent?: string) => void;
  onReject?: (gateKey: string) => void;
  onRedo?: (gateKey: string, instructions: string) => void;
  onUpdateSpecs?: (gateKey: string, report: string) => void;
}) {
  return (
    <AwaitingCard>
      <div className="flex items-center gap-2.5 px-3.5 py-3 border-b border-line-faint-row">
        <div className="w-[26px] h-[26px] flex-none rounded-[7px] bg-brand grid place-items-center">
          <ListChecks className="h-3.5 w-3.5 text-white" />
        </div>
        <p className="flex-1 m-0 text-[12.5px] font-semibold text-ink-900 font-[Manrope]">Review gate — {laneGate.agentName}</p>
        <span className="text-[8.5px] font-semibold uppercase tracking-wider text-brand bg-brand-fill border border-brand-border px-1.5 py-1 rounded">Awaiting you</span>
      </div>
      <div className="px-3.5 py-3">
        <InlineGateActions
          agentId={laneGate.agentId}
          agentName={laneGate.agentName}
          output={laneGate.output}
          gateKey={laneGate.gateKey}
          redoable={laneGate.redoable}
          updateSpecsEligible={laneGate.updateSpecsEligible}
          artifactKind={laneGate.artifactKind}
          isPipelineRunning={isRunning}
          approveLabel={laneGate.approveLabel}
          onApprove={onApprove}
          onReject={onReject ?? (() => {})}
          onRedo={onRedo}
          onUpdateSpecs={onUpdateSpecs}
        />
      </div>
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

export function StepsOverviewSpine({
  agents, pipelineState, clarifications, clarificationsLoading, onOpenAgent, topSlot, gateEvents,
  laneGate, onApproveGate, onRejectGate, onRedoGate, onUpdateSpecsGate,
  clarifyQuestions, onSubmitClarify, onSkipClarify, onCancelWorkflow,
}: StepsOverviewSpineProps) {
  const total = agents.length;
  const completedCount = agents.filter(a => a.status === "done").length;
  const isRunning = pipelineState?.isRunning ?? false;
  const failed = pipelineState?.failed || agents.some(a => a.status === "error");

  const statusLabel = failed ? "Run failed" : isRunning ? "Running" : "Run complete";

  // Mock's Steps-overview phase PILL + LABEL, keyed on the GENERIC run state
  // (SC-001 — no workflow-name literal): clarify awaiting → CLARIFY; active
  // review gate → REVIEW; otherwise running → BUILDING with live N/M counts
  // (Run - Live.dc.html :981). Failed/complete keep the plain statusLabel.
  const hasClarify = !!(clarifyQuestions && clarifyQuestions.length > 0 && onSubmitClarify);
  const gateActive = !!laneGate && isRunning && !!onApproveGate;
  const phase =
    failed ? null
    : hasClarify ? { pill: "CLARIFY", label: "Waiting on your answers", live: false }
    : gateActive ? { pill: "REVIEW", label: "Paused for your approval", live: false }
    : isRunning ? { pill: "BUILDING", label: `Pipeline running · ${completedCount} / ${total}`, live: true }
    : null;

  const totalDuration = pipelineState?.totalDuration;
  const metaBits = [
    total > 0 ? `${completedCount} / ${total} agents` : null,
    totalDuration ? formatDuration(totalDuration) : null,
  ].filter(Boolean).join(" · ");

  // Not-run (idle) agents after a failure → the halted banner count (ND-D).
  const notRun = failed ? agents.filter(a => a.status === "idle").length : 0;
  const failedAgent = agents.find(a => a.status === "error");

  // An active gate renders inline after its paused agent's row; if it maps to no
  // visible agent, a foot-of-spine fallback keeps it reachable (never lost).
  const gateAgentMatches = !!laneGate && agents.some(a => a.id === laneGate.agentId);
  const showGateFallback = !!laneGate && isRunning && !!onApproveGate && !gateAgentMatches;

  // Approved gate-event rows keyed by the agent (step) they fired on → the settled
  // "Review gate — approved" strips interleaved after each agent's row.
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
        {total > 0 && (
          <div className="flex gap-[3px] h-[5px] rounded-[3px] overflow-hidden">
            {agents.map((a, i) => (
              <div key={i} className={`flex-1 ${
                a.status === "done" ? "bg-brand" :
                a.status === "running" || a.status === "thinking" ? "bg-brand animate-pulse" :
                a.status === "error" ? "bg-status-failed" :
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
          <div className="flex items-center gap-2 px-3.5 py-3 border-b border-line-faint-row">
            <p className="flex-1 m-0 text-[13px] font-semibold text-ink-900 font-[Manrope]">Clarifications</p>
            <span className="text-[8.5px] font-semibold uppercase tracking-wider text-brand bg-brand-fill border border-brand-border px-1.5 py-1 rounded">Awaiting you</span>
          </div>
          <div className="p-3.5">
            <InlineClarifyActions questions={clarifyQuestions} onSubmitAnswers={onSubmitClarify} onCancelWorkflow={onCancelWorkflow} />
          </div>
        </AwaitingCard>
      )}

      {/* compact navigable agent rows + gate strips */}
      {agents.map((agent) => {
        const isDone = agent.status === "done";
        const isRun = agent.status === "running" || agent.status === "thinking";
        const isErr = agent.status === "error";
        const isIdle = agent.status === "idle";
        const navigable = !isIdle;
        const rowMeta = [
          agent.duration != null ? formatDuration(agent.duration) : null,
          agent.totalTokens != null && agent.totalTokens > 0 ? `${formatTokenCount(agent.totalTokens)} tok` : null,
        ].filter(Boolean).join(" · ");

        const gateHere = laneGate?.agentId === agent.id;
        const gateAwaiting = gateHere && isRunning && !!onApproveGate;
        const approvedGates = approvedGatesByAgent[agent.id] ?? [];

        return (
          <div key={agent.id}>
            <button
              data-testid="steps-agent-row"
              onClick={() => navigable && onOpenAgent(agent.id)}
              disabled={!navigable}
              className={`w-full flex items-center gap-2.5 rounded-[11px] border px-3 py-2.5 mb-1.5 text-left transition-colors ${
                isRun ? "bg-[#F4F2FB] border-[#DED9F7]" : "border-transparent"
              } ${
                navigable ? "hover:bg-surface-warm cursor-pointer" : "cursor-default"
              }`}
            >
              {isDone ? (
                <span className="w-[18px] h-[18px] flex-none rounded-full bg-surface-near-black grid place-items-center"><Check className="h-2.5 w-2.5 text-white" /></span>
              ) : isRun ? (
                <span className="w-[18px] h-[18px] flex-none rounded-full bg-brand-fill border-[1.5px] border-brand grid place-items-center shadow-[0_0_0_4px_rgba(60,44,218,0.15)]"><span className="w-1.5 h-1.5 rounded-full bg-brand animate-pulse" /></span>
              ) : isErr ? (
                <span className="w-[18px] h-[18px] flex-none rounded-full bg-status-failed grid place-items-center"><XCircle className="h-2.5 w-2.5 text-white" /></span>
              ) : (
                <span className="w-[18px] h-[18px] flex-none rounded-full border-[1.5px] border-line-faint bg-surface-white" />
              )}
              <span className={`text-[13px] font-medium font-[Manrope] ${isIdle ? "text-ink-300" : "text-ink-900"}`}>{agent.name}</span>
              {isIdle && failed && <span className="text-[9px] text-status-amber bg-status-amber-fill border border-status-amber-border px-1.5 py-0.5 rounded">Not run</span>}
              <span className="flex-1" />
              {rowMeta && <span className="text-[11.5px] text-ink-300 font-mono">{rowMeta}</span>}
              {navigable && <ChevronRight className="h-4 w-4 flex-none text-line-faint" />}
            </button>

            {/* gate — AWAITING you (reused InlineGateActions, same submit channel) */}
            {gateAwaiting && (
              <GateAwaitingCard
                laneGate={laneGate!}
                isRunning={isRunning}
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

      {/* Fallback: an active gate that maps to no visible agent row still shows. */}
      {showGateFallback && (
        <GateAwaitingCard
          laneGate={laneGate!}
          isRunning={isRunning}
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
