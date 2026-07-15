"use client";

/**
 * useRunChat — the chat lane's DATA layer (Phase 31, CHATUI-01). A
 * TRANSPORT-AGNOSTIC transcript hook that folds the Phase-29 chat frame
 * vocabulary (`chat_message` / `chat_reply` / `stream_attached`) into a single
 * append-only, family-anchored (D-02) transcript.
 *
 * Design constraints (LIVE-STATE-CONTRACT §0 + POR D-02):
 *   - The transcript ACCUMULATES. It is NEVER swapped per phase/state — a new
 *     run state's frames APPEND, and a `pipeline_complete`/state-change frame
 *     does not wipe a prior turn. A child (revision) run's frames stitch into
 *     the SAME array (family anchoring), keyed on the run/thread ids the server
 *     already scoped (T-31-03-I: no cross-owner fetch here).
 *   - Frames are deduped by `data.event_id` (mirrors the dashboard's
 *     `shouldApplyEvent`), so a durable replay after reconnect is idempotent.
 *   - Optimistic send: `sendMessage` renders the user turn immediately keyed on
 *     a CLIENT-minted `message_id`; the later server `chat_message` echo with the
 *     SAME id reconciles in place (no duplicate bubble). A server echo with a
 *     MISMATCHED id appends as a distinct turn rather than overwriting an
 *     unrelated optimistic bubble (T-31-03-S).
 *
 * Transport-agnostic: it takes a `subscribe(fn)` fan-out (the Phase-29
 * `RunConnectionProvider.subscribe` when the SSE flag is ON) and a
 * `sendCommand(runId, payload)` REST up-channel. When a `legacyWsSend` is
 * provided (flag-OFF), `sendMessage` emits the legacy `user_message` WS frame
 * instead — the SAME transcript either way ("single backend channel", CONTEXT).
 *
 * It does NOT touch `useWorkflow.ts`: the pipeline reducer (and its FIX-039
 * accumulator-reset ordering) is a separate concern; the transcript is its own
 * hook. It also does NOT rewire the live transport (that is plan 31-07) — it
 * exposes a stable contract downstream plans import (interface-first).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { ChatAttachment, ChatMessage, DeepLinkTarget } from "@/types/index";

/** The shared frame envelope — identical in shape to the WS/SSE `{ type, data }`. */
export interface RunChatFrame {
  type: string;
  data: Record<string, unknown>;
}

/** The reconnect-handshake state surfaced from the latest `stream_attached`. */
export interface StreamAttachedState {
  /** Whether the stream is now live (true) or still catching up (false). */
  live: boolean;
  /** The `seq` the server replayed up to (resume cursor hint). */
  replayedThroughSeq?: number;
}

export interface UseRunChatConfig {
  /** The run whose transcript to fold. `null` → an empty, idle transcript. */
  runId: string | null;
  /** Frame fan-out subscription (returns an unsubscribe). Transport-agnostic. */
  subscribe: (fn: (msg: RunChatFrame) => void) => () => void;
  /**
   * REST up-channel (SSE transport): `sendMessage` posts the turn via this
   * (`POST /api/runs/{id}/messages`). Ignored when `legacyWsSend` is provided.
   */
  sendCommand: (
    runId: string | null,
    payload: Record<string, unknown>,
  ) => Promise<void> | void;
  /**
   * Legacy WS up-channel (flag-OFF). When present, `sendMessage` emits a
   * `user_message` frame through this instead of `sendCommand` — same transcript.
   */
  legacyWsSend?: (payload: Record<string, unknown>) => void;
}

/**
 * Optional trailing send flags folded onto the `POST /api/runs/{id}/messages`
 * up-channel payload (43-02, the A.1 CRUX). Field names match the backend
 * `MessageCommand` EXACTLY (`run_commands.py:346/351`):
 *   - `concierge`      — opt this turn into the free-form → Concierge escalation
 *                        (a settled-run ASK answered, not launched as a revision).
 *   - `confirm_proposal` — the confirm round-trip for a previously HELD
 *                        consequential proposal `{ channel, params }` (33-04).
 * GENERIC (SC-001/INV-1): neither field is a workflow-name/agent-id literal.
 * Absent options ⇒ the payload is byte-identical to the pre-43-02 shape
 * (dormant, INV-3) — no `concierge` key is written.
 */
