"use client";

/**
 * useRunStream — the SSE run transport (Phase 29, CHAT-07, D-14 a/c/f). SSE is
 * the sole run transport (44-06 hard cutoff); this hook owns the per-run
 * down-channel and its Last-Event-ID reconnect/replay.
 *
 * It consumes the per-run SSE down-channel
 * (`GET /api/runs/{id}/events/stream`) and mirrors the WS path's contract so the
 * SAME downstream reducer (`handlePipelineMessage`) and the SAME dedup-by-
 * `event_id` + max-seen-`seq` cursor that `dashboard/page.tsx` already applies
 * keep working UNCHANGED:
 *
 *   - Envelope parity: each SSE block (`id: {seq}` / `event: {type}` /
 *     `data: {json}`) is dispatched as `{ type, data }` — the exact shape the WS
 *     `onmessage` handler produces, so `msg.data.event_id` / `msg.data.seq`
 *     dedup + cursor still bind (mockWs.ts / mockSse.ts wire model).
 *   - Native `Last-Event-ID` resume (D-14): the fetch-stream reconnect re-issues
 *     the request carrying `Last-Event-ID: <max-seen seq>` so the server replays
 *     only frames past the cursor (worst case = full replay; correctness by the
 *     downstream `event_id` dedup).
 *   - Keepalive drop: `pipeline_heartbeat` / `pong` are swallowed (WS parity).
 *   - Exponential-backoff reconnect capped at 30s, no give-up (WS parity).
 *   - Connection state machine surfaced (connecting → replaying → live →
 *     reconnecting) for the provider (D-14d).
 *   - JWT-expiry (4001) path with SILENT refresh before expiry (D-14f, mitigates
 *     T-29-07-2): a pre-emptive refresh timer fires ahead of `exp`, and a mid-
 *     stream 401 attempts one silent refresh before falling back to the WS
 *     path's clear-token-and-redirect behavior — so there is no mid-run logout.
 *
 * NB: this uses `fetch` + a `ReadableStream` reader rather than the browser
 * `EventSource`, because `EventSource` cannot attach the `Authorization: Bearer`
 * header (the JWT). The fetch reader sends `Authorization` + `Last-Event-ID`
 * headers explicitly — the same native resume semantics, credential-safe.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { getToken, handleSessionExpiry, refreshAccessToken } from "@/lib/api";
import { ENV } from "@/lib/env";
import { parseSseBlock } from "@/lib/sseFrame";
import { STREAM_TERMINAL_TYPES } from "@/types";

/**
 * The connection state machine (D-14d). `connecting`/`reconnecting` mirror the
 * WS `ConnectionStatus`; `replaying` (attached, draining the durable tail) and
 * `live` (caught up, `stream_attached {live:true}` seen) are the SSE-specific
 * phases the provider surfaces.
 */
export type RunConnectionPhase =
  | "idle"
  | "connecting"
  | "replaying"
  | "live"
  | "reconnecting"
  | "disconnected"
  | "failed";

/** The dispatched envelope — identical in shape to the WS `{ type, data }` frame. */
export interface RunStreamMessage {
  type: string;
  data: Record<string, unknown>;
  /** Injected by RunConnectionProvider: the run id whose SSE stream this frame
   *  was sourced from. Used by handleWebSocketMessage to route frames to the
   *  correct pipelineState reducer when multiple concurrent runs are attached.
   *  Absent on legacy WS paths and Concierge /messages streaming. */
  _sourceRunId?: string;
}

export interface UseRunStreamConfig {
  /** The run whose event stream to attach to. `null` → idle (no connection). */
  runId: string | null;
  /** JWT; when it changes the stream re-attaches (WS-path parity). */
  token: string | null;
  /** Frame sink — receives every non-keepalive frame as `{ type, data }`. */
  onMessage?: (msg: RunStreamMessage) => void;
  /**
   * Resume cursor (max-seen `seq`) to seed the first attach as `Last-Event-ID`.
   * Lets an app-level owner (RunConnectionProvider, D-14c) resume across a page
   * reload from a persisted cursor. Absent → full replay.
   */
  afterSeq?: number | null;
  /** Called whenever the resume cursor advances (persist for D-14c). */
  onCursor?: (seq: number) => void;
  /** Master switch — when false the hook stays idle (flag-gated by the caller). */
  enabled?: boolean;
}

export interface UseRunStreamReturn {
  phase: RunConnectionPhase;
  /** Force an immediate reconnect (resets the backoff counter). */
  reconnect: () => void;
  lastMessage: RunStreamMessage | null;
  lastError: string | null;
  /** The max-seen `seq` cursor (the `Last-Event-ID` a reconnect would carry). */
  cursor: number | null;
}

