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

import { Check, ChevronRight, XCircle, Zap, ListChecks, RotateCw } from "lucide-react";
import type { AgentRunState, ClarifyRound, PipelineRunState } from "@/types/index";
import { InlineGateActions } from "@/components/chat/InlineGateActions";
import { InlineClarifyActions } from "@/components/chat/InlineClarifyActions";
import type { GateContext } from "@/components/chat/RunChatLane";
import type { ClarifyQuestion } from "@/components/preview/QuestionnairePanel";
import type { ClarifyResponse } from "@/components/chat/InlineClarifyActions";
import { ClarificationsCard } from "./ClarificationsCard";
import { formatDuration, formatTokenCount } from "@/lib/runStats";

export interface StepsOverviewSpineProps {
  agents: AgentRunState[];
  pipelineState?: PipelineRunState;
  clarifications?: ClarifyRound[];
  clarificationsLoading?: boolean;
  onOpenAgent: (agentId: string) => void;
  // Reused inline gate / clarify (SC-2, INV-12 — same submit channels)
  laneGate?: GateContext;
  onApproveGate?: (gateKey: string, editedContent?: string) => void;
  onRejectGate?: (gateKey: string) => void;
  onRedoGate?: (gateKey: string, instructions: string) => void;
  onUpdateSpecsGate?: (gateKey: string, report: string) => void;
  clarifyQuestions?: ClarifyQuestion[];
  onSubmitClarify?: (responses: ClarifyResponse[]) => void;
  onSkipClarify?: () => void;
}

// The "Awaiting you" card chrome from the mock (brand-tinted, focus-ring shadow).
function AwaitingCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-3 ml-2 rounded-[12px] border border-line-border bg-[#FCFAF3] overflow-hidden shadow-[0_0_0_3px_rgba(60,44,218,0.06)]">
      {children}
    </div>
  );
}

