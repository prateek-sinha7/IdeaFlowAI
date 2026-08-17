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

/**
 * The ACTIVE streaming-reply hint (quick-260719-rqo, Issue 2 part 2). Set on
 * every `chat_reply_chunk` (with a refreshed `lastChunkAt`) and cleared on the
 * matching terminal `chat_reply`. The lane derives a "reading run data…"
 * indicator from a chunk-GAP on this: a mid-reply freeze on the Concierge path
 * is always a read-tool call, so an elapsed gap with no terminal means the reply
 * is reading. GENERIC (SC-001) — just an opaque bubble id + a timestamp.
 */
export interface ReplyStreamingState {
  /** The streaming bubble id (`chat-reply:{message_id}`) — matches the terminal. */
  id: string;
  /** Epoch ms of the most recent `chat_reply_chunk` for this reply. */
  lastChunkAt: number;
}

/**
 * A Concierge-held consequential proposal (33-03 / D-05), sourced from the
 * durable `concierge_proposal` run_events row via the existing post-send
 * fetchEvents re-fetch (DEF-44-12-2). Generic — keyed on opaque channel/params
 * strings, never a workflow-name literal (SC-001/INV-1).
 */
export interface HeldProposal {
  /** The durable row's event_id: `concierge-proposal:{message_id}:{channel}`. */
  id: string;
  channel: string;
  params: Record<string, unknown>;
  /** Needed to match the later "resolved" companion row (gate_action/revision only). */
  messageId: string;
  /** The run id the proposal was written to — needed so the confirm turn POSTs
   *  to the correct run even if the UI has since switched to a child/revision run. */
  proposalRunId?: string;
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
   * May return a string (e.g. `revision_run_id` from a confirm-proposal response)
   * that `sendMessage` forwards to `options.onRevisionLaunched` when set.
   */
  sendCommand: (
    runId: string | null,
    payload: Record<string, unknown>,
  ) => Promise<string | null | void> | void;
  /**
   * Legacy WS up-channel (flag-OFF). When present, `sendMessage` emits a
   * `user_message` frame through this instead of `sendCommand` — same transcript.
   */
  legacyWsSend?: (payload: Record<string, unknown>) => void;
  /**
   * DEF-44-12-2 durable re-fetch. When supplied, `sendMessage` awaits the
   * up-channel and THEN fetches events since the last seen `seq` and folds each
   * through `handleFrame`. This delivers the Concierge reply (persisted durable-
   * only, never queued → the live SSE tail never carries it) on BOTH terminal
   * and live opened runs. The per-hook `event_id` dedup makes it idempotent.
   * Absent → behaviour is byte-identical to today (no re-fetch, no crash).
   */
  fetchEvents?: (
    runId: string | null,
    afterSeq: number,
  ) => Promise<RunChatFrame[]>;
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
  /**
   * Optional generic chain-suggestion hints `[{ id, label }]` folded onto a
   * Concierge ask (c72) — the FE-curated next-workflow labels the settled-run
   * lane shows as chips. GENERIC (SC-001/INV-1): plain display labels, never a
   * workflow-name literal. Absent/empty ⇒ NO `chain_hints` key (dormant, INV-3).
   */
  chain_hints?: { id: string; label: string }[];
  /**
   * FIX-119: When set, `sendMessage` will reconcile an ALREADY-ADDED optimistic
   * bubble with this id (from `addOptimisticMessage`) rather than minting a new
   * id. This prevents a duplicate bubble when the user message was shown
   * immediately via `addOptimisticMessage` before the backend call.
   */
  existingMessageId?: string;
  /**
   * FIX-210 (confirm-proposal): When set, overrides the payload's `message_id`
   * with this value. Used by `handleConfirmProposal` to forward the ORIGINAL
   * ASK turn's `message_id` so the backend's `_load_pending_proposal` can
   * locate the durable pending row via `concierge-proposal:{messageId}:{channel}`.
   * Without this, a newly minted id never matches any row → 404 → nothing happens.
   */
  proposalMessageId?: string;
  /**
   * FIX-211: When set, called with the revision_run_id if the confirm-proposal
   * response includes one (a concierge-confirmed revision launched a child run).
   * Lets the caller (handleConfirmProposal) attach + switch the UI to the new run.
   */
  onRevisionLaunched?: (runId: string) => void;
  /**
   * FIX-211b: When set, overrides the run id used for the POST URL. Used when
   * the proposal was written to a run that is no longer the viewed run (e.g.
   * after a revision, the view switches to the child run but the proposal lives
   * on the parent). Without this, the confirm POSTs to the wrong run → 404.
   */
  targetRunId?: string;
  /**
   * FIX-218 (KAN-170): pre-extracted file text entries from chat attachments.
   * Each entry: {name, text, error?, truncated?}. Folded onto the payload as
   * `file_contents` so the backend threads the content to the Concierge prompt
   * and ectx.steering_notes. Absent/empty ⇒ NO `file_contents` key (dormant, INV-3).
   */
  file_contents?: { name: string; text: string; error?: string; truncated?: boolean }[];
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
  /**
   * FIX-119: Add a user bubble to local state ONLY — no backend call, no
   * mechanical-router side-effect. Used when the caller needs to echo the user's
   * text IMMEDIATELY (e.g. before a classify-intent LLM round-trip) without
   * triggering a revision or any other backend routing. The returned `messageId`
   * can later be passed to `sendMessage` via the `messageId` option to reconcile
   * the existing bubble in place instead of creating a duplicate.
   */
  addOptimisticMessage: (
    text: string,
    attachments?: ChatAttachment[],
  ) => string;
  /** The latest `stream_attached` handshake state (null until first attach). */
  streamAttached: StreamAttachedState | null;
  /**
   * The active streaming-reply hint (quick-260719-rqo, Issue 2 part 2): non-null
   * from a reply's first `chat_reply_chunk` until its terminal `chat_reply`, with
   * `lastChunkAt` refreshed on each chunk. The lane reads a chunk-GAP off this to
   * show the "reading run data…" indicator during the mid-reply read-tool freeze.
   */
  replyStreaming: ReplyStreamingState | null;
  /**
   * FIX-172: Fold frames into the transcript WITHOUT resetting — used to recover
   * narrator chat_reply cards that the SSE race drops (pipeline_complete detaches
   * the stream before the narrator card arrives). Idempotent: the per-hook seenRef
   * deduplicates frames already processed, so calling this with already-seen frames
   * is safe. Does NOT clear messages or the seen-set (unlike seedTranscript).
   */
  appendFrames: (frames: RunChatFrame[]) => void;
  /**
   * FIX-176: The last-seen seq from the chat transcript hook — used by FIX-172's
   * appendRunChatFrames caller to fetch only NEWLY-arrived events (after lastSeq)
   * rather than ALL events from seq 0. This prevents duplicate chat_reply cards
   * (e.g. "Revision started") from being re-added by FIX-172 when the seenRef
   * dedup might be racing with seedRunChatTranscript's seenRef.clear().
   */
  getLastSeq: () => number;
  /**
   * DEF-44-12-4 (Piece 3) — IMPERATIVE prior-transcript seed, fired ONLY from
   * the explicit history-open action. Clears the per-hook seen-set + seq cursor,
   * resets `messages` to empty, then folds each frame through `handleFrame` (so
   * `chat_message`/`chat_reply` rows re-populate as turns; non-chat frames are
   * ignored). Because it is imperative and never called on a live revision, the
   * accumulating family-anchored transcript (Test 6) is untouched — the reset is
   * scoped by the deliberate view-change, NOT by a per-run filter on handleFrame.
   */
  seedTranscript: (frames: RunChatFrame[], isTerminalRun?: boolean) => void;
  /**
   * ISS-054 / KAN-160 — Concierge-held consequential proposals (chain, gate_action,
   * revision) sourced from durable concierge_proposal run_events rows via the
   * existing post-send fetchEvents re-fetch. Empty until a Concierge turn creates one.
   */
  proposals: HeldProposal[];
  /**
   * Client-side-only dismiss — removes the chip locally. A hard reload will
   * re-show a pending row (accepted limitation; the row was never designed to be
   * dismissible server-side via reject).
   */
  dismissProposal: (id: string) => void;
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
  // The frame's deep_link is `{ target, nonce }`. `target` is the narrator's
  // milestone/artifact ANCHOR (`run:<id>` / `clarify:<id>` / `deliverable:<file>`
  // / `spec_revision:<id>:<n>` / a `gate_key`) — it is NOT a panel tab id, so it
  // is kept as `anchor`. Aliasing it onto `tab` (pre-FIX-128) made the result
  // card hand PreviewPanel an unknown tab, which that panel's PANEL_TAB_IDS
  // guard silently dropped — so "Open in Steps"/"Open in Preview" never switched
  // the tab. `tab` is now populated ONLY by an explicit `tab` field; otherwise the
  // card kind's generic defaultTab wins. `nonce` coerces to a number (0 if absent
  // or non-numeric — the engine's hex nonce is a card identifier, while the
  // NAVIGATION nonce is minted fresh by useTabDeepLink on click).
  const anchor = typeof r.target === "string" && r.target ? r.target : undefined;
  const tab = typeof r.tab === "string" && r.tab ? r.tab : undefined;
  if (!anchor && !tab) return undefined;
  const nonceNum = Number(r.nonce);
  return {
    ...(tab ? { tab } : {}),
    ...(anchor ? { anchor } : {}),
    nonce: Number.isFinite(nonceNum) ? nonceNum : 0,
  };
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
  // DEF-44-12-2 de-collision: key the assistant bubble on the frame's DISTINCT
  // event_id ("chat-reply:{message_id}") when present, falling back to
  // message_id (then a minted id). This is ALSO the idempotency key handleFrame
  // dedups on — so a Concierge reply (which carries message_id === the user
  // turn's id, run_commands.py:994) appends as its OWN turn instead of matching-
  // and-overwriting the user's question bubble.
  const id =
    typeof data.event_id === "string" && data.event_id
      ? data.event_id
      : typeof data.message_id === "string" && data.message_id
      ? // HARDENING (Issue-3 defense): a reply frame missing its event_id must
        // NEVER key on the bare message_id — the Concierge reply reuses the user
        // turn's id, so a bare-id key overwrites the user's bubble. Mint the same
        // distinct `chat-reply:{message_id}` the backend + durable row use.
        `chat-reply:${data.message_id}`
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

/**
 * Fold a transient `chat_reply_chunk` delta into the streaming assistant bubble
 * (m0o). Mirrors the `agent_chunk` idempotent-accumulation PATTERN
 * (useWorkflow.ts:337) inside the transcript: the bubble is keyed on
 * `chat-reply:{message_id}` — the SAME id the terminal `chat_reply` uses via
 * upsertNarratorMessage (event_id `chat-reply:{message_id}`) — so the terminal
 * MERGES this bubble (content ← authoritative full text) instead of appending a
 * second turn. Chunks carry NO event_id (bypass the top-of-handler dedup) and NO
 * real seq (the cursor is untouched); they are delivered exactly once in the
 * streamed POST body. An empty `message_id` is skipped (never key on an empty id).
 */
function upsertStreamingReply(
  prev: ChatMessage[],
  data: Record<string, unknown>,
): ChatMessage[] {
  const messageId = typeof data.message_id === "string" ? data.message_id : "";
  if (!messageId) return prev; // never key a bubble on an empty id
  const delta = typeof data.delta === "string" ? data.delta : "";
  const id = `chat-reply:${messageId}`;
  const runId = typeof data.run_id === "string" ? data.run_id : undefined;
  const threadId = typeof data.thread_id === "string" ? data.thread_id : undefined;
  const idx = prev.findIndex((m) => m.id === id);
  if (idx >= 0) {
    const next = prev.slice();
    next[idx] = { ...prev[idx], content: prev[idx].content + delta };
    return next;
  }
  const msg: ChatMessage = {
    id,
    chatSessionId: threadId ?? runId ?? "",
    role: "assistant",
    content: delta,
    createdAt: new Date().toISOString(),
    runId,
    threadId,
  };
  return [...prev, msg];
}

export function useRunChat(config: UseRunChatConfig): UseRunChatReturn {
  const { runId, subscribe, sendCommand, legacyWsSend, fetchEvents } = config;

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streamAttached, setStreamAttached] = useState<StreamAttachedState | null>(
    null,
  );
  // ISS-054 / KAN-160: held Concierge proposals (33-03/D-05), sourced from durable
  // concierge_proposal run_events rows via the post-send fetchEvents re-fetch.
  const [proposals, setProposals] = useState<HeldProposal[]>([]);
  // The active streaming reply (rqo Issue-2 part-2): set on each chat_reply_chunk,
  // cleared on the matching terminal chat_reply. Drives the lane's reading hint.
  const [replyStreaming, setReplyStreaming] = useState<ReplyStreamingState | null>(
    null,
  );

