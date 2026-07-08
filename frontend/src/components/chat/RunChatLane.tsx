"use client";

/**
 * RunChatLane — the run-screen left-column composition root (Phase 31, CHATUI-01).
 *
 * It turns the revived dead kit + the open-design borrow mechanisms + the plan-03
 * data layer into ONE working conversational lane in the CURRENT skin (D-15 —
 * behavior over restyle; Phase 32 owns the reskin). It:
 *   1. renders {@link ChatPanel} for the family-anchored transcript (D-02) with
 *      the `aria-live`/`role=log` streaming region and the plan-01/02 agent-block
 *      rendering;
 *   2. projects narrator `chat_reply` cards (via ChatPanel → MessageBubble →
 *      ResultCard) that deep-link into run tabs through the nonce'd seam (borrow #6);
 *   3. renders a UNIFIED composer that ABSORBS the AgentProgressPanel controls —
 *      a Stop button (while running), the revise-as-chat textarea, and the
 *      "Suggested next steps" chain rendered as quick-reply CHIPS;
 *   4. switches COMPOSER MODE per the D-12 live-state (LIVE-STATE-CONTRACT §1):
 *      clarify → the plan-05 InlineClarifyActions, gate → the plan-05
 *      InlineGateActions, building → steering, complete → revision, terminal →
 *      relaunch. Free-text send goes through `sendMessage` (transport-agnostic,
 *      plan 03); quick-actions go through the SAME typed callbacks (plan 05).
 *
 * SC-001 (the CONTEXT invariant): the composer mode keys off the GENERIC
 * `runState` discriminator — NEVER a workflow/agent name. Every affordance is
 * driven by generic props supplied by the caller (plan 07 threads them live).
 */

import { useCallback, useRef, useState } from "react";
import { Send, Sparkles, Square } from "lucide-react";

import type {
  AgentEvent,
} from "./runtime/blocks.types";
import type { AgentRunState, ChatAttachment, ChatMessage, PipelineRunState } from "@/types/index";
import type { ClarifyQuestion } from "../preview/QuestionnairePanel";
import { ChatPanel } from "./ChatPanel";
import { ChatAttachments } from "./ChatAttachments";
import { ChatTokenWidget } from "./ChatTokenWidget";
import {
  InlineClarifyActions,
  type ClarifyResponse,
} from "./InlineClarifyActions";
import { InlineGateActions } from "./InlineGateActions";
import type { PendingAttachment } from "@/hooks/useChatAttachments";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { Badge } from "../ui/Badge";
import { buildAgentNameById, resolveAgentNames } from "@/lib/parseFailedAgents";

/**
 * The GENERIC live-run state that drives the composer mode (D-12,
 * LIVE-STATE-CONTRACT §1). Never a workflow/agent name (SC-001).
 */
export type RunLaneState =
  | "idle"
  | "building"
  | "clarify"
  | "gate"
  | "complete"
  | "terminal";

/** The active gate the lane surfaces (mirrors the Steps ReviewGatePanel props). */
export interface GateContext {
  agentId: string;
  agentName: string;
  output: string;
  gateKey: string;
  redoable?: boolean;
  /** GENERIC eligibility flag for the KAN-101 spec loop (SC-001). */
  updateSpecsEligible?: boolean;
  approveLabel?: string;
}

/** A generic quick-reply suggestion chip (never a workflow-name literal). */
export interface LaneSuggestion {
  id: string;
  label: string;
  description?: string;
}

export interface RunChatLaneProps {
  /** The family-anchored transcript (plan 03 `useRunChat.messages`). */
  messages: ChatMessage[];
  /** The GENERIC live-run state driving the composer mode (D-12). */
  runState: RunLaneState;
  /** Transport-agnostic send (plan 03 `useRunChat.sendMessage`). */
  sendMessage: (text: string, attachments?: ChatAttachment[]) => void;
  isStreaming?: boolean;
  streamingContent?: string;
  /** Live run telemetry — drives the compact token widget (plan 06 / P26). */
  pipelineState?: PipelineRunState;
  /** Agent event stream per assistant turn id (plan 01/02 block rendering). */
  eventsByMessageId?: Record<string, AgentEvent[]>;
  /** The nonce'd deep-link seam a narrator card fires (plan 03, borrow #6). */
  onRequestOpenTab?: (tab: string) => void;

