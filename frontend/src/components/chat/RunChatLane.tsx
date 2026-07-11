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
import type { ReactNode } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Check,
  Code2,
  FileText,
  HelpCircle,
  ImageIcon,
  Mic,
  Minimize2,
  Paperclip,
  Pause,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Square,
  X,
} from "lucide-react";

import type {
  AgentEvent,
} from "./runtime/blocks.types";
import type { AgentRunState, ChatAttachment, ChatMessage, ClarifyRound, PipelineRunState } from "@/types/index";
import type { ClarifyQuestion } from "../preview/QuestionnairePanel";
import { ChatPanel } from "./ChatPanel";
import { ChatAttachments } from "./ChatAttachments";
import { LaneRunHeader } from "./LaneRunHeader";
import {
  composedContextUsage,
  COMPACT_THRESHOLD_PCT,
  type ComposedContextTelemetry,
} from "./ChatTokenWidget";
import {
  InlineClarifyActions,
  type ClarifyResponse,
} from "./InlineClarifyActions";
import { InlineGateActions } from "./InlineGateActions";
import type { PendingAttachment } from "@/hooks/useChatAttachments";
import { formatDuration } from "@/lib/runStats";
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

/**
 * A held CONSEQUENTIAL Concierge proposal (the 33-03 `concierge_proposal` hold)
 * that the user must CONFIRM before the app executes it (D-05, SC-1). GENERIC —
 * `channel` is a proposal channel ("gate_action" | "revision"), never a
 * workflow-name literal (INV-1, mirroring LaneSuggestion's discipline). The
 * confirm handler POSTs the confirm turn back through the existing chat send
 * seam (`{ concierge: true, confirm_proposal: { channel, params } }`); reject
 * simply dismisses without executing anything.
 */
export interface LaneProposal {
  /** Stable proposal id (the 33-03 concierge-proposal event id). */
  id: string;
  /** The Phase-29 disposal channel the confirm turn replays. Generic. */
  channel: string;
  /** The ProposalIntent params carried verbatim to the confirm turn. */
  params: Record<string, unknown>;
  /** Human-readable description of the consequential action (rendered escaped). */
  summary?: string;
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
  /**
   * Live run telemetry — drives the compact token widget (plan 06 / P26) and,
   * when the stream supplies it, the composed-context usage that surfaces the
   * compact affordance (D-08). Accepts the optional composed-context extension.
   */
  pipelineState?: PipelineRunState & Partial<ComposedContextTelemetry>;
  /** Agent event stream per assistant turn id (plan 01/02 block rendering). */
  eventsByMessageId?: Record<string, AgentEvent[]>;
  /** The nonce'd deep-link seam a narrator card fires (plan 03, borrow #6). */
  onRequestOpenTab?: (tab: string) => void;

  // ── Lane run header (Phase 39, RUNUI-06 — wired live by 39-05) ─────────────
  /** Back-to-history link in the run header — rendered only when supplied. */
  onBackToHistory?: () => void;
  /** The run title (falls back to the caller's brief / first user turn). */
  runTitle?: string;
  /** An explicit run-type label; falls back to the humanized `pipeline_type`. */
  runType?: string;
  /** The settled deliverable filename — renders the "open in preview" card when
   *  supplied (live meta threaded by 39-05; absent = no card, never invented). */
  deliverableFilename?: string;
  /** The settled deliverable revision index (for the "Delivered as v{n}" label). */
  deliverableVersion?: number;

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

  // ── Consequential Concierge proposals (confirm-chip hold, 33-03/D-05) ──────
  /**
   * Held consequential proposals awaiting explicit confirmation. Rendered as a
   * confirm/reject chip pair modeled on the suggestion-chip path. Confirming is
   * the ONLY path that executes the held intent (T-33-04-01).
   */
  proposals?: LaneProposal[];
  /**
   * Confirm a held proposal → the caller POSTs the confirm turn through the
   * existing chat send seam so the app executes the held intent. RunChatLane is
   * presentational; the transport lives with the caller (plan 07), the same way
   * suggestion chips / gate actions are wired.
   */
  onConfirmProposal?: (proposal: LaneProposal) => void;
  /** Reject/dismiss a held proposal — nothing executes. */
  onRejectProposal?: (id: string) => void;

