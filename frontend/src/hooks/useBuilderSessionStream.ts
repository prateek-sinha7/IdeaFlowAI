"use client";

/**
 * useBuilderSessionStream — the Session_Stream reader of the AI Workflow Builder
 * (design 3.3.4 and 3.10.3, Req 13.2, 13.3, 13.5, 17.12, 17.13, 40.9, 48.10).
 *
 * It attaches to `GET /api/workflow-builder/sessions/{id}/events` with `fetch`
 * and a `ReadableStream` reader, because `EventSource` cannot send the
 * `Authorization: Bearer` header. Blocks go through the shared `parseSseBlock`.
 *
 *   - No `Last-Event-ID`: text and thinking deltas are not stored, so every
 *     (re)connect starts with a fresh `snapshot` event instead of a replay.
 *   - The wire `data` carries no `type` key, so each event is rebuilt as
 *     `{ ...data, type }` to give a `BuilderEvent` union (decision 18.1).
 *   - Reconnect with backoff 1 s doubling to 30 s, with no give-up while mounted.
 *   - A silent token refresh runs ahead of expiry (`refreshOnce`, `getTokenExpiryMs`)
 *     and re-attaches with the new token.
 *   - The hook stops on a 404, on `session_deleted` and on `session_revoked`.
 *     `session_revoked` also calls `expireSession()` (pending G-14, G-15).
 *
 * The hook is mounted by the builder host while the panel is mounted, collapsed
 * or not. Nothing under `components/workflow` opens a stream.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { expireSession, getToken, getTokenExpiryMs, refreshOnce, SESSION_REFRESH_SKEW_MS } from "@/lib/api";
import { ENV } from "@/lib/env";
import { parseSseBlock } from "@/lib/sseFrame";
import type { BuilderEvent, BuilderEventType } from "@/types/workflowBuilder";

export type BuilderStreamPhase =
  | "idle"
  | "connecting"
  | "open"
  | "reconnecting"
  | "closed_not_found"
  | "closed_deleted"
  | "closed_revoked"
  | "closed_auth";

export interface UseBuilderSessionStreamConfig {
  /** The session to follow. `null` keeps the hook idle. */
  sessionId: string | null;
  /** Master switch. When false the hook stays idle and holds no connection. */
  enabled: boolean;
  /** Receives every event, as one member of the `BuilderEvent` union. */
  onEvent: (event: BuilderEvent) => void;
}

export interface UseBuilderSessionStreamReturn {
  phase: BuilderStreamPhase;
  /** Re-attach now and reset the backoff. No-op once the stream has closed for good. */
  reconnect: () => void;
}

export const BUILDER_STREAM_BASE_DELAY_MS = 1000;
export const BUILDER_STREAM_MAX_DELAY_MS = 30000;

const BASE_PATH = "/api/workflow-builder";

const KNOWN_EVENT_TYPES: ReadonlySet<string> = new Set<BuilderEventType>([
  "snapshot",
  "turn_started",
  "stage",
  "thinking",
  "tool_started",
  "tool_finished",
  "check_result",
  "draft_applied",
  "text",
  "limit_warning",
  "turn_completed",
  "error",
  "draft_restored",
  "session_deleted",
  "session_revoked",
]);

/** Backoff delay for the n-th consecutive failure (0-based): 1 s, 2 s, ... capped at 30 s. */
export function builderBackoffDelayMs(attempt: number): number {
  return Math.min(BUILDER_STREAM_BASE_DELAY_MS * 2 ** attempt, BUILDER_STREAM_MAX_DELAY_MS);
}

