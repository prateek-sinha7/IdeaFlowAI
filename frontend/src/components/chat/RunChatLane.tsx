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
 *      a Stop button (while running), the revise-as-chat textarea, and — on a
 *      COMPLETED run — the chain-suggestion "Chain into" quick-reply CHIPS
 *      rendered ABOVE the input from the `suggestions`/`onSuggestion` props
 *      (c72 — restored above the chat per the user's request, overriding the
 *      Phase-39 mock that had removed them);
 *   4. switches COMPOSER MODE per the D-12 live-state (LIVE-STATE-CONTRACT §1):
 *      clarify/gate → a plain phase-hint FreeTextComposer (Group C — the Steps
 *      panel is the sole answer surface after 42-02; the lane keeps only the
 *      AwaitingCard status card + a hint composer whose free text routes as a
 *      steering note), building → steering, complete → revision, terminal →
 *      relaunch. Free-text send goes through `sendMessage` (transport-agnostic,
 *      plan 03); quick-actions go through the SAME typed callbacks (plan 05).
 *
 * SC-001 (the CONTEXT invariant): the composer mode keys off the GENERIC
 * `runState` discriminator — NEVER a workflow/agent name. Every affordance is
 * driven by generic props supplied by the caller (plan 07 threads them live).
 */

import { useCallback, useEffect, useId, useRef, useState } from "react";
import type { ReactNode } from "react";
import { motion } from "motion/react";
import {
  AlertTriangle,
  ArrowRight,
  Check,
  ChevronDown,
  ChevronRight,
  Code2,
  FileText,
  HelpCircle,
  ImageIcon,
  Mic,
  MicOff,
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
import type { ClarifyQuestion } from "@/types/index";
import { ChatPanel } from "./ChatPanel";
import { ChatAttachments } from "./ChatAttachments";
import { LaneRunHeader } from "./LaneRunHeader";
import {
  composedContextUsage,
  COMPACT_THRESHOLD_PCT,
  type ComposedContextTelemetry,
} from "./ChatTokenWidget";
import type { ClarifyResponse } from "./InlineClarifyActions";
import type { PendingAttachment } from "@/hooks/useChatAttachments";
import type { ReplyStreamingState, SendMessageOptions } from "@/hooks/useRunChat";
import { formatDuration } from "@/lib/runStats";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { Badge } from "../ui/Badge";
import { buildAgentNameById, resolveAgentNames } from "@/lib/parseFailedAgents";
import { useSpeechRecognition } from "@/hooks/useSpeechRecognition";

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
  /**
   * GENERIC artifact kind from _artifact_kind_for (backend) — "spec", "task_list",
   * "summary", "html_file", etc. Passed to discriminateArtifact so agents whose
   * output has no XML wrapper tag (e.g. user_stories domain-analyst produces plain
   * markdown with kind="summary") still render the correct preview renderer.
   * SC-001: never a workflow/agent-name literal — the backend derives this
   * structurally from _AGENT_KIND_MAP (with "summary" as the generic fallback).
   */
  artifactKind?: string;
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
  /**
   * Transport-agnostic send (plan 03 `useRunChat.sendMessage`). The optional
   * trailing `options` carry the 43-02 Concierge flags (`concierge` /
   * `confirm_proposal`) onto the up-channel payload; a settled-run ASK folds
   * `{ concierge: true }` here to route the turn to the Concierge (the A.1 CRUX).
   */
  sendMessage: (
    text: string,
    attachments?: ChatAttachment[],
    options?: SendMessageOptions,
  ) => void;
  /**
   * FIX-119: Optimistically add a user bubble to the transcript WITHOUT posting
   * to the backend. Used in `handleFreeText` on a `complete` run to echo the
   * user's text immediately before the classify-intent LLM round-trip, so the
   * user always sees their message — without triggering the mechanical router's
   * CHANNEL_REVISION side-effect (the double-version bug from FIX-118). Returns
   * the stable `messageId` the caller can pass to `sendMessage` via
   * `options.existingMessageId` to reconcile the bubble instead of duplicating.
   */
  addOptimisticMessage?: (
    text: string,
    attachments?: ChatAttachment[],
  ) => string;
  isStreaming?: boolean;
  streamingContent?: string;
  /**
   * The active streaming-reply hint (quick-260719-rqo, Issue 2 part 2) from
   * `useRunChat.replyStreaming`: non-null while a Concierge reply streams, with a
   * `lastChunkAt` refreshed per chunk. The lane derives a "reading run data…"
   * indicator from a chunk-GAP on this — the mid-reply read-tool freeze. Absent
   * (non-live callers / tests) → the indicator never shows (unchanged behaviour).
   */
  replyStreaming?: ReplyStreamingState | null;
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
  /**
   * KAN-120 BUG-4: inline error message shown when a resume attempt fails
   * (instead of silently navigating away). Cleared by the caller when the
   * run successfully starts (pipeline_start received). Optional/undefined →
   * no error message (normal path, zero regression).
   */
  relaunchError?: string | null;
  /**
   * "Edit brief & run again" — navigates home so the user can modify their
   * brief and start a fresh run. Distinct from `onRelaunch` (resume from
   * checkpoint). When absent the secondary button falls back to `onRelaunch`.
   */
  onEditBrief?: () => void;
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
  /** Cancel the active pipeline from the inline clarify (Phase 42-02 §A2 re-home). */
  onCancelWorkflow?: () => void;
}

/**
 * GENERIC ask-vs-change classifier for a SETTLED-run free-text turn (43-02, the
 * A.1 CRUX / SC-001·INV-1). Keys ONLY on the generic text — NEVER a
 * workflow-name or agent-id literal. A CHANGE REQUEST (an imperative edit) still
 * launches the revision pipeline (onRevise); an ASK (a status/question turn) is
 * answered by the Concierge (`sendMessage(..., { concierge: true })`).
 *
 * Change-intent is weighed FIRST so a question-SHAPED change request
 * ("can you make the button bigger?") routes as a CHANGE, not an ask — a bare
 * question-mark heuristic would misroute it. Ambiguous settled free text falls
 * through to the historical default (a revision); misclassification is bounded —
 * the consequential path stays confirm-gated server-side (T-43-02-ROUTE).
 */