  // ── Absorbed AgentProgressPanel controls ──────────────────────────────────
  /** Stop the running pipeline (Stop button, visible while running). */
  onStop?: () => void;
  /** Revise-as-chat (the absorbed AgentProgressPanel revise composer). */
  onRevise?: (instruction: string) => void;
  /** Relaunch after a terminal run. */
  onRelaunch?: () => void;
  /** Suggested next steps rendered as quick-reply chips. */
  suggestions?: LaneSuggestion[];
  onSuggestion?: (id: string) => void;

  // ── Plan-05 gate quick-actions ────────────────────────────────────────────
  gate?: GateContext;
  onApprove?: (gateKey: string, editedContent?: string) => void;
  onReject?: (gateKey: string) => void;
  onRedo?: (gateKey: string, instructions: string) => void;
  onUpdateSpecs?: (gateKey: string, report: string) => void;

  // ── Plan-05 clarify quick-actions ─────────────────────────────────────────
  clarifyQuestions?: ClarifyQuestion[];
  onSubmitAnswers?: (responses: ClarifyResponse[]) => void;
  onSkipClarify?: () => void;
}

/**
 * First error string among the failed agents (server-surfaced). Falls back to
 * any agent carrying an error so an older/partial run never renders blank.
 */
function firstAgentError(
  agents: AgentRunState[] | undefined,
  failedIds: string[],
): string | undefined {
  if (!agents) return undefined;
  for (const a of agents) {
    if (failedIds.includes(a.id) && a.error) return a.error;
  }
  for (const a of agents) if (a.error) return a.error;
  return undefined;
}

/**
 * Sanitize a server error to a single human line — the FIRST line only, capped.
 * Never surfaces raw stack frames / internal fields (T-32-06-01, LIVE-STATE-
 * CONTRACT §1: "sanitized error" only).
 */
function sanitizeError(err: string | undefined): string | undefined {
  if (!err) return undefined;
  const firstLine = err.split("\n")[0]?.trim();
  if (!firstLine) return undefined;
  return firstLine.length > 200 ? `${firstLine.slice(0, 197)}…` : firstLine;
}