  // Per-hook dedup of frames by event_id (mirrors the dashboard seen-set).
  const seenRef = useRef<Set<string>>(new Set());
  // Per-hook max-seen seq cursor (mirrors the page's lastSeqRef) — the offset the
  // DEF-44-12-2 re-fetch-after-send passes as `afterSeq` so it pulls only newer
  // events. Advanced inside handleFrame from a larger numeric `data.seq`.
  const lastSeqRef = useRef<number>(0);

  const handleFrame = useCallback((frame: RunChatFrame) => {
    const data = (frame?.data ?? {}) as Record<string, unknown>;
    const eventId = typeof data.event_id === "string" ? data.event_id : undefined;
    if (eventId) {
      if (seenRef.current.has(eventId)) return; // replayed/duplicate — drop
      seenRef.current.add(eventId);
    }
    const seq = typeof data.seq === "number" ? data.seq : undefined;
    if (typeof seq === "number" && seq > lastSeqRef.current) {
      lastSeqRef.current = seq;
    }
    switch (frame.type) {
      case "chat_message":
        setMessages((prev) => upsertUserMessage(prev, data));
        break;
      case "chat_reply": {
        // FIX-180: drop stale pre-FIX-178 narrator cards persisted in run_events
        // for the review_gate_approved "approve" action. Before FIX-178 the narrator
        // wrote a CARD_CLARIFY row with this exact text; FIX-178 replaced the mechanism
        // with the resolved-gate inline text ("Review approved — build continues") and
        // removed the narrator emission, but existing DB rows were not deleted. When
        // getRunEvents replays them they produce a duplicate "Approved — build continues"
        // clarify bubble alongside the resolved gate card. Guard keys on the literal
        // deprecated text string — SC-001-safe (no pipeline_type / workflow name branch);
        // INV-3-safe (narrator is dormant on golden runs; this text never appears there).
        const deprecatedApproveCard =
          data.card_kind === "clarify" &&
          typeof data.text === "string" &&
          data.text === "Approved \u2014 build continues";
        if (deprecatedApproveCard) break;
        setMessages((prev) => upsertNarratorMessage(prev, data));
        // rqo Issue-2 part-2: finalize the active streaming reply if THIS terminal
        // matches it (by the message_id-derived bubble id or the frame event_id),
        // so the lane's "reading run data…" hint clears the instant the reply lands.
        setReplyStreaming((cur) => {
          if (!cur) return cur;
          const mid = typeof data.message_id === "string" ? data.message_id : "";
          if (mid && cur.id === `chat-reply:${mid}`) return null;
          const eid = typeof data.event_id === "string" ? data.event_id : "";
          if (eid && cur.id === eid) return null;
          return cur;
        });
        break;
      }
      case "chat_reply_chunk": {
        // m0o — accumulate the streamed delta into the SAME bubble the terminal
        // `chat_reply` finalizes (keyed `chat-reply:{message_id}`). No dedup/cursor
        // interaction: chunks carry no event_id and no real seq.
        setMessages((prev) => upsertStreamingReply(prev, data));
        // rqo Issue-2 part-2: mark this reply as actively streaming and refresh the
        // gap clock. A NEW object each chunk → the lane's gap timer re-arms (hides
        // the reading hint on fresh content, re-shows it if the stream stays silent).
        const chunkMid =
          typeof data.message_id === "string" ? data.message_id : "";
        if (chunkMid) {
          setReplyStreaming({
            id: `chat-reply:${chunkMid}`,
            lastChunkAt: Date.now(),
          });
        }
        break;
      }
      case "stream_attached":
        setStreamAttached({
          live: data.live === true,
          replayedThroughSeq:
            typeof data.replayed_through_seq === "number"
              ? data.replayed_through_seq
              : undefined,
        });
        break;
      case "review_gate_approved":
        // Mark the most recent unresolved gate card in the transcript as
        // resolved so it re-renders as a plain inline text
        // ("Review approved — build continues") instead of a styled box.
        // Generic — keyed on cardKind, never on workflow/agent name (SC-001).
        setMessages((prev) => {
          // Find the last unresolved gate card and flip it.
          const idx = prev.map((m, i) => ({ m, i }))
            .reverse()
            .find(({ m }) => m.cardKind === "gate" && !m.resolved)?.i;
          if (idx === undefined) return prev;
          const updated = [...prev];
          updated[idx] = { ...updated[idx], resolved: true };
          return updated;
        });
        break;
      case "concierge_proposal": {
        // ISS-054 / KAN-160: durable Concierge-held consequential proposal
        // (33-03/D-05). "pending" adds/updates the chip; a "resolved" row
        // (written on gate_action/revision confirm) removes it. chain proposals
        // never get a resolved row (FIX-115 — confirm fires onSuggestion, not
        // onConfirmProposal) so they stay until dismissed client-side.
        // GENERIC (SC-001/INV-1) — keyed on opaque channel/params, never a
        // workflow-name branch.
        const ch = typeof data.channel === "string" ? data.channel : "";
        const mid = typeof data.message_id === "string" ? data.message_id : "";
        const pStatus = typeof data.status === "string" ? data.status : "pending";
        if (pStatus === "resolved") {
          setProposals((prev) =>
            prev.filter((p) => !(p.channel === ch && p.messageId === mid)),
          );
          break;
        }
        if (!ch || !mid) break;
        const propId = `concierge-proposal:${mid}:${ch}`;
        const propParams = (data.params && typeof data.params === "object"
          ? data.params
          : {}) as Record<string, unknown>;
        setProposals((prev) => {
          // Exact-id dedup: already have this exact proposal, nothing to do.
          if (prev.some((p) => p.id === propId)) return prev;
          // Same-channel replacement: remove any older proposal for the same
          // channel (e.g. two consecutive "create prototype" turns both produce
          // a chain proposal — keep only the latest). This prevents duplicate
          // chips stacking up from repeated chat turns.
          const withoutSameChannel = prev.filter((p) => p.channel !== ch);
          return [...withoutSameChannel, { id: propId, channel: ch, params: propParams, messageId: mid, proposalRunId: runId ?? undefined }];
        });
        break;
      }
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
      // FIX-119: use the caller-supplied existingMessageId (from addOptimisticMessage)
      // to reconcile an already-added bubble, rather than minting a new id and
      // creating a duplicate user bubble.
      const messageId = options?.existingMessageId ?? mintMessageId();
      const optimistic: ChatMessage = {
        id: messageId,
        chatSessionId: runId ?? "",
        role: "user",
        content: text,
        createdAt: new Date().toISOString(),
        attachments,
        runId: runId ?? undefined,
      };
      // Optimistic render — skip when BOTH text is empty AND no file attachments
      // (e.g. confirm-proposal turns send text="" and should not add a blank bubble).
      // FIX-218: a file-only send (text="" but attachments present) DOES render a
      // bubble — the file chips inside the bubble are the user-visible content.
      const hasFileAttachments = (attachments ?? []).some((a) => a.kind === "file");
      if (text.trim() || hasFileAttachments) {
        setMessages((prev) =>
          prev.some((m) => m.id === messageId) ? prev : [...prev, optimistic],
        );
      }
      const payload: Record<string, unknown> = {
        text,
        attachments: attachments ?? [],
        // FIX-210: when `proposalMessageId` is set (confirm-proposal flow), the
        // backend's `_load_pending_proposal` must receive the ORIGINAL ASK turn's
        // `message_id` (the one stored in `concierge-proposal:{id}:{channel}`),
        // NOT a freshly minted client id. Override here; all other sends use the
        // client-minted id for optimistic-bubble reconciliation.
        message_id: options?.proposalMessageId ?? messageId,
      };
      // 43-02 (A.1 CRUX): fold the Concierge send flags onto the payload ONLY
      // when supplied — field names match the backend MessageCommand exactly
      // (`concierge` / `confirm_proposal`). With no options the payload is
      // byte-identical to the pre-43-02 shape (dormant, INV-3).
      if (options?.concierge) payload.concierge = true;
      if (options?.confirm_proposal) {
        payload.confirm_proposal = options.confirm_proposal;
      }
      // c72: fold the generic chain hints ONLY when non-empty — an absent/empty
      // array writes NO key (byte-identical dormant payload, INV-3).
      if (options?.chain_hints && options.chain_hints.length > 0) {
        payload.chain_hints = options.chain_hints;
      }
      // FIX-218 (KAN-170): fold pre-extracted file text ONLY when non-empty —
      // absent/empty ⇒ NO `file_contents` key (byte-identical dormant payload, INV-3).
      if (options?.file_contents && options.file_contents.length > 0) {
        payload.file_contents = options.file_contents;
      }
      if (legacyWsSend) {
        // Flag-OFF legacy WS up-channel (LOCK-B): same transcript. The concierge
        // fields ride the payload but the WS transport does not deliver them to
        // the Concierge until the Part-C SSE cutover — expected (43-02 proves
        // the payload shape + the routing decision, not a live round-trip).
        legacyWsSend({ type: "user_message", ...payload });
      } else {
        // DEF-44-12-2 — fire-and-forget: await the up-channel, THEN (if a
        // fetchEvents is wired) pull events since the last seen seq and fold each
        // through handleFrame. This delivers the durable-only Concierge reply
        // (never queued → the live tail never carries it) on both terminal and
        // live opened runs. The per-hook event_id dedup guarantees idempotency
        // (no duplicate reply, no duplicate echo). The synchronous optimistic
        // render + `return messageId` above are unaffected (Test 5 send routing).
        void (async () => {
          // FIX-211b: use targetRunId to POST to the correct run when the proposal
          // was written to a run that is no longer the currently viewed one.
          const postRunId = options?.targetRunId ?? runId;
          const result = await sendCommand(postRunId, payload);
          // FIX-211: when a confirm-proposal response includes a revision_run_id
          // (concierge confirmed a revision), call the caller's onRevisionLaunched
          // callback so the UI can attachRun + switchViewTo the new child run.
          if (result && options?.onRevisionLaunched) {
            options.onRevisionLaunched(result);
          }
          if (!fetchEvents) return;
          try {
            const newFrames = await fetchEvents(postRunId, lastSeqRef.current);
            for (const f of newFrames) handleFrame(f);
          } catch {
            // A re-fetch failure must not surface — the optimistic turn stands;
            // a later live frame / reopen still reconciles by event_id.
          }
        })();
      }
      return messageId;
    },
    [runId, sendCommand, legacyWsSend, fetchEvents, handleFrame],
  );

  // DEF-44-12-4 (Piece 3) — reset + fold the seeded durable chat rows on an
  // explicit history-open. handleFrame re-populates seenRef/lastSeqRef and
  // appends chat turns; non-chat frames fall through its default branch. The
  // setMessages([]) reset is queued before the per-frame updaters, so React
  // applies them in order (empty → folded turns).
  const seedTranscript = useCallback(
    (frames: RunChatFrame[], isTerminalRun?: boolean) => {
      seenRef.current.clear();
      lastSeqRef.current = 0;
      setMessages([]);
      // rqo Issue-2 part-2: an explicit history-open resets the streaming hint too
      // (a seeded transcript's chat_reply rows are all terminal — never mid-stream).
      setReplyStreaming(null);
      for (const f of frames) handleFrame(f);
      // Auto-resolve all gate cards when seeding a completed/terminal run.
      // A gate in a completed run was necessarily approved — there is no pending
      // review box to show. This covers history-reopen and family-seed paths
      // where review_gate_approved may not be in the durable event log.
      // Generic — keyed on cardKind, never on workflow/agent name (SC-001).
      if (isTerminalRun) {
        setMessages((prev) =>
          prev.map((m) =>
            m.cardKind === "gate" && !m.resolved ? { ...m, resolved: true } : m
          )
        );
      }
    },
    [handleFrame],
  );

  /**
   * FIX-119 — add a user bubble to LOCAL STATE ONLY, with NO backend call.
   * Used when the caller needs to show the user's text IMMEDIATELY (e.g. before
   * a classify-intent LLM round-trip in handleFreeText) without triggering any
   * mechanical-router side-effect (which would create a spurious revision run on
   * a terminal/complete run — the double-version bug from FIX-118). The returned
   * `messageId` is stable and can be passed back to `sendMessage` via
   * `options.existingMessageId` to reconcile the existing bubble in place instead
   * of creating a duplicate.
   */
  const addOptimisticMessage = useCallback(
    (text: string, attachments?: ChatAttachment[]): string => {
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
      setMessages((prev) =>
        prev.some((m) => m.id === messageId) ? prev : [...prev, optimistic],
      );
      return messageId;
    },
    [runId],
  );

  /**
   * FIX-172: Fold frames into the transcript without resetting the seen-set or
   * messages state. Used after pipeline_complete to recover narrator chat_reply
   * cards that the SSE race may have dropped. Idempotent: seenRef deduplicates
   * already-processed frames so re-folding a durable log replay is safe.
   */
  const appendFrames = useCallback(
    (frames: RunChatFrame[]) => {
      for (const f of frames) handleFrame(f);
    },
    [handleFrame],
  );

  /**
   * FIX-176: Expose the last-seen seq so FIX-172's appendRunChatFrames caller
   * can fetch only events AFTER the last delivered seq, preventing duplicate
   * chat_reply cards (e.g. "Revision started") from re-appearing.
   */
  const getLastSeq = useCallback((): number => {
    return lastSeqRef.current;
  }, []);

  /**
   * ISS-054 / KAN-160: client-side-only dismiss — removes the chip from local
   * state. A hard reload will re-show a still-pending durable row (accepted
   * limitation; the row was never designed to be dismissible server-side).
   */
  const dismissProposal = useCallback((id: string) => {
    setProposals((prev) => prev.filter((p) => p.id !== id));
  }, []);

  return { messages, sendMessage, addOptimisticMessage, streamAttached, replyStreaming, seedTranscript, appendFrames, getLastSeq, proposals, dismissProposal };
}