export interface SendMessageOptions {
  concierge?: boolean;
  confirm_proposal?: { channel: string; params: Record<string, unknown> };
}

export interface UseRunChatReturn {
  /** The append-only, family-anchored transcript. */
  messages: ChatMessage[];
  /**
   * Optimistically append a user turn and send it up-channel. Returns the
   * client-minted `message_id` (the reconciliation key for the server echo).
   * The optional trailing `options` fold `concierge` / `confirm_proposal` onto
   * the up-channel payload (43-02); omitting them keeps the payload unchanged.
   */
  sendMessage: (
    text: string,
    attachments?: ChatAttachment[],
    options?: SendMessageOptions,
  ) => string;
  /** The latest `stream_attached` handshake state (null until first attach). */
  streamAttached: StreamAttachedState | null;
}

// ── id minting ────────────────────────────────────────────────────────────────
let _clientSeq = 0;
function mintMessageId(): string {
  const rnd =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `client-${++_clientSeq}-${rnd}`;
}

// ── pure frame → message projections ──────────────────────────────────────────
function parseAttachments(raw: unknown): ChatAttachment[] | undefined {
  if (!Array.isArray(raw)) return undefined;
  const out: ChatAttachment[] = raw.map((a) => {
    const r = (a ?? {}) as Record<string, unknown>;
    return {
      kind: r.kind === "image" ? "image" : "file",
      name: typeof r.name === "string" ? r.name : "",
      mimeType: typeof r.mimeType === "string" ? r.mimeType : undefined,
      sizeBytes: typeof r.sizeBytes === "number" ? r.sizeBytes : undefined,
      // Payload-transient default (ND-10): retained only when the server says so.
      retained: r.retained === true,
    };
  });
  return out;
}

function parseDeepLink(raw: unknown): DeepLinkTarget | undefined {
  if (raw == null || typeof raw !== "object") return undefined;
  const r = raw as Record<string, unknown>;
  // The frame's deep_link is `{ target, nonce }` (mock driver contract); map
  // `target` → the generic `tab` id. `nonce` coerces to a number (0 if absent).
  const tab = typeof r.target === "string" ? r.target : typeof r.tab === "string" ? r.tab : "";
  if (!tab) return undefined;
  const nonceNum = Number(r.nonce);
  return { tab, nonce: Number.isFinite(nonceNum) ? nonceNum : 0 };
}

const CARD_KINDS = new Set([
  "clarify",
  "gate",
  "pipeline",
  "deliverable",
  "spec_revision",
]);
function parseCardKind(raw: unknown): ChatMessage["cardKind"] | undefined {
  return typeof raw === "string" && CARD_KINDS.has(raw)
    ? (raw as ChatMessage["cardKind"])
    : undefined;
}

/**
 * Fold a `chat_message` echo into the transcript. Reconciles STRICTLY by
 * `message_id`: an existing turn (optimistic or already-echoed) with the same id
 * is merged in place (single bubble); a new id appends (T-31-03-S).
 */
function upsertUserMessage(
  prev: ChatMessage[],
  data: Record<string, unknown>,
): ChatMessage[] {
  const id =
    typeof data.message_id === "string" && data.message_id
      ? data.message_id
      : mintMessageId();
  const runId = typeof data.run_id === "string" ? data.run_id : undefined;
  const threadId = typeof data.thread_id === "string" ? data.thread_id : undefined;
  const attachments = parseAttachments(data.attachments);
  const idx = prev.findIndex((m) => m.id === id);
  if (idx >= 0) {
    const existing = prev[idx];
    const merged: ChatMessage = {
      ...existing,
      // The server echo is authoritative for content/anchoring once it lands.
      content: typeof data.text === "string" ? data.text : existing.content,
      attachments: attachments ?? existing.attachments,
      runId: runId ?? existing.runId,
      threadId: threadId ?? existing.threadId,
      chatSessionId: threadId ?? runId ?? existing.chatSessionId,
    };
    const next = prev.slice();
    next[idx] = merged;
    return next;
  }
  const msg: ChatMessage = {
    id,
    chatSessionId: threadId ?? runId ?? "",
    role: "user",
    content: typeof data.text === "string" ? data.text : "",
    createdAt: new Date().toISOString(),
    attachments,
    runId,
    threadId,
  };
  return [...prev, msg];
}