/** Free-text composer: a textarea + send + the plan-06 attachment tray. */
function FreeTextComposer({
  placeholder,
  onSend,
  hint,
}: {
  placeholder: string;
  onSend: (text: string, attachments: ChatAttachment[]) => void;
  hint?: string;
}) {
  const [value, setValue] = useState("");
  // Remounting ChatAttachments (via key) clears its internal intake after a send.
  const [attachKey, setAttachKey] = useState(0);
  const pendingRef = useRef<PendingAttachment[]>([]);

  const handleSend = useCallback(() => {
    const text = value.trim();
    if (!text) return;
    onSend(text, pendingRef.current);
    setValue("");
    pendingRef.current = [];
    setAttachKey((k) => k + 1);
  }, [value, onSend]);

  return (
    <div className="space-y-2">
      {hint && <p className="text-[10px] text-ink-400">{hint}</p>}
      <ChatAttachments
        key={attachKey}
        onChange={(a) => {
          pendingRef.current = a;
        }}
      />
      <div className="flex items-end gap-2">
        <textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          rows={2}
          placeholder={placeholder}
          aria-label="Chat message input"
          className="flex-1 resize-none rounded-[var(--radius-card)] border border-line-control bg-surface-white px-3 py-2 text-[13px] text-ink-900 placeholder-ink-400 focus:outline-none focus:border-brand/40 leading-relaxed"
        />
        <button
          type="button"
          data-testid="chat-send"
          onClick={handleSend}
          disabled={!value.trim()}
          aria-label="Send message"
          className="flex items-center justify-center rounded-[var(--radius-button)] bg-brand px-3.5 py-2.5 text-white transition-colors hover:bg-brand-pressed disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Send className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

export function RunChatLane({
  messages,
  runState,
  sendMessage,
  isStreaming = false,
  streamingContent = "",
  pipelineState,
  eventsByMessageId,
  onRequestOpenTab,
  onStop,
  onRevise,
  onRelaunch,
  suggestions,
  onSuggestion,
  gate,
  onApprove,
  onReject,
  onRedo,
  onUpdateSpecs,
  clarifyQuestions,
  onSubmitAnswers,
  onSkipClarify,
}: RunChatLaneProps) {
  // isRunning keys off the GENERIC runState only (SC-001) — no workflow branch.
  const isRunning =
    runState === "building" || runState === "clarify" || runState === "gate";

  // Free-text send routes through the transport-agnostic sendMessage; in the
  // complete (revision) mode a free-text turn is a REVISION (onRevise) when the
  // caller supplied that channel, else it falls back to a plain message.
  const handleFreeText = useCallback(
    (text: string, attachments: ChatAttachment[]) => {
      if (runState === "complete" && onRevise) {
        onRevise(text);
        return;
      }
      sendMessage(text, attachments);
    },
    [runState, onRevise, sendMessage],
  );

  const renderComposerBody = () => {
    switch (runState) {
      case "clarify":
        return (
          <InlineClarifyActions
            questions={clarifyQuestions ?? []}
            onSubmitAnswers={onSubmitAnswers ?? (() => {})}
            onSkipAll={onSkipClarify}
          />
        );

      case "gate":
        return gate ? (
          <InlineGateActions
            agentId={gate.agentId}
            agentName={gate.agentName}
            output={gate.output}
            gateKey={gate.gateKey}
            redoable={gate.redoable}
            updateSpecsEligible={gate.updateSpecsEligible}
            approveLabel={gate.approveLabel}
            // In gate mode the pipeline is live; the component fences itself on
            // terminal (KAN-100) — the lane's terminal mode never mounts a gate.
            isPipelineRunning
            onApprove={onApprove ?? (() => {})}
            onReject={onReject ?? (() => {})}
            onRedo={onRedo}
            onUpdateSpecs={onUpdateSpecs}
          />
        ) : null;

      case "complete":
        return (
          <div className="space-y-2.5">
            {suggestions && suggestions.length > 0 && (
              <div className="space-y-1.5">
                <div className="flex items-center gap-1.5">
                  <Sparkles className="h-3 w-3 text-brand" />
                  <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-brand">
                    Suggested next steps
                  </p>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {suggestions.map((s) => (
                    <button
                      key={s.id}
                      type="button"
                      data-testid="chat-suggestion-chip"
                      data-suggestion-id={s.id}
                      onClick={() => onSuggestion?.(s.id)}
                      title={s.description}
                      className="rounded-[var(--radius-pill)] border border-line-control bg-surface-white px-3 py-1.5 text-[11px] font-medium text-brand transition-all hover:border-brand hover:bg-brand hover:text-white"
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <FreeTextComposer
              placeholder="Describe what you'd like to change…"
              hint="Free text sends a revision."
              onSend={handleFreeText}
            />
          </div>
        );

      case "terminal": {
        // Terminal variant keys off the GENERIC pipelineState markers (plan 05)
        // — cancelled / failed / degraded — never a workflow name (SC-001).
        const failedIds = pipelineState?.failedAgents ?? [];
        const degradedIds = pipelineState?.degradedFailedAgents ?? [];
        const nameById = buildAgentNameById(pipelineState?.agents);

        const relaunch = (label: string) => (
          <Button
            type="button"
            variant="secondary"
            data-testid="chat-relaunch"
            onClick={() => onRelaunch?.()}
            className="w-full justify-center"
          >
            {label}
          </Button>
        );

        // Cancelled by you ack + Run again (LIVE-STATE-CONTRACT §1).
        if (pipelineState?.cancelled) {
          return (
            <div data-testid="chat-terminal-cancelled" className="space-y-2.5">
              <Card className="px-3.5 py-3">
                <div className="flex items-center gap-2">
                  <Badge status="cancelled" label="Cancelled" />
                  <p className="text-[12px] font-semibold text-ink-900">
                    Cancelled by you
                  </p>
                </div>
                <p className="mt-1 text-[11px] text-ink-500">
                  The run was stopped. Nothing further will happen.
                </p>
              </Card>
              {relaunch("Run again")}
            </div>
          );
        }

        // "What went wrong" card — agents_failed[] names + sanitized error (P16).
        if (pipelineState?.failed) {
          const names = resolveAgentNames(failedIds, nameById);
          const sanitized = sanitizeError(
            firstAgentError(pipelineState?.agents, failedIds),
          );
          return (
            <div data-testid="chat-terminal-failed" className="space-y-2.5">
              <Card className="px-3.5 py-3">
                <div className="flex items-center gap-2">
                  <Badge status="failed" label="Failed" />
                  <p className="text-[12px] font-semibold text-ink-900">
                    What went wrong
                  </p>
                </div>
                {names.length > 0 && (
                  <p className="mt-1.5 text-[11px] text-ink-600">
                    Failed {names.length > 1 ? "agents" : "agent"}:{" "}
                    <span className="font-medium text-ink-900">
                      {names.join(", ")}
                    </span>
                  </p>
                )}
                {sanitized && (
                  <p
                    data-testid="chat-terminal-error"
                    className="mt-1 text-[11px] text-status-failed"
                  >
                    {sanitized}
                  </p>
                )}
              </Card>
              {relaunch("Edit brief & run again")}
            </div>
          );
        }

        // Degraded — "completed with issues" naming the failed agents (D-12).
        if (pipelineState?.degraded) {
          const names = resolveAgentNames(degradedIds, nameById);
          return (
            <div data-testid="chat-terminal-degraded" className="space-y-2.5">
              <Card className="px-3.5 py-3">
                <div className="flex items-center gap-2">
                  <Badge status="cancelled" label="Issues" />
                  <p className="text-[12px] font-semibold text-ink-900">
                    Completed with issues
                  </p>
                </div>
                {names.length > 0 && (
                  <p className="mt-1.5 text-[11px] text-ink-600">
                    Skipped or failed:{" "}
                    <span className="font-medium text-ink-900">
                      {names.join(", ")}
                    </span>
                  </p>
                )}
              </Card>
              {relaunch("Run again")}
            </div>
          );
        }

        // Plain terminal (no marker) — generic relaunch.
        return relaunch("Start a new run");
      }

      case "building":
        return (
          <FreeTextComposer
            placeholder="Steer the run…"
            hint="Guidance applies at the next step."
            onSend={handleFreeText}
          />
        );

      case "idle":
      default:
        return (
          <FreeTextComposer
            placeholder="Message the run…"
            onSend={handleFreeText}
          />
        );
    }
  };

  return (
    <div
      data-testid="run-chat-lane"
      data-run-state={runState}
      className="flex h-full flex-col bg-white"
    >
      {/* Header — compact token widget + Stop while running. */}
      <div className="flex items-center justify-between gap-2 border-b border-line-divider px-4 py-2.5 flex-shrink-0">
        {pipelineState ? (
          <ChatTokenWidget pipelineState={pipelineState} />
        ) : (
          <span />
        )}
        {isRunning && onStop && (
          <Button
            type="button"
            variant="secondary"
            size="sm"
            data-testid="chat-stop"
            onClick={onStop}
            className="gap-1.5 text-[10px] text-ink-500"
          >
            <Square className="h-3 w-3" /> Stop
          </Button>
        )}
      </div>

      {/* Transcript — ChatPanel owns the aria-live/role=log region + blocks. */}
      <div data-testid="chat-lane-transcript" className="flex-1 min-h-0">
        <ChatPanel
          messages={messages}
          isStreaming={isStreaming}
          streamingContent={streamingContent}
          onSendMessage={(text) => handleFreeText(text, [])}
          onRequestOpenTab={onRequestOpenTab}
          eventsByMessageId={eventsByMessageId}
          hideComposer
        />
      </div>

      {/* Unified, mode-switched composer (D-12) — absorbs Stop/revise/suggestions. */}
      <div
        data-testid="chat-composer"
        data-composer-mode={runState}
        className="flex-shrink-0 border-t border-line-divider px-4 py-3"
      >
        {renderComposerBody()}
      </div>
    </div>
  );
}