const BASE_DELAY_MS = 1000;
const MAX_RETRY_DELAY_MS = 30000; // cap backoff at 30s — never give up (WS parity)
const REFRESH_SKEW_MS = 60000; // silently refresh the JWT 60s before it expires

/** Decode a JWT's `exp` (seconds) into an absolute ms timestamp; null if absent. */
function jwtExpiryMs(token: string | null): number | null {
  if (!token) return null;
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const json = JSON.parse(
      atob(payload.replace(/-/g, "+").replace(/_/g, "/")),
    ) as { exp?: number };
    return typeof json.exp === "number" ? json.exp * 1000 : null;
  } catch {
    return null;
  }
}

/**
 * Attempt a SILENT token refresh (D-14f). Best-effort: returns true only when a
 * fresh token was obtained. Any failure (4xx, network, a local/break-glass user
 * with no Cognito refresh token) resolves false so the caller falls back to the
 * natural-expiry path — never throwing, never logging the user out on its own.
 *
 * Delegates to the shared `refreshAccessToken()` in `lib/api` rather than
 * re-implementing the call: the REST client now runs the same refresh on a 401
 * (Cognito Phase 4), and two copies would drift — and would defeat the
 * single-flight coalescing that keeps a burst of simultaneous 401s from minting
 * one refresh each.
 */
async function attemptSilentRefresh(): Promise<boolean> {
  return (await refreshAccessToken()) !== null;
}