/**
 * Fold a `chat_reply` narrator card into the transcript (idempotent by
 * `message_id`). Carries the generic `cardKind` + `deepLink` descriptor.
 */
function upsertNarratorMessage(
  prev: ChatMessage[],
  data: Record<string, unknown>,
): ChatMessage[] {
  const id =
    typeof data.message_id === "string" && data.message_id
      ? data.message_id
      : mintMessageId();
  const runId = typeof data.run_id === "string" ? data.run_id : undefined;
  const threadId = typeof data.thread_id === "string" ? data.thread_id : undefined;
  const msg: ChatMessage = {
    id,
    chatSessionId: threadId ?? runId ?? "",
    role: "assistant",
    content: typeof data.text === "string" ? data.text : "",
    createdAt: new Date().toISOString(),
    cardKind: parseCardKind(data.card_kind),
    deepLink: parseDeepLink(data.deep_link),
    runId,
    threadId,
  };
  const idx = prev.findIndex((m) => m.id === id);
  if (idx >= 0) {
    const next = prev.slice();
    next[idx] = { ...prev[idx], ...msg };
    return next;
  }
  return [...prev, msg];
}

export function useRunChat(config: UseRunChatConfig): UseRunChatReturn {
  const { runId, subscribe, sendCommand, legacyWsSend } = config;

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streamAttached, setStreamAttached] = useState<StreamAttachedState | null>(
    null,
  );

  // Per-hook dedup of frames by event_id (mirrors the dashboard seen-set).
  const seenRef = useRef<Set<string>>(new Set());

  const handleFrame = useCallback((frame: RunChatFrame) => {
    const data = (frame?.data ?? {}) as Record<string, unknown>;
    const eventId = typeof data.event_id === "string" ? data.event_id : undefined;
    if (eventId) {
      if (seenRef.current.has(eventId)) return; // replayed/duplicate — drop
      seenRef.current.add(eventId);
    }
    switch (frame.type) {
      case "chat_message":
        setMessages((prev) => upsertUserMessage(prev, data));
        break;
      case "chat_reply":
        setMessages((prev) => upsertNarratorMessage(prev, data));
        break;
      case "stream_attached":
        setStreamAttached({
          live: data.live === true,
          replayedThroughSeq:
            typeof data.replayed_through_seq === "number"
              ? data.replayed_through_seq
              : undefined,
        });
        break;
      default:
        // Every other frame (pipeline_complete, agent_*, …) leaves the
        // transcript untouched — it ACCUMULATES, never wipes (§0 rule).
        break;
    }
  }, []);

  useEffect(() => subscribe(handleFrame), [subscribe, handleFrame]);

  const sendMessage = useCallback(
    (
      text: string,
      attachments?: ChatAttachment[],
      options?: SendMessageOptions,
    ): string => {
      const messageId = mintMessageId();
      const optimistic: ChatMessage = {
        id: messageId,
        chatSessionId: runId ?? "",
        role: "user",
        content: text,
        createdAt: new Date().toISOString(),
        attachments,
        runId: runId ?? undefined,
      };
      // Optimistic render (guarded so a re-invoke cannot double-append).
      setMessages((prev) =>
        prev.some((m) => m.id === messageId) ? prev : [...prev, optimistic],
      );
      const payload: Record<string, unknown> = {
        text,
        attachments: attachments ?? [],
        message_id: messageId,
      };
      // 43-02 (A.1 CRUX): fold the Concierge send flags onto the payload ONLY
      // when supplied — field names match the backend MessageCommand exactly
      // (`concierge` / `confirm_proposal`). With no options the payload is
      // byte-identical to the pre-43-02 shape (dormant, INV-3).
      if (options?.concierge) payload.concierge = true;
      if (options?.confirm_proposal) {
        payload.confirm_proposal = options.confirm_proposal;
      }
      if (legacyWsSend) {
        // Flag-OFF legacy WS up-channel (LOCK-B): same transcript. The concierge
        // fields ride the payload but the WS transport does not deliver them to
        // the Concierge until the Part-C SSE cutover — expected (43-02 proves
        // the payload shape + the routing decision, not a live round-trip).
        legacyWsSend({ type: "user_message", ...payload });
      } else {
        void sendCommand(runId, payload);
      }
      return messageId;
    },
    [runId, sendCommand, legacyWsSend],
  );

  return { messages, sendMessage, streamAttached };
}