export function StepsOverviewSpine({
  agents, pipelineState, clarifications, clarificationsLoading, onOpenAgent,
  laneGate, onApproveGate, onRejectGate, onRedoGate, onUpdateSpecsGate,
  clarifyQuestions, onSubmitClarify, onSkipClarify,
}: StepsOverviewSpineProps) {
  const total = agents.length;
  const completedCount = agents.filter(a => a.status === "done").length;
  const isRunning = pipelineState?.isRunning ?? false;
  const failed = pipelineState?.failed || agents.some(a => a.status === "error");

  const statusLabel = failed ? "Run failed" : isRunning ? "Running" : "Run complete";
  const totalDuration = pipelineState?.totalDuration;
  const metaBits = [
    total > 0 ? `${completedCount} / ${total} agents` : null,
    totalDuration ? formatDuration(totalDuration) : null,
  ].filter(Boolean).join(" · ");

  // Not-run (idle) agents after a failure → the halted banner count (ND-D).
  const notRun = failed ? agents.filter(a => a.status === "idle").length : 0;
  const failedAgent = agents.find(a => a.status === "error");

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
          <span className="text-[15px] font-semibold text-ink-900 font-[Manrope]">{statusLabel}</span>
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
            <InlineClarifyActions questions={clarifyQuestions} onSubmitAnswers={onSubmitClarify} onSkipAll={onSkipClarify} />
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
        const gateApproved = gateHere && !isRunning && !!laneGate;

        return (
          <div key={agent.id}>
            <button
              data-testid="steps-agent-row"
              onClick={() => navigable && onOpenAgent(agent.id)}
              disabled={!navigable}
              className={`w-full flex items-center gap-2.5 rounded-[11px] px-3 py-2.5 mb-1.5 text-left transition-colors ${
                navigable ? "hover:bg-surface-warm cursor-pointer" : "cursor-default"
              }`}
            >
              {isDone ? (
                <span className="w-[18px] h-[18px] flex-none rounded-full bg-surface-near-black grid place-items-center"><Check className="h-2.5 w-2.5 text-white" /></span>
              ) : isRun ? (
                <span className="w-[18px] h-[18px] flex-none rounded-full bg-brand-fill border-[1.5px] border-brand grid place-items-center"><span className="w-1.5 h-1.5 rounded-full bg-brand animate-pulse" /></span>
              ) : isErr ? (
                <span className="w-[18px] h-[18px] flex-none rounded-full bg-status-failed grid place-items-center"><XCircle className="h-2.5 w-2.5 text-white" /></span>
              ) : (
                <span className="w-[18px] h-[18px] flex-none rounded-full border-[1.5px] border-line-faint bg-surface-white" />
              )}
              <span className={`text-[13px] font-medium font-[Manrope] ${isIdle ? "text-ink-300" : "text-ink-900"}`}>{agent.name}</span>
              {isRun && <span className="inline-flex items-center gap-1 text-[8px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-brand-fill text-brand"><Zap className="h-2.5 w-2.5" />Live</span>}
              {isIdle && failed && <span className="text-[9px] text-status-amber bg-status-amber-fill border border-status-amber-border px-1.5 py-0.5 rounded">Not run</span>}
              <span className="flex-1" />
              {rowMeta && <span className="text-[11.5px] text-ink-300 font-mono">{rowMeta}</span>}
              {navigable && <ChevronRight className="h-4 w-4 flex-none text-line-faint" />}
            </button>

            {/* gate — AWAITING you (reused InlineGateActions, same submit channel) */}
            {gateAwaiting && (
              <AwaitingCard>
                <div className="flex items-center gap-2.5 px-3.5 py-3 border-b border-line-faint-row">
                  <div className="w-[26px] h-[26px] flex-none rounded-[7px] bg-brand grid place-items-center">
                    <ListChecks className="h-3.5 w-3.5 text-white" />
                  </div>
                  <p className="flex-1 m-0 text-[12.5px] font-semibold text-ink-900 font-[Manrope]">Review gate — {laneGate!.gateKey}</p>
                  <span className="text-[8.5px] font-semibold uppercase tracking-wider text-brand bg-brand-fill border border-brand-border px-1.5 py-1 rounded">Awaiting you</span>
                </div>
                <div className="px-3.5 py-3">
                  <InlineGateActions
                    agentId={laneGate!.agentId}
                    agentName={laneGate!.agentName}
                    output={laneGate!.output}
                    gateKey={laneGate!.gateKey}
                    redoable={laneGate!.redoable}
                    updateSpecsEligible={laneGate!.updateSpecsEligible}
                    isPipelineRunning={isRunning}
                    approveLabel={laneGate!.approveLabel}
                    onApprove={onApproveGate!}
                    onReject={onRejectGate ?? (() => {})}
                    onRedo={onRedoGate}
                    onUpdateSpecs={onUpdateSpecsGate}
                  />
                </div>
              </AwaitingCard>
            )}

            {/* gate — approved by you (settled strip) */}
            {gateApproved && (
              <div className="flex items-center gap-2.5 mb-3 ml-2 px-3.5 py-2.5 border border-brand-border bg-brand-violet-tint rounded-[11px]">
                <div className="w-[26px] h-[26px] flex-none rounded-[7px] bg-surface-near-black grid place-items-center">
                  <ListChecks className="h-3.5 w-3.5 text-brand-on-dark" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="m-0 text-[12px] font-semibold text-ink-900 font-[Manrope]">Review gate — {laneGate!.gateKey}</p>
                  <p className="mt-0.5 m-0 text-[11px] text-[#8A86B0]">Paused for review · approved by you</p>
                </div>
                <span className="inline-flex items-center gap-1.5 text-[10px] font-semibold text-ink-700 font-[Manrope]"><Check className="h-3 w-3 text-ink-900" />Approved</span>
              </div>
            )}
          </div>
        );
      })}

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