export function useRunStream(config: UseRunStreamConfig): UseRunStreamReturn {
  const { runId, token, onMessage, afterSeq, onCursor, enabled = true } = config;

  const [phase, setPhase] = useState<RunConnectionPhase>("idle");
  // FIX: lastMessage is NOT React state — same reason as cursor.
  // setLastMessage fires on EVERY SSE frame, causing a re-render storm with
  // concurrent runs. No production caller reads lastMessage from the return value
  // (only RunConnectionProvider.test.tsx mocks it as null). Track it as a ref.
  const lastMessageRef = useRef<RunStreamMessage | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);
  // FIX: cursor is NOT React state — it only needs to be a ref.
  // Making it useState caused setCursor() to fire on every SSE frame (each frame
  // has a seq number), which triggered a re-render storm: with multiple concurrent
  // runs each emitting frames, React exceeded its maximum update depth limit.
  // The cursor value is already tracked in cursorRef for Last-Event-ID; the only
  // consumer of the returned `cursor` is a test — no production code reads it.
  const cursorStateRef = useRef<number | null>(afterSeq ?? null);

  // Refs so the connect loop reads the latest callbacks without re-subscribing.
  const onMessageRef = useRef(onMessage);
  const onCursorRef = useRef(onCursor);
  const cursorRef = useRef<number | null>(afterSeq ?? null);
  const retryCountRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const stoppedRef = useRef(false);
  const connectRef = useRef<() => void>(() => {});
  // BUG-015: the last `stream_attached` liveness for the CURRENT connection.
  // Reset to false at the top of every connect() so liveness is judged per-
  // connection — a genuine live-stream drop still reconnects; a non-live attach
  // (a terminal run's post-replay close) does NOT (else it re-replays ~14k events
  // in a loop and flaps the "Reconnecting…" banner).
  const sawNonLiveAttachRef = useRef(false);

  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);
  useEffect(() => {
    onCursorRef.current = onCursor;
  }, [onCursor]);

  // The whole connect/reconnect lifecycle lives inside one effect keyed on the
  // identity inputs (runId/token/enabled). Helpers are closures; `connectRef`
  // exposes the latest `connect` to the imperative `reconnect()` handle.
  useEffect(() => {
    stoppedRef.current = false;

    if (typeof window === "undefined") return;
    if (!enabled || !runId) {
      setPhase("idle");
      return;
    }

    // Seed the resume cursor from the caller's persisted value (D-14c).
    if (afterSeq != null && cursorRef.current == null) {
      cursorRef.current = afterSeq;
      cursorStateRef.current = afterSeq;
    }

    const clearTimers = () => {
      if (reconnectTimerRef.current !== null) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (refreshTimerRef.current !== null) {
        clearTimeout(refreshTimerRef.current);
        refreshTimerRef.current = null;
      }
    };

    const handleAuthExpiry = () => {
      // Mirror the WS path's 4001 close: clear the token and bounce to
      // routes.login({ expired: true }) via the shared FR-015 helper. Reached
      // only after a silent refresh already failed — so this is a true expiry,
      // not a transient blip (no mid-run logout, T-29-07-2).
      handleSessionExpiry();
      setPhase("disconnected");
      setLastError("Your session has expired. Please log in again.");
    };

    const scheduleRefresh = () => {
      if (refreshTimerRef.current !== null) clearTimeout(refreshTimerRef.current);
      const expMs = jwtExpiryMs(getToken());
      if (expMs == null) return;
      const fireIn = expMs - Date.now() - REFRESH_SKEW_MS;
      if (fireIn <= 0) return; // already inside the skew window — reactive path covers it
      refreshTimerRef.current = setTimeout(() => {
        void attemptSilentRefresh().then((ok) => {
          if (ok && !stoppedRef.current) connect(); // re-attach with the fresh token
        });
      }, fireIn);
    };

    const dispatchBlock = (block: string) => {
      // The envelope parse lives in ONE shared helper (INV-12); the cursor
      // advance, keepalive drop, stream_attached liveness and onMessage sink stay
      // hook-local around it. `parseSseBlock` returns null for empty/malformed
      // blocks (same discard-and-return behavior as before extraction).
      const parsed = parseSseBlock(block);
      if (!parsed) return;
      const { type, data } = parsed;

      // The `id:` line is a hook-local cursor concern (not part of the envelope
      // parse), so it stays here for the seq fallback below.
      let idLine: string | undefined;
      for (const line of block.split("\n")) {
        if (line.startsWith("id:")) {
          idLine = line.slice(3).trim();
          break;
        }
      }

      // Advance the max-seen seq cursor from data.seq (fallback to the id line).
      const seq =
        typeof data.seq === "number"
          ? (data.seq as number)
          : idLine != null && idLine !== ""
          ? Number(idLine)
          : undefined;
      if (
        typeof seq === "number" &&
        !Number.isNaN(seq) &&
        (cursorRef.current == null || seq > cursorRef.current)
      ) {
        cursorRef.current = seq;
        cursorStateRef.current = seq;
        onCursorRef.current?.(seq);
      }

      // Keepalives never reach the reducer (WS parity).
      if (type === "pipeline_heartbeat" || type === "pong") return;

      // Guard: don't call setState after the connection has been torn down.
      // In React strict-mode / Turbopack dev, the effect cleanup runs before
      // the async reader loop drains; frames arriving after cleanup would call
      // setState on an unmounted or re-mounted hook instance, triggering
      // "Maximum update depth exceeded".
      if (stoppedRef.current) return;

      // stream_attached {live:true} → caught up, promote to the live phase (D-14d).
      // Also record the attach liveness for the close branch (BUG-015): a non-live
      // attach means this run is terminal, so its close must NOT trigger a reconnect.
      if (type === "stream_attached") {
        sawNonLiveAttachRef.current = data.live !== true;
        if (data.live === true) setPhase("live");
      }

      // BUG-015 / ISS-147 (terminal → non-live attach): the members of STREAM_TERMINAL_TYPES
      // are the ONLY events that close the stream — the backend intentionally closes the
      // stream right after draining them. Mark the connection as "non-live" so the
      // close-branch below calls setPhase("disconnected") instead of scheduleReconnect().
      // Without this, sawNonLiveAttachRef stays false (was a live stream_attached{live:true})
      // and the stream close triggers a yellow "Reconnecting…" banner on every Stop click
      // or every successful pipeline_complete. The detachRun call in dashboard/page.tsx
      // is additive insurance; this ref-set is guaranteed synchronous within the same
      // microtask as the frame dispatch. ISS-147: moved to constant to prevent future
      // omission (e.g. pipeline_complete was missing, now consolidated in STREAM_TERMINAL_TYPES).
      if (STREAM_TERMINAL_TYPES.has(type)) {
        sawNonLiveAttachRef.current = true;
      }

      // Stamp the source run onto the envelope (the SINGLE stamping site for
      // stream frames — this hook is instantiated once per run, so `runId` here is
      // authoritative). Downstream run-scoping depends on it; see RunStreamMessage.
      const msg: RunStreamMessage = { type, data, _sourceRunId: runId };
      lastMessageRef.current = msg;
      onMessageRef.current?.(msg);
    };

    const scheduleReconnect = () => {
      const delay = Math.min(
        BASE_DELAY_MS * Math.pow(2, retryCountRef.current),
        MAX_RETRY_DELAY_MS,
      );
      retryCountRef.current += 1;
      setPhase("reconnecting");
      setLastError(
        `Connection lost. Reconnecting in ${Math.round(delay / 1000)}s… (attempt ${retryCountRef.current})`,
      );
      reconnectTimerRef.current = setTimeout(() => {
        connect();
      }, delay);
    };

    const connect = () => {
      // BUG-015: liveness is per-connection — reset before every (re)connect so a
      // genuine live drop still reconnects even after a prior non-live attach.
      sawNonLiveAttachRef.current = false;

      const currentToken = getToken();
      if (!currentToken) {
        setPhase("disconnected");
        return;
      }

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setPhase(retryCountRef.current > 0 ? "reconnecting" : "connecting");

      const headers: Record<string, string> = {
        Accept: "text/event-stream",
        Authorization: `Bearer ${currentToken}`,
      };
      // Native resume: carry the max-seen seq so the server replays only newer
      // frames (worst case full replay; dedup makes it idempotent).
      if (cursorRef.current != null) {
        headers["Last-Event-ID"] = String(cursorRef.current);
      }

      const url = `${ENV.API_URL}/api/runs/${runId}/events/stream`;

      void (async () => {
        try {
          const res = await fetch(url, {
            headers,
            signal: controller.signal,
            cache: "no-store",
          });

          if (res.status === 401 || res.status === 403) {
            // Mid-stream auth failure — try ONE silent refresh before giving up.
            const refreshed = await attemptSilentRefresh();
            if (refreshed && !stoppedRef.current) {
              connect();
              return;
            }
            handleAuthExpiry();
            return;
          }

          if (!res.ok || !res.body) {
            throw new Error(`SSE stream failed with status ${res.status}`);
          }

          // Attached — reset backoff, enter the replay phase, arm the pre-expiry
          // refresh timer.
          retryCountRef.current = 0;
          setLastError(null);
          setPhase("replaying");
          scheduleRefresh();

          const reader = res.body.getReader();
          const decoder = new TextDecoder();
          let buf = "";
          for (;;) {
            const { value, done } = await reader.read();
            if (done) break;
            // Normalize CRLF -> LF so the backend's `\r\n\r\n` frame separators
            // (sse-starlette) boundary-match the `indexOf("\n\n")` split below.
            // This targets only line-ending CRLF; JSON string data escapes
            // newlines as literal `\n`, never raw `\r\n`, so payloads are
            // untouched (BUG-014-B).
            //
            // SSE-003: normalize AFTER appending to `buf`, never per-chunk. A chunk
            // boundary can fall BETWEEN the `\r` and the `\n` of a CRLF, and neither
            // chunk then contains the pair for the regex to match — so normalizing
            // each chunk in isolation (the previous
            // `buf += decode(...).replace(...)`) let that CRLF through un-normalized
            // and leaked a stray `\r` into the tail of a data line. Appending raw and
            // normalizing the accumulated buffer closes the split across the seam:
            // the lone trailing `\r` stays in `buf`, and the next chunk's leading
            // `\n` completes the pair for this same replace. Idempotent on the
            // retained remainder (after a pass, no `\r\n` survives), and `buf` is
            // drained to at most one partial frame per iteration, so re-scanning it
            // is bounded.
            buf += decoder.decode(value, { stream: true });
            buf = buf.replace(/\r\n/g, "\n");
            let idx: number;
            while ((idx = buf.indexOf("\n\n")) !== -1) {
              const rawBlock = buf.slice(0, idx);
              buf = buf.slice(idx + 2);
              dispatchBlock(rawBlock);
            }
          }
          // Flush any trailing block (server closed without a terminal blank line).
          if (buf.trim()) dispatchBlock(buf);

          // The response ended (server closed the connection). Unless we were
          // intentionally torn down, treat it as a drop and reconnect from the
          // cursor (native Last-Event-ID resume). EXCEPTION (BUG-015): the backend
          // closes a TERMINAL run's stream after replay (stream_attached{live:false}
          // then close) — reconnecting there re-replays the whole run in a loop, so
          // when the last attach was non-live we settle quiescent instead.
          if (!stoppedRef.current && !controller.signal.aborted) {
            if (sawNonLiveAttachRef.current) {
              setPhase("disconnected");
            } else {
              scheduleReconnect();
            }
          }
        } catch {
          if (controller.signal.aborted || stoppedRef.current) return;
          scheduleReconnect();
        }
      })();
    };

    connectRef.current = connect;
    connect();

    return () => {
      stoppedRef.current = true;
      clearTimers();
      abortRef.current?.abort();
      abortRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, token, enabled]);

  const reconnect = useCallback(() => {
    retryCountRef.current = 0;
    connectRef.current();
  }, []);

  return { phase, reconnect, lastMessage: lastMessageRef.current, lastError, cursor: cursorStateRef.current };
}