export function useBuilderSessionStream(
  config: UseBuilderSessionStreamConfig,
): UseBuilderSessionStreamReturn {
  const { sessionId, enabled, onEvent } = config;
  const [phase, setPhase] = useState<BuilderStreamPhase>("idle");
  // Idle is derived, not stored: a disabled hook holds no connection.
  const active = enabled && sessionId !== null;

  // The connect loop reads the latest callback without re-subscribing.
  const onEventRef = useRef(onEvent);
  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  const reconnectRef = useRef<() => void>(() => {});

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!active || !sessionId) {
      reconnectRef.current = () => {};
      return;
    }

    let stopped = false; // set by cleanup
    let closedForGood = false; // 404, session_deleted, session_revoked, auth expiry
    let retryCount = 0;
    let authRetried = false;
    let controller: AbortController | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let refreshTimer: ReturnType<typeof setTimeout> | null = null;

    const url = `${ENV.API_URL}${BASE_PATH}/sessions/${encodeURIComponent(sessionId)}/events`;

    const clearTimers = () => {
      if (reconnectTimer !== null) clearTimeout(reconnectTimer);
      if (refreshTimer !== null) clearTimeout(refreshTimer);
      reconnectTimer = null;
      refreshTimer = null;
    };

    const closeForGood = (next: BuilderStreamPhase) => {
      closedForGood = true;
      clearTimers();
      controller?.abort();
      if (!stopped) setPhase(next);
    };

    const handleAuthExpiry = () => {
      closeForGood("closed_auth");
      expireSession();
    };

    const scheduleReconnect = () => {
      if (stopped || closedForGood) return;
      const delay = builderBackoffDelayMs(retryCount);
      retryCount += 1;
      setPhase("reconnecting");
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        connect();
      }, delay);
    };

    const scheduleRefresh = () => {
      if (refreshTimer !== null) clearTimeout(refreshTimer);
      refreshTimer = null;
      const expMs = getTokenExpiryMs(getToken());
      if (expMs === null) return;

      const refreshAndReattach = async (): Promise<void> => {
        const refreshed = await refreshOnce();
        if (stopped || closedForGood) return;
        if (refreshed !== null) {
          connect();
          return;
        }
        // Another refresher may have replaced the token: re-arm on the new expiry.
        if (getTokenExpiryMs(getToken()) !== expMs) {
          scheduleRefresh();
          return;
        }
        // A transient failure before true expiry must not log the user out early.
        const remaining = expMs - Date.now();
        if (remaining > 0) {
          refreshTimer = setTimeout(() => void refreshAndReattach(), remaining);
          return;
        }
        handleAuthExpiry();
      };

      const fireIn = expMs - Date.now() - SESSION_REFRESH_SKEW_MS;
      if (fireIn <= 0) {
        void refreshAndReattach();
        return;
      }
      refreshTimer = setTimeout(() => void refreshAndReattach(), fireIn);
    };

    /** Returns true when the block ended the stream for good. */
    const dispatchBlock = (block: string): boolean => {
      const parsed = parseSseBlock(block);
      // Keep-alive comments and unknown event names carry nothing for the panel.
      if (!parsed || !KNOWN_EVENT_TYPES.has(parsed.type)) return false;
      if (stopped || closedForGood) return true;

      // First real event on this connection: it is attached, so the backoff resets.
      retryCount = 0;
      authRetried = false;
      setPhase("open");

      const event = { ...parsed.data, type: parsed.type } as BuilderEvent;
      onEventRef.current(event);

      if (event.type === "session_deleted") {
        closeForGood("closed_deleted");
        return true;
      }
      if (event.type === "session_revoked") {
        closeForGood("closed_revoked");
        expireSession();
        return true;
      }
      return false;
    };

    const connect = () => {
      if (stopped || closedForGood) return;
      const token = getToken();
      if (!token) {
        handleAuthExpiry();
        return;
      }

      controller?.abort();
      const current = new AbortController();
      controller = current;
      setPhase(retryCount > 0 ? "reconnecting" : "connecting");

      void (async () => {
        try {
          const res = await fetch(url, {
            headers: { Accept: "text/event-stream", Authorization: `Bearer ${token}` },
            signal: current.signal,
            cache: "no-store",
          });

          if (res.status === 404) {
            closeForGood("closed_not_found");
            return;
          }
          if (res.status === 401 || res.status === 403) {
            // One silent refresh, then give up; a second 401 in a row ends the session.
            if (!authRetried && (await refreshOnce()) !== null && !stopped && !closedForGood) {
              authRetried = true;
              connect();
              return;
            }
            if (!stopped && !closedForGood) handleAuthExpiry();
            return;
          }
          if (!res.ok || !res.body) {
            throw new Error(`Builder stream failed with status ${res.status}`);
          }

          scheduleRefresh();

          const reader = res.body.getReader();
          const decoder = new TextDecoder();
          let buf = "";
          for (;;) {
            const { value, done } = await reader.read();
            if (done) break;
            // Normalise after appending, so a CRLF split across two chunks still matches.
            buf += decoder.decode(value, { stream: true });
            buf = buf.replace(/\r\n/g, "\n");
            let idx: number;
            while ((idx = buf.indexOf("\n\n")) !== -1) {
              const block = buf.slice(0, idx);
              buf = buf.slice(idx + 2);
              if (dispatchBlock(block)) {
                void reader.cancel().catch(() => undefined);
                return;
              }
            }
          }
          if (buf.trim() && dispatchBlock(buf)) return;

          // The server closed the stream. Reconnect, which starts with a new snapshot.
          if (!current.signal.aborted) scheduleReconnect();
        } catch {
          if (current.signal.aborted || stopped || closedForGood) return;
          scheduleReconnect();
        }
      })();
    };

    reconnectRef.current = () => {
      if (stopped || closedForGood) return;
      retryCount = 0;
      if (reconnectTimer !== null) clearTimeout(reconnectTimer);
      reconnectTimer = null;
      connect();
    };

    connect();

    return () => {
      stopped = true;
      clearTimers();
      controller?.abort();
      controller = null;
      reconnectRef.current = () => {};
    };
  }, [sessionId, active]);

  const reconnect = useCallback(() => {
    reconnectRef.current();
  }, []);

  return { phase: active ? phase : "idle", reconnect };
}