const CHANGE_INTENT =
  /\b(make|change|changed|add|added|remove|removed|delete|deleted|drop|update|fix|fixed|rename|reorder|move|resize|replace|swap|set|turn|redesign|restyle|recolor|tweak|adjust|convert|increase|decrease|reduce|expand|shrink|revise|revamp|modify|edit|improve|refactor|rework|redo|shorten|lengthen|simplify|bigger|smaller|larger|wider|narrower|taller|shorter|darker|lighter|bolder)\b/i;
const ASK_INTENT =
  /(^\s*(what|whats|what's|why|how|is|are|was|were|do|does|did|where|when|who|which|can|could|should|would|will)\b|\bstatus\b|\bexplain\b|\bprogress\b|\?\s*$)/i;
// FIX-104: vague chain intent — the user wants to start a follow-up workflow but
// hasn't named a specific target yet. Fires BEFORE change/ask so it isn't
// swallowed by the revision hold. GENERIC (SC-001/INV-1) — no workflow-name literal.
// Covers: "chain this", "chaining", "chained to", "chain it", "next workflow",
// "build on this", "follow-up", "what can I do next", "continue with", etc.
// Also covers "covert/convert this to X" style phrases that indicate chain intent.
const CHAIN_INTENT =
  /\b(chain(ing|ed|s)?(\s+this|\s+it|\s+into|\s+to|\s+from)?|next\s+workflow|follow.?up|build\s+on|what.?s\s+next|what\s+can\s+i|continue\s+with|extend\s+this|what\s+else|next\s+step|next\s+pipeline|pipeline\s+chain|chained?(\s+workflow)?|i\s+want\s+to\s+chain|convert?\s+this|covert\s+this)\b/i;

// Safety-net window for the settled-run Concierge "reply pending" indicator.
// Comfortably longer than a normal 2–8s reply so it only fires on a genuinely
// failed / never-arriving reply (fire-and-forget send → no chat_reply to clear it).
const REPLY_PENDING_TIMEOUT_MS = 45_000;

// rqo Issue-2 part-2 — the "reading run data…" indicator windows. A Concierge
// reply streams, then FREEZES ~1.3s while it calls a read tool. When the streaming
// reply's text has not grown for READING_GAP_MS and it has not finalized, the FE
// shows the reading indicator (the freeze on this path is always a read-tool call,
// so the wording is accurate without any backend signal). READING_MAX_MS is a
// safety cap: if the stream stalls abnormally long with no terminal, hide the
// indicator rather than let it lie about ongoing activity (mirrors the
// replyPending safety-net philosophy — never a stuck indicator).
const READING_GAP_MS = 700;
const READING_MAX_MS = 15_000;

/**
 * The mid-reply "reading run data…" indicator (rqo Issue-2 part-2). A subtle
 * inline status line in the lane's light aesthetic (indented like AnsweredNote /
 * the transcript bubbles), NOT the dark-themed pre-reply TypingIndicator — the two
 * are distinct states and must not double up (spec guardrail 4). GENERIC (SC-001):
 * a fixed UI string, no workflow-name/agent-id literal.
 */
function ReadingIndicator() {
  return (
    <div
      data-testid="lane-reading-indicator"
      className="ml-[31px] flex items-center gap-[9px] font-sans text-[11.5px] font-medium text-ink-500"
    >
      <span className="flex items-center gap-[3px]">
        {[0, 1, 2].map((i) => (
          <motion.span
            key={i}
            className="h-[5px] w-[5px] rounded-full bg-brand"
            animate={{ opacity: [0.3, 0.9, 0.3] }}
            transition={{
              duration: 1.2,
              repeat: Infinity,
              delay: i * 0.15,
              ease: "easeInOut",
            }}
          />
        ))}
      </span>
      reading run data…
    </div>
  );
}

function classifyFreeText(text: string): "ask" | "change" | "chain" {
  const t = text.trim();
  // FIX-104: chain intent is checked first so "chain this to a prototype" never
  // falls through to the revision hold. Named-target phrases that also contain a
  // transform verb are caught earlier by matchChainTarget; this handles the vague
  // "I want to chain this" case where no target was named.
  if (CHAIN_INTENT.test(t)) return "chain";
  if (CHANGE_INTENT.test(t)) return "change";
  if (ASK_INTENT.test(t)) return "ask";
  return "change";
}

// A settled-run "<transform> into <target>" chain phrase (BUG-1, quick-260720-ec4):
// a generic transform verb FOLLOWED (anywhere later) by a connector (into|to|as).
// No connector ⇒ NOT a chain phrase (a bare "make it bigger" stays a change).
const CHAIN_TRANSFORM =
  /\b(convert|turn|make|transform|change|render|export|generate)\b.*\b(into|to|as)\b/i;
const CHAIN_CONNECTOR = /\b(into|to|as)\b/i;

/**
 * Detect a settled-run "<transform> into <named available chain target>" phrase
 * and return the matched suggestion's id — the SC-001-safe chain seam (BUG-1,
 * quick-260720-ec4). Two-part gate, BOTH required:
 *   1. Transform shape — a generic transform verb FOLLOWED (anywhere later) by a
 *      connector (into|to|as). No connector ⇒ null (a bare "make it bigger" is a
 *      change, not a chain).
 *   2. Named available target — the TAIL after the FIRST connector names one of
 *      the CURRENTLY-AVAILABLE suggestions, matched case-insensitively against the
 *      DATA-DRIVEN suggestions[].label (substring, or any whitespace token of the
 *      label with length >= 4). NEVER a workflow-name literal (SC-001/INV-1).
 * Matching the TAIL (not the whole text) is load-bearing: "convert the
 * presentation-buttons into pills" must NOT spuriously match — only a target
 * NAMED as the transform destination counts. Returns the FIRST matching id, else null.
 */
function matchChainTarget(
  text: string,
  suggestions?: LaneSuggestion[],
): string | null {
  if (!suggestions || suggestions.length === 0) return null;
  const t = text.trim().toLowerCase();
  if (!CHAIN_TRANSFORM.test(t)) return null;
  const connector = CHAIN_CONNECTOR.exec(t);
  if (!connector) return null;
  const tail = t.slice(connector.index + connector[0].length);
  for (const s of suggestions) {
    const label = s.label.trim().toLowerCase();
    if (!label) continue;
    if (tail.includes(label)) return s.id;
    const tokens = label.split(/\s+/).filter((w) => w.length >= 4);
    if (tokens.some((w) => tail.includes(w))) return s.id;
  }
  return null;
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
  return firstLine.length > 200 ? `${firstLine.slice(0, 197)}\u2026` : firstLine;
}

/**
 * KAN-123: Derive structured security failure bullets from live PipelineRunState.
 * Returns [] for non-security failures so the generic agent-name + error path runs.
 * Checks: (1) pipelineState.hookRuns blocked rows → "Secret scan blocked…"
 *          (2) failed-agent exec-denied errors → "Code execution denied…"
 *          (3) validation CRITICAL/HIGH issues → "Validation found N critical…"
 * Generic signal detection only — no agent-id/workflow-name literal (SC-001/INV-1).
 */
function deriveSecurityBullets(state: PipelineRunState | undefined): string[] {
  if (!state) return [];
  const bullets: string[] = [];

  // (1) Secret-scan blocks from live hook_run events (pipelineState.hookRuns).
  const blockedScans = (state.hookRuns ?? []).filter(
    (h) => h.outcome === "block" && /secret|scan/i.test(h.hook ?? "")
  );
  for (const scan of blockedScans) {
    const d = scan.detail as Record<string, unknown> | null;
    const file = typeof d?.file === "string" ? ` to ${d.file}` : "";
    const marker = typeof d?.marker === "string" ? ` containing ${d.marker}` : " containing credentials";
    bullets.push(`Secret scan blocked a write${file}${marker}`);
  }

  // (2) Exec-denied errors from failed agents (any agent status="error" with
  //     an exec-denied signal in its error string).
  const execDenied = (state.agents ?? []).some(
    (a) => a.status === "error" && /exec.*denied|exec.*off/i.test(a.error ?? "")
  );
  if (execDenied) {
    bullets.push("Code execution denied \u2014 exec is off for this workspace");
  }

  // (3) Validation CRITICAL/HIGH issues from any agent's validationIssues.
  let criticalCount = 0;
  for (const a of state.agents ?? []) {
    for (const v of a.validationIssues ?? []) {
      if (v.severity === "CRITICAL" || v.severity === "HIGH") criticalCount++;
    }
  }
  if (criticalCount > 0) {
    bullets.push(
      `Validation found ${criticalCount} critical structural error${criticalCount !== 1 ? "s" : ""} in the partial build`
    );
  }

  return bullets;
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
  pipelineState,
}: {
  agents: AgentRunState[];
  onOpen?: () => void;
  building?: boolean;
  completedCount?: number;
  pipelineState?: import("@/types/index").PipelineRunState;
}) {
  // FIX-182: same constructionComplete guard as AgentThinkingTab/StepsOverviewSpine —
  // prevents premature DONE checkmark on the build agent during task-loop iterations.
  const isRunning = pipelineState?.isRunning ?? building ?? false;
  const constructionIdx = agents.findIndex(a => /build|construct/i.test(a.id));
  const laterAgentStarted = constructionIdx >= 0 &&
    agents.slice(constructionIdx + 1).some(a => a.status !== "idle");
  const completedTaskCount = pipelineState?.protoCompletedTaskCount ?? 0;
  const protoTotalTasks = pipelineState?.protoTotalTasks ?? 0;
  const totalTasks = protoTotalTasks > 0 ? protoTotalTasks : completedTaskCount;
  const allTasksDone = totalTasks > 0 && completedTaskCount >= totalTasks;
  const agentIsReallyDone = (idx: number): boolean => {
    const a = agents[idx];
    if (!a || a.status !== "done") return false;
    if (idx !== constructionIdx) return true;
    return !isRunning || (laterAgentStarted && allTasksDone);
  };
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
      {agents.map((a, agentIdx) => {
        const done = agentIsReallyDone(agentIdx);
        const running = !done && (a.status === "running" || a.status === "thinking");
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

/**
 * Settled run-summary strip (BUG-018 Part B): the completed transcript's
 * adornments (ClarifyCountRow + PipelineMini + DeliverableCard) collapsed
 * BY DEFAULT behind a compact, animated, keyboard-accessible toggle — so the
 * conversation leads and the newest reply reads as the last conversational item,
 * with the generated artifacts one click away.
 *
 * The toggle is a real <button> (aria-expanded/aria-controls + a visible focus
 * ring). The panel stays MOUNTED when collapsed (inert + aria-hidden, height 0)
 * so its deep-linkable cards keep their identity; it animates open via the house
 * motion/react idiom (mirrors ThinkingBlock/ArtifactCard). SC-001: keyed on the
 * generic agent count + deliverable filename — never a workflow name.
 */
function SettledSummaryStrip({
  clarifyCount,
  agents,
  dFilename,
  dVersion,
  goSteps,
  goPreview,
}: {
  clarifyCount: number;
  agents: AgentRunState[];
  dFilename?: string;
  dVersion?: number;
  goSteps?: () => void;
  goPreview?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const metaBits: string[] = [];
  if (agents.length > 0) {
    metaBits.push(`${agents.length} ${agents.length === 1 ? "agent" : "agents"}`);
  }
  if (dFilename) metaBits.push(dFilename);

  return (
    <div className="flex flex-col">
      <button
        type="button"
        data-testid="lane-adornments-toggle"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
        className="group flex w-full items-center gap-2 rounded-[var(--radius-node)] border border-line-border bg-surface-card px-[13px] py-[9px] text-left transition-colors hover:border-line-faint focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-1"
      >
        {open ? (
          <ChevronDown className="h-3.5 w-3.5 flex-none text-ink-500" aria-hidden="true" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 flex-none text-ink-500" aria-hidden="true" />
        )}
        <span className="font-sans text-[12px] font-semibold text-ink-900">
          Run summary
        </span>
        {metaBits.length > 0 && (
          <span className="min-w-0 flex-1 truncate font-serif text-[11px] text-ink-600">
            {metaBits.join(" · ")}
          </span>
        )}
      </button>

      <motion.div
        id={panelId}
        data-testid="lane-adornments"
        role="region"
        aria-hidden={!open}
        inert={!open ? true : undefined}
        initial={false}
        animate={{ height: open ? "auto" : 0, opacity: open ? 1 : 0 }}
        transition={{ duration: 0.22, ease: "easeOut" }}
        className="overflow-hidden"
      >
        <div className="flex flex-col gap-4 pt-3">
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
      </motion.div>
    </div>
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

// c72 — the chat textarea auto-grows with content up to this capped max height
// (~6 rows), then overflow-scrolls. A named const so the JS cap and the Tailwind
// `max-h-[132px]` scroll safety stay in lockstep.
const COMPOSER_MAX_HEIGHT_PX = 132;

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
  // c72 — the textarea element, driven imperatively for the auto-grow (no value
  // effect, so the send-reset stays deterministic + jsdom-testable).
  const taRef = useRef<HTMLTextAreaElement>(null);

  // FIX-192 — wire useSpeechRecognition (already proven in LaunchWizard / IdeaInputPage).
  // preSpeechTextRef snapshots whatever is typed BEFORE the mic is pressed so dictation
  // appends to existing text instead of clobbering it (IdeaInputPage.tsx pattern).
  const preSpeechTextRef = useRef("");
  const { isListening, transcript, startListening, stopListening, isSupported: speechSupported } =
    useSpeechRecognition();

  // Grow the textarea to its content height, clamped to the cap; past the cap it
  // scrolls (max-h + overflow-y-auto). Reset height to "auto" first so the box can
  // SHRINK when text is removed, then measure scrollHeight.
  const autoGrow = useCallback(() => {
    const el = taRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, COMPOSER_MAX_HEIGHT_PX) + "px";
  }, []);

  // Append live transcript to any pre-existing typed text (dual-gated: both
  // isListening and transcript must be truthy to avoid a stale-closure clobber).
  useEffect(() => {
    if (isListening && transcript) {
      setValue(
        preSpeechTextRef.current
          ? `${preSpeechTextRef.current} ${transcript}`
          : transcript,
      );
    }
  }, [transcript, isListening]);

  // Auto-grow when transcript drives setValue (transcript effect sets value through
  // a path that bypasses the onChange handler's inline autoGrow() call, so the box
  // would not resize until the next keystroke without this companion effect).
  useEffect(() => { autoGrow(); }, [value, autoGrow]);

  const handleSend = useCallback(() => {
    const text = value.trim();
    if (!text) return;
    onSend(text, pendingRef.current);
    setValue("");
    pendingRef.current = [];
    setAttachKey((k) => k + 1);
    // c72 — collapse the grown box back to a single row after send.
    if (taRef.current) taRef.current.style.height = "auto";
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
          ref={taRef}
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            autoGrow();
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          rows={1}
          placeholder={placeholder}
          aria-label="Chat message input"
          className="max-h-[132px] flex-1 resize-none overflow-y-auto border-none bg-transparent font-serif text-[13px] leading-[1.3] text-ink-900 placeholder-ink-200 focus:outline-none"
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
          onClick={() => {
            if (isListening) {
              stopListening();
            } else {
              preSpeechTextRef.current = value;
              startListening();
            }
          }}
          disabled={!speechSupported}
          title={
            !speechSupported
              ? "Speech recognition not supported"
              : isListening
              ? "Stop listening"
              : "Voice · transcribe"
          }
          aria-label={isListening ? "Stop listening" : "Voice input"}
          className={`grid h-8 w-8 flex-none place-items-center rounded-[9px] transition-colors ${
            isListening
              ? "animate-pulse text-status-failed"
              : "text-ink-500 hover:bg-surface-paper hover:text-brand"
          }`}
        >
          {isListening ? (
            <MicOff className="h-4 w-4" strokeWidth={1.7} />
          ) : (
            <Mic className="h-4 w-4" strokeWidth={1.7} />
          )}
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
  addOptimisticMessage,
  isStreaming = false,
  streamingContent = "",
  replyStreaming,
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
  relaunchError,
  onEditBrief,
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
  onCancelWorkflow,
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

  // A settled-run CHANGE request held behind the confirm-first refinement chip
  // (44-02, locked decision 5). The *_revision launch (onRevise) fires ONLY when
  // the user confirms the chip; the instruction text is parked here meanwhile.
  // GENERIC (SC-001/INV-1) — just the free text, never a workflow-name literal.
  const [heldRefinement, setHeldRefinement] = useState<string | null>(null);

  // FIX-104: chain picker — opened when the user types a vague chain intent
  // ("chain this", "next step", etc.) without naming a specific target.
  // Renders the available suggestions as inline chips so the user can pick.
  // GENERIC (SC-001/INV-1) — keyed only on suggestions[].id, never a literal.
  const [chainPickerOpen, setChainPickerOpen] = useState(false);

  // A settled-run Concierge ASK is answered by a BLOCKING backend round-trip
  // (POST /messages → concierge.converse, non-streaming) that emits ONE late
  // `chat_reply`. `isStreaming` tracks the PIPELINE stream (false on a settled
  // run), so the lane would otherwise show nothing while the reply is in flight.
  // This lane-local "reply pending" flag drives the SAME TypingIndicator the
  // pipeline path uses (folded into ChatPanel's isStreaming below), giving the
  // ask turn a thinking affordance until its answer renders. Scoped to the ASK
  // branch only — revise/change already have the confirm chip; a live pipeline
  // already streams. `sendMessage` returns the client message id synchronously
  // (its up-channel POST is fire-and-forget), so it is NOT thenable — the flag
  // is CLEARED by the transcript, not a promise: the instant an assistant turn
  // becomes the tail (the `chat_reply` rendered) the ChatPanel gate hides the
  // indicator AND the effect below drops the flag. The error path (no reply ever
  // arrives) is covered by the safety-net timeout further below — so the spinner
  // can never stick on ANY path.
  const [replyPending, setReplyPending] = useState(false);

  // Clear the pending flag once the awaited assistant reply lands as the tail.
  useEffect(() => {
    if (!replyPending) return;
    const last = messages[messages.length - 1];
    if (last && last.role === "assistant") setReplyPending(false);
  }, [messages, replyPending]);

  // Bind the flag to the VIEWED run: RunChatLane does NOT remount per run (no
  // key/runId in the parent — DashboardLayout), so a run switch before the reply
  // lands must not leak a stale spinner onto a different run (the BUG-001/005
  // run-binding class). Reset on the viewed run's identity change — the same
  // pipelineRunId signal the parent uses to detect a genuinely new run.
  const viewedRunId = pipelineState?.pipelineRunId;
  useEffect(() => {
    setReplyPending(false);
  }, [viewedRunId]);

  // Safety net for the ERROR path: sendMessage is fire-and-forget/void, so if the
  // Concierge POST fails / the reply never arrives (Bedrock error, the ~30s
  // AbortController timeout, network), NO `chat_reply` ever renders → the tail
  // stays the user turn and the two effects above never clear the flag → the
  // "generating…" indicator would stick FOREVER (worse than none — it lies about
  // ongoing activity). Drop the flag after a window comfortably longer than a
  // normal 2–8s reply so it fires ONLY on a genuinely failed/never-arriving reply;
  // a normal reply clears `replyPending` first, which unmounts this timer via
  // cleanup before it can trip.
  useEffect(() => {
    if (!replyPending) return;
    const timer = setTimeout(() => setReplyPending(false), REPLY_PENDING_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, [replyPending]);

  // rqo Issue-2 part-2 — the mid-reply "reading run data…" indicator. When a
  // Concierge reply is actively streaming (`replyStreaming` non-null) but its text
  // has not grown for READING_GAP_MS and it has NOT finalized, show the indicator;
  // hide it the instant the next chunk arrives or the reply lands. The gap is an
  // ELAPSED-TIME condition, so a timer (not just a render) drives the (re)check.
  const [isReading, setIsReading] = useState(false);

  // A NEW `replyStreaming` object is minted per chunk (see useRunChat), so this
  // effect re-runs on every chunk AND on finalize/clear. Lint-safe: setState fires
  // ONLY inside timer callbacks (never synchronously in the effect body) — mirrors
  // the useSmoothText pattern. The `hide` 0ms timer drops the indicator on fresh
  // content; `show` re-raises it if the stream stays silent past the gap; `safety`
  // caps a pathological stall so the indicator can never stick.
  useEffect(() => {
    const lastAt = replyStreaming?.lastChunkAt ?? null;
    if (lastAt == null) {
      // Not streaming / finalized → ensure hidden (timer callback, not effect body).
      const hide = setTimeout(() => setIsReading(false), 0);
      return () => clearTimeout(hide);
    }
    const hide = setTimeout(() => setIsReading(false), 0);
    const remaining = Math.max(0, READING_GAP_MS - (Date.now() - lastAt));
    const show = setTimeout(() => setIsReading(true), remaining);
    const safety = setTimeout(() => setIsReading(false), READING_MAX_MS);
    return () => {
      clearTimeout(hide);
      clearTimeout(show);
      clearTimeout(safety);
    };
  }, [replyStreaming]);

  // Belt-and-suspenders: a run switch must not leak a stale reading indicator onto
  // a different viewed run (the run-binding class). `useRunChat` clears
  // `replyStreaming` on an explicit history-open seed; this covers a live viewed-
  // run change while a reply is mid-stream. Lint-safe: the reset fires inside a
  // timer callback, never synchronously in the effect body (set-state-in-effect).
  useEffect(() => {
    const reset = setTimeout(() => setIsReading(false), 0);
    return () => clearTimeout(reset);
  }, [viewedRunId]);

  // Free-text send on a SETTLED run: silently classify intent via LLM
  // (FIX-116), then show the appropriate affordance immediately — no chat reply.
  //   • "revise"  → hold the text as a revision (same confirm-chip as before)
  //   • "chain"   → open the chain picker or direct-chain if target_id matches
  //   • "ask"     → fall through to Concierge for a conversational answer
  // The exact-label matchChainTarget fast-path is kept for named targets (no LLM).
  // All paths are GENERIC (SC-001/INV-1) — keyed only on intent, never a workflow name.
  //
  // UX: the user's text is echoed immediately as a user bubble via sendMessage's
  // chat_message path, then the TypingIndicator fires (replyPending=true) while
  // the classify-intent LLM call is in flight (~1–3s). When the result lands the
  // spinner clears and the revise/chain chip appears. Never a silent 10-second wait.
  const handleFreeText = useCallback(
    (text: string, attachments: ChatAttachment[]) => {
      if (runState === "complete") {
        // Fast path: exact named-target chain (BUG-1 fix — no LLM round-trip needed).
        const chainId = matchChainTarget(text, suggestions);
        if (chainId && onSuggestion) {
          onSuggestion(chainId);
          return;
        }

        // FIX-119: Echo the user's text as an optimistic bubble IMMEDIATELY,
        // before the classify-intent LLM call. On a complete run, calling
        // sendMessage() without { concierge: true } would route through
        // CHANNEL_REVISION (mechanical router) and create a spurious revision run
        // BEFORE the confirm chip appears — the double-version bug (FIX-118).
        // addOptimisticMessage() adds a bubble to local state ONLY with no backend
        // side-effect. The returned messageId is used to reconcile the bubble when
        // the ask path later calls sendMessage with { existingMessageId }.
        const echoMessageId = addOptimisticMessage
          ? addOptimisticMessage(text, attachments)
          : undefined;

        // Show TypingIndicator while classifying intent via LLM (~1–3s).
        setReplyPending(true);

        const runId = viewedRunId ?? "";
        const chainHints = suggestions?.map((s) => ({ id: s.id, label: s.label }));

        if (runId) {
          import("@/lib/api").then(({ classifyIntent, getToken }) => {
            const jwt = getToken() ?? "";
            if (!jwt) {
              setReplyPending(false);
              if (onRevise) setHeldRefinement(text);
              return;
            }
            classifyIntent(jwt, runId, text, chainHints).then((result) => {
              setReplyPending(false);   // ← clears TypingIndicator when result arrives
              if (result.intent === "chain") {
                if (result.target_id && onSuggestion) {
                  onSuggestion(result.target_id);
                } else if (suggestions && suggestions.length > 0 && onSuggestion) {
                  setChainPickerOpen(true);
                } else if (onRevise) {
                  setHeldRefinement(text);
                }
              } else if (result.intent === "ask") {
                // Conversational question → send to Concierge.
                // Reuse the existing optimistic bubble via existingMessageId so
                // sendMessage reconciles it in place instead of adding a duplicate.
                setReplyPending(true);
                sendMessage(text, attachments, {
                  concierge: true,
                  ...(echoMessageId ? { existingMessageId: echoMessageId } : {}),
                  ...(chainHints ? { chain_hints: chainHints } : {}),
                });
              } else {
                // "revise" → show confirm chip (the optimistic bubble is already visible)
                if (onRevise) setHeldRefinement(text);
              }
            }).catch(() => {
              setReplyPending(false);
              if (onRevise) setHeldRefinement(text);
            });
          });
          return;
        }

        // No runId — fall back to revision hold
        setReplyPending(false);
        if (onRevise) setHeldRefinement(text);
        return;
      }
      sendMessage(text, attachments);
    },
    [runState, onRevise, sendMessage, addOptimisticMessage, suggestions, onSuggestion, viewedRunId],
  );

  // Confirm the held refinement → launch the revision (the ONLY path that fires
  // onRevise on a settled run). Dismiss clears the hold and launches nothing.
  // The user's revision text was already echoed as an optimistic bubble in
  // handleFreeText via addOptimisticMessage (FIX-119 pattern) — do NOT call it
  // again here or the same text appears twice (FIX-171 duplicate-bubble fix).
  const confirmRefinement = useCallback(() => {
    if (heldRefinement !== null && onRevise) {
      onRevise(heldRefinement);
    }
    setHeldRefinement(null);
  }, [heldRefinement, onRevise]);

  const dismissRefinement = useCallback(() => setHeldRefinement(null), []);

  // FIX-104: dismiss the chain picker when the run state leaves "complete"
  // (e.g. the user started a new chain pipeline).
  useEffect(() => {
    if (runState !== "complete") setChainPickerOpen(false);
  }, [runState]);

  // Failed-lane composer send — a change instruction that feeds the reopen /
  // edit-brief flow (the mock's "Tell the agents what to change, then reopen…").
  // FIX-168: echo the user's instruction as an optimistic bubble before firing
  // onRevise so the terminal-state revision request also appears in the transcript.
  const handleTerminalRevise = useCallback(
    (text: string, attachments: ChatAttachment[]) => {
      if (addOptimisticMessage) addOptimisticMessage(text);
      if (onRevise) onRevise(text);
      else sendMessage(text, attachments);
    },
    [onRevise, sendMessage, addOptimisticMessage],
  );

  // Consequential Concierge proposals held behind a confirm chip (33-03/D-05).
  // Modeled on the suggestion-chip render path but mode-independent: a held
  // proposal (gate action / revision) can surface in any live state, and the
  // user must CONFIRM before the app executes it (T-33-04-01). GENERIC — no
  // workflow-name literal (INV-1). Proposal text is rendered through React's
  // default JSX escaping (no raw-HTML injection sink) — XSS-safe (T-33-04-02).
  // FIX-115: "chain" proposals confirm via onSuggestion(target_id) — the EXISTING
  // suggestion-chip seam — rather than a server round-trip (no new execution path).
  const renderProposals = () => {
    if (!proposals || proposals.length === 0) return null;
    return (
      <div data-testid="chat-proposals" className="space-y-2">
        {proposals.map((p) => {
          // "chain" proposals execute client-side via the existing suggestion seam.
          const isChain = p.channel === "chain";
          const chainTargetId = isChain ? String(p.params?.target_id ?? "") : "";
          const confirmLabel = isChain ? "Start this workflow" : "Confirm";
          const handleConfirm = isChain
            ? () => { if (chainTargetId && onSuggestion) onSuggestion(chainTargetId); }
            : () => onConfirmProposal?.(p);
          return (
          <Card
            key={p.id}
            data-proposal-id={p.id}
            className="border border-brand/30 bg-brand/5 px-3.5 py-3 space-y-2"
          >
            <div className="flex items-center gap-1.5">
              <Sparkles className="h-3 w-3 text-brand" />
              <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-brand">
                {isChain ? "Start a follow-up workflow?" : "Confirm to continue"}
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
                onClick={handleConfirm}
                className="rounded-[var(--radius-pill)] bg-brand px-3 py-1.5 text-[11px] font-medium text-white transition-colors hover:bg-brand-pressed"
              >
                {confirmLabel}
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
          );
        })}
      </div>
    );
  };

  // The confirm-first refinement chip (44-02, D-05). A settled-run CHANGE is
  // structurally a LOCAL proposal — it reuses the proposal-chip Card+confirm
  // pattern above. Confirm launches the revision (onRevise); Dismiss launches
  // nothing. GENERIC — no workflow-name literal (INV-1); the held instruction is
  // rendered through React's default JSX escaping, no raw-HTML sink (T-44-02-02).
  const renderHeldRefinement = () => {
    if (heldRefinement === null) return null;
    return (
      <Card
        data-testid="chat-refinement-chip"
        className="border border-brand/30 bg-brand/5 px-3.5 py-3 space-y-2"
      >
        <div className="flex items-center gap-1.5">
          <Sparkles className="h-3 w-3 text-brand" />
          <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-brand">
            Run a refinement with this change?
          </p>
        </div>
        <p className="text-[12px] text-ink-700">{heldRefinement}</p>
        <div className="flex flex-wrap gap-1.5">
          <button
            type="button"
            data-testid="chat-refinement-confirm"
            onClick={confirmRefinement}
            className="rounded-[var(--radius-pill)] bg-brand px-3 py-1.5 text-[11px] font-medium text-white transition-colors hover:bg-brand-pressed"
          >
            Run refinement
          </button>
          <button
            type="button"
            data-testid="chat-refinement-dismiss"
            onClick={dismissRefinement}
            className="rounded-[var(--radius-pill)] border border-line-control bg-surface-white px-3 py-1.5 text-[11px] font-medium text-ink-500 transition-colors hover:border-ink-300 hover:text-ink-700"
          >
            Dismiss
          </button>
        </div>
      </Card>
    );
  };

  // c72 — the settled-run chain-suggestion chips, restored ABOVE the chat input.
  // The `suggestions`/`onSuggestion` props already reach the lane (DashboardLayout
  // computes `laneSuggestions` off the static CHAIN_OPTIONS allow-list); Phase 39
  // deleted only the RENDER for mock fidelity. Rendered ONLY on a COMPLETED run
  // with suggestions present; each chip is an actionable <button> in the DS Pill
  // idiom (rounded-[var(--radius-pill)], border-line-control, bg-surface-white)
  // that fires the existing `onSuggestion(id)` chain action. GENERIC (SC-001/INV-1)
  // — the chip label + id come straight off the prop, never a workflow-name literal.
  const renderChainSuggestions = () => {
    if (runState !== "complete" || !suggestions || suggestions.length === 0) {
      return null;
    }
    return (
      <div data-testid="chat-chain-suggestions" className="space-y-1.5">
        <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-brand">
          Chain into
        </p>
        <div className="flex flex-wrap gap-1.5">
          {suggestions.map((s) => (
            <button
              key={s.id}
              type="button"
              data-testid="chat-chain-suggestion-chip"
              data-suggestion-id={s.id}
              onClick={() => onSuggestion?.(s.id)}
              className="inline-flex items-center gap-1 rounded-[var(--radius-pill)] border border-line-control bg-surface-white px-2.5 py-1 font-sans text-[11px] font-medium leading-none text-ink-700 transition-colors hover:border-brand hover:text-brand"
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>
    );
  };

  // FIX-104: inline chain picker — surfaces when the user typed a vague chain
  // intent (CHAIN_INTENT matched, setChainPickerOpen(true)). Renders the same
  // suggestion chips as the static row but inside a branded card with a dismiss
  // action, so the user explicitly picks the next workflow. GENERIC (SC-001/INV-1)
  // — chip ids/labels come from the suggestions prop, never a workflow-name literal.
  const renderChainPicker = () => {
    if (!chainPickerOpen || runState !== "complete" || !suggestions || suggestions.length === 0) {
      return null;
    }
    return (
      <div data-testid="chat-chain-picker" className="rounded-[12px] border border-brand/20 bg-brand/5 px-3.5 py-3 space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-[11px] font-semibold text-brand">
            Which workflow would you like to chain into?
          </p>
          <button
            type="button"
            onClick={() => setChainPickerOpen(false)}
            aria-label="Dismiss chain picker"
            className="text-ink-400 hover:text-ink-700 transition-colors"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {suggestions.map((s) => (
            <button
              key={s.id}
              type="button"
              data-testid="chat-chain-picker-chip"
              data-suggestion-id={s.id}
              onClick={() => { setChainPickerOpen(false); onSuggestion?.(s.id); }}
              className="inline-flex items-center gap-1 rounded-[var(--radius-pill)] border border-brand bg-white px-3 py-1.5 font-sans text-[11.5px] font-semibold text-brand transition-colors hover:bg-brand hover:text-white"
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>
    );
  };

  const renderComposerBody = () => {
    switch (runState) {
      case "clarify":
      case "gate": {
        // Group C (CONTEXT §C) — during clarify/gate the LANE composer is a plain
        // phase-HINT input, NOT a second answer surface. After 42-02 the sole
        // answer surface is the Steps panel (its inline clarify/gate cards); the
        // lane keeps only the AwaitingCard status card (renderTranscriptFooter)
        // plus this hint composer. A free-text turn here is a steering note routed
        // through the SHARED send seam (handleFreeText → sendMessage) — never a
        // new channel and never a second answer form. Keyed on the GENERIC
        // runState (SC-001); the per-state composerHint is the mock's phase cue.
        const composerHint =
          runState === "clarify"
            ? "Answer the questions above to continue…"
            : "Approve the plan above, or add a note…";
        return (
          <FreeTextComposer placeholder={composerHint} onSend={handleFreeText} />
        );
      }

      case "complete":
        // The settled composer is the "Ask for a change…" input. The chain-
        // suggestion chips (the "Chain into" quick-replies) are rendered by
        // `renderChainSuggestions()` in the composer container ABOVE this input
        // (c72 — restored from the `suggestions`/`onSuggestion` props per the
        // user's request, overriding the Phase-39 mock that had removed them).
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
                  The run was stopped. Click Run Again to resume from where it left off.
                </p>
              </Card>
              {/* KAN-120 BUG-4: inline error if the resume attempt failed. */}
              {relaunchError && (
                <div className="flex items-center gap-1.5 rounded-[8px] border border-status-amber-border bg-status-amber-fill px-[10px] py-[8px]">
                  <AlertTriangle className="h-[13px] w-[13px] flex-none text-status-amber" strokeWidth={1.8} />
                  <span className="font-serif text-[11.5px] leading-[1.4] text-status-amber-strong">
                    {relaunchError}
                  </span>
                </div>
              )}
              {relaunch("Run Again")}
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

          // KAN-123: derive structured security failure bullets from live state.
          // Checks pipelineState.hookRuns (blocked secret scans), failed agent
          // errors (exec denied, validation errors) — generic signals, SC-001.
          const securityBullets = deriveSecurityBullets(pipelineState);
          const isSecurityGate = securityBullets.length > 0 ||
            /security.*gate|exec.*denied|secret.*blocked|hook.*block/i.test(sanitized ?? "");

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
                  {/* KAN-123: show structured security bullets when available;
                      fall back to the generic agent-name + error pattern. */}
                  {securityBullets.length > 0 ? (
                    securityBullets.map((bullet, i) => (
                      <p key={i} className={i < securityBullets.length - 1 ? "mb-[7px]" : ""}>
                        • {bullet}
                      </p>
                    ))
                  ) : (
                    <>
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
                    </>
                  )}
                  {/* When security gate stopped the run, mention the Audit tab. */}
                  {isSecurityGate && (
                    <p className="mt-[7px] text-[11px] text-ink-400">
                      See the Audit tab for detector, match, and action details.
                    </p>
                  )}
                </div>
              </div>
              {/* Resume options — primary reopen (red) + secondary edit-brief. */}
              <div className="rounded-[var(--radius-menu)] border border-line-border bg-surface-card px-[14px] py-[13px]">
                <p className="mb-[9px] font-sans text-[11.5px] font-semibold text-ink-900">
                  Resume options
                </p>
                {/* KAN-120 BUG-4: inline error if the resume attempt failed
                    (e.g. timing race — DB not yet committed; or any other error).
                    Shown above the buttons so the user sees it without scrolling.
                    Absent on the normal path (relaunchError is null/undefined). */}
                {relaunchError && (
                  <div className="mb-[9px] flex items-center gap-1.5 rounded-[8px] border border-status-amber-border bg-status-amber-fill px-[10px] py-[8px]">
                    <AlertTriangle className="h-[13px] w-[13px] flex-none text-status-amber" strokeWidth={1.8} />
                    <span className="font-serif text-[11.5px] leading-[1.4] text-status-amber-strong">
                      {relaunchError}
                    </span>
                  </div>
                )}
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
                  onClick={() => (onEditBrief ?? onRelaunch)?.()}
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
      // KAN-128 (FIX-141): prefer the explicit deliverableFilename prop (content-derived,
      // passed by DashboardLayout using deriveDeliverableFilename) over
      // pipelineState?.deliverableFilename (the static manifest name). The ?? order
      // was reversed before this fix — the static state silently won over the prop.
      const dFilename = deliverableFilename ?? pipelineState?.deliverableFilename;
      const dVersion = pipelineState?.deliverableVersion ?? deliverableVersion;
      if (clarifyCount === 0 && agents.length === 0 && !dFilename) {
        return null;
      }
      return (
        <SettledSummaryStrip
          clarifyCount={clarifyCount}
          agents={agents}
          dFilename={dFilename}
          dVersion={dVersion}
          goSteps={goSteps}
          goPreview={goPreview}
        />
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
              pipelineState={pipelineState}
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
          // Fold the lane-local Concierge "reply pending" flag into the streaming
          // signal so the SAME TypingIndicator fires for a settled-run ASK (whose
          // pipeline stream is idle). ChatPanel's gate auto-hides it the instant an
          // assistant turn is the tail — so this cannot show a stuck spinner.
          isStreaming={isStreaming || replyPending}
          streamingContent={streamingContent}
          onSendMessage={(text) => handleFreeText(text, [])}
          onRequestOpenTab={onRequestOpenTab}
          eventsByMessageId={eventsByMessageId}
          hideComposer
          transcriptFooter={
            <>
              {/* rqo Issue-2 part-2 — the mid-reply "reading run data…" indicator
                  sits at the head of the footer, directly under the streaming
                  reply bubble, and scrolls with the transcript (ChatPanel's
                  follow-scroll keeps it in view). It is a SEPARATE, mid-reply state
                  from ChatPanel's pre-reply TypingIndicator (which only fires when
                  the tail is NOT an assistant turn) — so the two never double up. */}
              {isReading && <ReadingIndicator />}
              {renderTranscriptFooter()}
            </>
          }
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
        {/* Confirm-first refinement chip — a held settled-run change gates its
            *_revision launch behind an explicit confirm (44-02, D-05). */}
        {renderHeldRefinement()}
        {/* Chain-suggestion chips — on a COMPLETED run, the chainable next-
            workflows rendered just above the input (c72). */}
        {renderChainSuggestions()}
        {/* FIX-104: inline chain picker — shown when user typed a vague chain intent. */}
        {renderChainPicker()}
        {renderComposerBody()}
      </div>
    </div>
  );
}