  // ── Compact affordance (D-08, display/trigger only — no FE compression) ────
  /**
   * Signal the backend compaction is available (e.g. composed-context usage is
   * high). When absent, the affordance is derived from the live composed-context
   * usage on `pipelineState`.
   */
  compactAvailable?: boolean;
  /** Trigger backend compaction (the FE only signals — it does NOT compress). */
  onCompact?: () => void;

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

/** Total answered/asked clarifying questions across the retained rounds (live). */
function countClarifications(rounds?: ClarifyRound[]): number {
  if (!rounds || rounds.length === 0) return 0;
  return rounds.reduce((sum, r) => sum + (r.qa?.length ?? 0), 0);
}

/** A generic clickable transcript adornment card (the mock's inline cards). */
function TranscriptCard({
  onOpen,
  className,
  children,
  testid,
}: {
  onOpen?: () => void;
  className?: string;
  children: ReactNode;
  testid?: string;
}) {
  return (
    <div
      data-testid={testid}
      onClick={onOpen}
      className={`ml-[31px] cursor-pointer rounded-[var(--radius-menu)] border transition-colors ${className ?? ""}`}
    >
      {children}
    </div>
  );
}

/** Settled: an inline "N clarifying questions → In Steps" row (live count). */
function ClarifyCountRow({ count, onOpen }: { count: number; onOpen?: () => void }) {
  return (
    <TranscriptCard
      testid="lane-clarify-count"
      onOpen={onOpen}
      className="flex items-center gap-[10px] border-line-border bg-surface-card px-[13px] py-[11px] hover:border-line-faint"
    >
      <HelpCircle className="h-[15px] w-[15px] text-ink-500" strokeWidth={1.6} />
      <span className="flex-1 font-sans text-[12.5px] font-semibold text-ink-900">
        {count} clarifying {count === 1 ? "question" : "questions"}
      </span>
      <span className="font-sans text-[11px] font-medium text-brand">In Steps →</span>
    </TranscriptCard>
  );
}

/** Settled/building: the "Pipeline · N agents" mini with per-agent rows (live). */
function PipelineMini({
  agents,
  onOpen,
  building,
  completedCount,
}: {
  agents: AgentRunState[];
  onOpen?: () => void;
  building?: boolean;
  completedCount?: number;
}) {
  return (
    <TranscriptCard
      testid="lane-pipeline-mini"
      onOpen={onOpen}
      className="border-line-border bg-surface-card px-[14px] py-3 hover:border-line-faint"
    >
      <div className="mb-[10px] flex items-center justify-between">
        <span className="font-sans text-[10.5px] font-semibold uppercase tracking-[0.11em] text-ink-300">
          Pipeline · {agents.length} agents
        </span>
        {building ? (
          <span className="inline-flex items-center gap-1.5 font-sans text-[11px] font-medium text-brand">
            <span className="h-[6px] w-[6px] animate-pulse rounded-full bg-brand" />
            {completedCount ?? 0} / {agents.length}
          </span>
        ) : (
          <span className="font-sans text-[11px] font-medium text-brand">Open Steps →</span>
        )}
      </div>
      {agents.map((a) => {
        const done = a.status === "done";
        const running = a.status === "running" || a.status === "thinking";
        const errored = a.status === "error";
        return (
          <div key={a.id} className="flex items-center gap-[10px] py-[5px]">
            <span
              className={`grid h-5 w-5 flex-none place-items-center rounded-full ${
                done
                  ? "bg-surface-near-black"
                  : errored
                    ? "bg-status-failed"
                    : running
                      ? "border border-brand bg-brand-fill"
                      : "border border-line-control bg-surface-white"
              }`}
            >
              {done ? (
                <Check className="h-[11px] w-[11px] text-white" strokeWidth={2.4} />
              ) : running ? (
                <span className="h-[6px] w-[6px] animate-pulse rounded-full bg-brand" />
              ) : null}
            </span>
            <span
              className={`flex-1 font-sans text-[12.5px] font-medium ${
                running ? "text-ink-900" : "text-ink-800"
              }`}
            >
              {a.name}
            </span>
            <span className="font-serif text-[11px] tabular-nums text-ink-200">
              {formatDuration(a.duration)}
            </span>
          </div>
        );
      })}
      {building && (
        <p className="mt-[9px] font-sans text-[11px] font-medium text-brand">
          Open Steps for the full live trace →
        </p>
      )}
    </TranscriptCard>
  );
}

/** Live: an "Awaiting you" status card (clarify / gate) — status only; the full
 *  clarify/gate UI lives in the composer body + Steps (Phase 39, RUNUI-08). */
function AwaitingCard({
  icon,
  title,
  body,
  cta,
  onOpen,
  testid,
}: {
  icon: ReactNode;
  title: string;
  body: string;
  cta: string;
  onOpen?: () => void;
  testid: string;
}) {
  return (
    <TranscriptCard
      testid={testid}
      onOpen={onOpen}
      className="border-line-border bg-surface-card px-[14px] py-[13px] hover:border-line-faint"
    >
      <div className="mb-1.5 flex items-center gap-2">
        {icon}
        <span className="flex-1 font-sans text-[12.5px] font-semibold text-ink-900">
          {title}
        </span>
        <span className="rounded-[var(--radius-tag)] bg-brand-fill px-1.5 py-1 font-sans text-[8px] font-semibold uppercase tracking-[0.05em] text-brand">
          Awaiting you
        </span>
      </div>
      <p className="mb-[9px] font-serif text-[11.5px] leading-[1.5] text-ink-500">{body}</p>
      <span className="inline-flex items-center gap-1.5 font-sans text-[11px] font-semibold text-brand">
        {cta}
        <ArrowRight className="h-[13px] w-[13px]" strokeWidth={2} />
      </span>
    </TranscriptCard>
  );
}

/** Live: a small "N clarifications answered [· task plan approved]" note. */
function AnsweredNote({ count, planApproved }: { count: number; planApproved?: boolean }) {
  return (
    <div className="ml-[31px] flex items-center gap-[9px] font-sans text-[11.5px] font-medium text-ink-500">
      <Check className="h-[14px] w-[14px] text-ink-900" strokeWidth={2} />
      {count} clarifications answered{planApproved ? " · task plan approved" : ""}
    </div>
  );
}

/** Settled: the deliverable card ("Delivered as v{n} · open in preview"). */
function DeliverableCard({
  filename,
  version,
  onOpen,
}: {
  filename: string;
  version?: number;
  onOpen?: () => void;
}) {
  return (
    <TranscriptCard
      testid="lane-deliverable"
      onOpen={onOpen}
      className="flex items-center gap-[11px] border-brand-border bg-brand-fill px-[13px] py-[11px] hover:bg-brand-border/40"
    >
      <span className="grid h-8 w-8 flex-none place-items-center rounded-[var(--radius-node)] bg-brand">
        <Code2 className="h-4 w-4 text-white" strokeWidth={1.7} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate font-sans text-[12.5px] font-semibold text-ink-900">
          {filename}
        </span>
        <span className="mt-0.5 block font-serif text-[11px] text-ink-600">
          {version ? `Delivered as v${version} · ` : ""}open in preview →
        </span>
      </span>
    </TranscriptCard>
  );
}

/** Format a byte count as the mock's compact chip size ("1.2KB" / "340KB"). */
function formatChipSize(bytes?: number): string {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1_048_576) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / 1_048_576).toFixed(1)}MB`;
}

/** True when an attachment is audio — by mime or by a common audio extension
 *  (ChatAttachment.kind is only image|file, so audio is detected here). */
function isAudioAttachment(f: ChatAttachment): boolean {
  return (
    (f.mimeType?.startsWith("audio/") ?? false) ||
    /\.(m4a|mp3|wav|ogg|aac|flac|opus)$/i.test(f.name)
  );
}

/** The run's input attachments as the mock's white chips above the composer
 *  (Phase 39). Derived live from the transcript turns' attachments (SC-001);
 *  each chip carries a hover-red "×" for functional in-view removal. */
function RunAttachmentChips({ attachments }: { attachments: ChatAttachment[] }) {
  // Local in-view removal (the mock's per-chip "×") — keyed by kind:name.
  const [removed, setRemoved] = useState<Set<string>>(new Set());
  const shown = attachments.filter((f) => !removed.has(`${f.kind}:${f.name}`));
  if (shown.length === 0) return null;
  return (
    <div data-testid="lane-run-attachments" className="mb-2 flex flex-wrap gap-1.5">
      {shown.map((f, i) => {
        const audio = isAudioAttachment(f);
        return (
          <span
            key={`${f.name}-${i}`}
            data-testid="lane-run-attach-chip"
            className="inline-flex items-center gap-[7px] rounded-[var(--radius-node)] border border-line-control bg-surface-white py-[5px] pl-2 pr-[7px]"
          >
            <span className="grid h-[22px] w-[22px] flex-none place-items-center rounded-[var(--radius-tag)] bg-surface-paper text-ink-500">
              {f.kind === "image" ? (
                <ImageIcon className="h-3 w-3" strokeWidth={1.7} />
              ) : audio ? (
                <Mic className="h-3 w-3" strokeWidth={1.7} />
              ) : (
                <FileText className="h-3 w-3" strokeWidth={1.7} />
              )}
            </span>
            <span className="max-w-[10rem] truncate font-sans text-[11.5px] font-medium text-ink-800">
              {f.name}
            </span>
            {f.sizeBytes ? (
              <span className="font-serif text-[10px] tabular-nums text-ink-200">
                {formatChipSize(f.sizeBytes)}
              </span>
            ) : null}
            <button
              type="button"
              data-testid="lane-run-attach-remove"
              aria-label={`Remove ${f.name}`}
              onClick={() =>
                setRemoved((prev) => new Set(prev).add(`${f.kind}:${f.name}`))
              }
              className="grid h-4 w-4 flex-none place-items-center rounded-[4px] text-ink-200 transition-colors hover:bg-status-failed-fill hover:text-status-failed"
            >
              <X className="h-[11px] w-[11px]" strokeWidth={2} />
            </button>
          </span>
        );
      })}
    </div>
  );
}

/** Free-text composer: the mock's white rounded input bar (attach · voice ·
 *  send) + the plan-06 attachment tray as compact chips above (Phase 39). */
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
  const attachOpenRef = useRef<(() => void) | null>(null);

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
        compact
        openRef={attachOpenRef}
        onChange={(a) => {
          pendingRef.current = a;
        }}
      />
      <div className="flex items-center gap-[5px] rounded-[var(--radius-menu)] border border-line-control bg-surface-white py-[7px] pl-[13px] pr-[7px]">
        <textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          rows={1}
          placeholder={placeholder}
          aria-label="Chat message input"
          className="flex-1 resize-none border-none bg-transparent font-serif text-[13px] leading-[1.3] text-ink-900 placeholder-ink-200 focus:outline-none"
        />
        <button
          type="button"
          onClick={() => attachOpenRef.current?.()}
          title="Attach files"
          aria-label="Attach files"
          className="grid h-8 w-8 flex-none place-items-center rounded-[9px] text-ink-500 transition-colors hover:bg-surface-paper hover:text-brand"
        >
          <Paperclip className="h-4 w-4" strokeWidth={1.7} />
        </button>
        <button
          type="button"
          title="Voice · transcribe"
          aria-label="Voice input"
          className="grid h-8 w-8 flex-none place-items-center rounded-[9px] text-ink-500 transition-colors hover:bg-surface-paper hover:text-brand"
        >
          <Mic className="h-4 w-4" strokeWidth={1.7} />
        </button>
        <button
          type="button"
          data-testid="chat-send"
          onClick={handleSend}
          disabled={!value.trim()}
          aria-label="Send message"
          className="grid h-8 w-8 flex-none place-items-center rounded-[9px] bg-brand text-white transition-colors hover:bg-brand-pressed disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ArrowRight className="h-4 w-4" strokeWidth={1.8} />
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
  onBackToHistory,
  runTitle,
  runType,
  deliverableFilename,
  deliverableVersion,
  onStop,
  onRevise,
  onRelaunch,
  suggestions,
  onSuggestion,
  proposals,
  onConfirmProposal,
  onRejectProposal,
  compactAvailable,
  onCompact,
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

  // The compact affordance surfaces when the backend signals compaction is
  // available OR the live composed-context usage crosses the shared threshold
  // (D-08 — FE only DISPLAYS/triggers, it never compresses). Derived from the
  // SAME telemetry the ChatTokenWidget reads (single source of truth).
  const ctxUsage = pipelineState ? composedContextUsage(pipelineState) : null;
  const compactEligible =
    Boolean(onCompact) &&
    (compactAvailable === true ||
      (ctxUsage !== null && ctxUsage.pct >= COMPACT_THRESHOLD_PCT));

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

  // Failed-lane composer send — a change instruction that feeds the reopen /
  // edit-brief flow (the mock's "Tell the agents what to change, then reopen…").
  const handleTerminalRevise = useCallback(
    (text: string, attachments: ChatAttachment[]) => {
      if (onRevise) onRevise(text);
      else sendMessage(text, attachments);
    },
    [onRevise, sendMessage],
  );

  // Consequential Concierge proposals held behind a confirm chip (33-03/D-05).
  // Modeled on the suggestion-chip render path but mode-independent: a held
  // proposal (gate action / revision) can surface in any live state, and the
  // user must CONFIRM before the app executes it (T-33-04-01). GENERIC — no
  // workflow-name literal (INV-1). Proposal text is rendered through React's
  // default JSX escaping (no raw-HTML injection sink) — XSS-safe (T-33-04-02).
  const renderProposals = () => {
    if (!proposals || proposals.length === 0) return null;
    return (
      <div data-testid="chat-proposals" className="space-y-2">
        {proposals.map((p) => (
          <Card
            key={p.id}
            data-proposal-id={p.id}
            className="border border-brand/30 bg-brand/5 px-3.5 py-3 space-y-2"
          >
            <div className="flex items-center gap-1.5">
              <Sparkles className="h-3 w-3 text-brand" />
              <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-brand">
                Confirm to continue
              </p>
            </div>
            {p.summary && (
              <p className="text-[12px] text-ink-700">{p.summary}</p>
            )}
            <div className="flex flex-wrap gap-1.5">
              <button
                type="button"
                data-testid="chat-proposal-confirm"
                data-proposal-id={p.id}
                onClick={() => onConfirmProposal?.(p)}
                className="rounded-[var(--radius-pill)] bg-brand px-3 py-1.5 text-[11px] font-medium text-white transition-colors hover:bg-brand-pressed"
              >
                Confirm
              </button>
              <button
                type="button"
                data-testid="chat-proposal-reject"
                data-proposal-id={p.id}
                onClick={() => onRejectProposal?.(p.id)}
                className="rounded-[var(--radius-pill)] border border-line-control bg-surface-white px-3 py-1.5 text-[11px] font-medium text-ink-500 transition-colors hover:border-ink-300 hover:text-ink-700"
              >
                Dismiss
              </button>
            </div>
          </Card>
        ))}
      </div>
    );
  };

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
        // Mock fidelity (D39-1): the settled composer is JUST the "Ask for a
        // change…" input — the "Suggested next steps" chip block has no mock
        // equivalent and is removed from the run-screen lane. The
        // suggestions/onSuggestion props are retained on the interface until
        // 39-05 retires the DashboardLayout wiring (kept here, unrendered).
        return (
          <FreeTextComposer
            placeholder="Ask for a change or a follow-up…"
            onSend={handleFreeText}
          />
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

        // Failed — the mock's failure-explanation card + "Resume options" (P16).
        // Live data only (ND-D): sanitized server error + real failed-agent
        // names, never the mock's fixed security-gate fiction.
        if (pipelineState?.failed) {
          const names = resolveAgentNames(failedIds, nameById);
          const sanitized = sanitizeError(
            firstAgentError(pipelineState?.agents, failedIds),
          );
          return (
            <div data-testid="chat-terminal-failed" className="space-y-3">
              {/* Failure card — red-tinted, alert header, live bullets. */}
              <div className="overflow-hidden rounded-[13px] border border-status-failed-border bg-status-failed-fill">
                <div className="flex items-center gap-2 border-b border-status-failed-border px-[14px] py-3">
                  <AlertTriangle
                    className="h-[15px] w-[15px] text-status-failed"
                    strokeWidth={1.8}
                  />
                  <span className="flex-1 font-sans text-[12.5px] font-semibold text-status-failed-strong">
                    What went wrong
                  </span>
                </div>
                <div className="px-[14px] py-3 font-serif text-[12px] leading-[1.6] text-ink-700">
                  {names.length > 0 && (
                    <p className="mb-[7px]">
                      • Failed {names.length > 1 ? "agents" : "agent"}:{" "}
                      <span className="font-semibold text-ink-900">
                        {names.join(", ")}
                      </span>
                    </p>
                  )}
                  {sanitized && (
                    <p data-testid="chat-terminal-error">• {sanitized}</p>
                  )}
                  {names.length === 0 && !sanitized && (
                    <p>• The run stopped before completing. Reopen to resume.</p>
                  )}
                </div>
              </div>
              {/* Resume options — primary reopen (red) + secondary edit-brief. */}
              <div className="rounded-[var(--radius-menu)] border border-line-border bg-surface-card px-[14px] py-[13px]">
                <p className="mb-[9px] font-sans text-[11.5px] font-semibold text-ink-900">
                  Resume options
                </p>
                <button
                  type="button"
                  data-testid="chat-relaunch"
                  onClick={() => onRelaunch?.()}
                  className="mb-2 flex w-full items-center justify-center gap-[7px] rounded-[10px] bg-status-failed px-3 py-[11px] font-sans text-[12.5px] font-semibold text-white transition-colors hover:bg-status-failed-strong"
                >
                  <RotateCcw className="h-[14px] w-[14px]" strokeWidth={1.9} />
                  Reopen &amp; fix from the failed step
                </button>
                <button
                  type="button"
                  data-testid="chat-relaunch-secondary"
                  onClick={() => onRelaunch?.()}
                  className="flex w-full items-center justify-center rounded-[10px] border border-line-control bg-surface-white px-3 py-[10px] font-sans text-[12px] font-semibold text-ink-700 transition-colors hover:border-line-faint"
                >
                  Edit brief &amp; run again
                </button>
              </div>
              {/* Composer at the lane foot (mock Run-Failed:82-89) — a change
                  instruction that feeds the reopen / edit-brief flow. */}
              <FreeTextComposer
                placeholder="Tell the agents what to change, then reopen…"
                onSend={handleTerminalRevise}
              />
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
            placeholder="Steer the run — add a note or change a requirement…"
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

  // Deep-link seams the inline transcript cards fire (borrow #6).
  const goSteps = onRequestOpenTab ? () => onRequestOpenTab("thinking") : undefined;
  const goPreview = onRequestOpenTab ? () => onRequestOpenTab("preview") : undefined;

  // The structured-transcript adornments (the mock's inline cards), rendered at
  // the foot of the transcript and driven by the GENERIC runState + live
  // pipelineState (SC-001 / ND-D — never the mock's fixed counts/strings).
  const renderTranscriptFooter = (): ReactNode => {
    const agents = pipelineState?.agents ?? [];

    // Settled — the completed transcript's inline cards.
    if (runState === "complete" || runState === "idle") {
      const clarifyCount = countClarifications(pipelineState?.clarifications);
      // The deliverable is surfaced LIVE from pipelineState (D39-4 — the
      // pipeline_complete event carries the filename/version). The prop remains a
      // 39-05 override. This is the SINGLE deliverable card (INV-12) — the mock's
      // composition; no interim narrator ResultCard stand-in.
      const dFilename = pipelineState?.deliverableFilename ?? deliverableFilename;
      const dVersion = pipelineState?.deliverableVersion ?? deliverableVersion;
      if (clarifyCount === 0 && agents.length === 0 && !dFilename) {
        return null;
      }
      return (
        <div data-testid="lane-adornments" className="flex flex-col gap-4">
          {clarifyCount > 0 && (
            <ClarifyCountRow count={clarifyCount} onOpen={goSteps} />
          )}
          {agents.length > 0 && <PipelineMini agents={agents} onOpen={goSteps} />}
          {dFilename && (
            <DeliverableCard
              filename={dFilename}
              version={dVersion}
              onOpen={goPreview}
            />
          )}
        </div>
      );
    }

    // Live — clarify: status card only (the questions live in the composer + Steps).
    if (runState === "clarify") {
      const n = clarifyQuestions?.length ?? 0;
      return (
        <AwaitingCard
          testid="lane-clarify-status"
          icon={<Pause className="h-[14px] w-[14px] text-brand" strokeWidth={1.9} />}
          title={`Paused — ${n > 0 ? `${n} ${n === 1 ? "question" : "questions"} for you` : "questions for you"}`}
          body="Answer a few clarifications in the Steps panel and the build will start."
          cta="Answer in Steps"
          onOpen={goSteps}
        />
      );
    }

    // Live — gate: status card only (the plan + approve live in the composer + Steps).
    if (runState === "gate") {
      return (
        <div className="flex flex-col gap-4">
          {countClarifications(pipelineState?.clarifications) > 0 && (
            <AnsweredNote count={countClarifications(pipelineState?.clarifications)} />
          )}
          <AwaitingCard
            testid="lane-gate-status"
            icon={<ShieldCheck className="h-[14px] w-[14px] text-brand" strokeWidth={1.7} />}
            title="Paused — task plan needs approval"
            body="Review the task plan and approve it in the Steps panel to start building."
            cta="Review in Steps"
            onOpen={goSteps}
          />
        </div>
      );
    }

    // Live — building: an answered note + the live pipeline mini (k/N, per-agent dots).
    if (runState === "building") {
      const answered = countClarifications(pipelineState?.clarifications);
      if (answered === 0 && agents.length === 0) return null;
      return (
        <div data-testid="lane-adornments" className="flex flex-col gap-4">
          {answered > 0 && <AnsweredNote count={answered} planApproved />}
          {agents.length > 0 && (
            <PipelineMini
              agents={agents}
              onOpen={goSteps}
              building
              completedCount={pipelineState?.completedCount}
            />
          )}
        </div>
      );
    }

    return null;
  };

  // The run-header actions (Stop / Compact) — kept while running (behavior
  // preserved), surfaced in the header's back-link row.
  const headerActions =
    (isRunning && onStop) || compactEligible ? (
      <>
        {compactEligible && (
          <Button
            type="button"
            variant="secondary"
            size="sm"
            data-testid="chat-compact"
            onClick={() => onCompact?.()}
            title="Context is near budget — compact the conversation history"
            className="gap-1.5 text-[10px] text-ink-500"
          >
            <Minimize2 className="h-3 w-3" /> Compact
          </Button>
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
      </>
    ) : null;

  // Title fallback — the run's brief (the first user turn) when no explicit title.
  const firstUserTurn = messages.find((m) => m.role === "user")?.content;

  // The run's input attachments — the mock's chip tray above the composer.
  // Derived live from the transcript turns' attachments, deduped by name+kind
  // (SC-001 / ND-D — never a seeded literal).
  const runAttachments = (() => {
    const seen = new Set<string>();
    const out: ChatAttachment[] = [];
    for (const m of messages) {
      for (const a of m.attachments ?? []) {
        const key = `${a.kind}:${a.name}`;
        if (seen.has(key)) continue;
        seen.add(key);
        out.push(a);
      }
    }
    return out;
  })();

  return (
    <div
      data-testid="run-chat-lane"
      data-run-state={runState}
      className="flex h-full flex-col bg-surface-warm"
    >
      {/* Run header — Back-to-history · type · status · title · meta (Phase 39). */}
      <LaneRunHeader
        runState={runState}
        pipelineState={pipelineState}
        runType={runType}
        runTitle={runTitle ?? firstUserTurn}
        onBackToHistory={onBackToHistory}
        actions={headerActions}
      />

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
          transcriptFooter={renderTranscriptFooter()}
        />
      </div>

      {/* Unified, mode-switched composer (D-12) — absorbs Stop/revise/suggestions. */}
      <div
        data-testid="chat-composer"
        data-composer-mode={runState}
        className="flex-shrink-0 border-t border-line-border bg-surface-warm px-4 py-3 space-y-2.5"
      >
        {/* The run's input attachments — the mock's chip tray above the input. */}
        <RunAttachmentChips attachments={runAttachments} />
        {/* Held consequential proposals surface above the mode body so a
            confirm/reject decision is visible in ANY live state (D-05). */}
        {renderProposals()}
        {renderComposerBody()}
      </div>
    </div>
  );
}
