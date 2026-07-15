"use client";

/**
 * useHandoffSocket — the dedicated WebSocket client for the SURVIVING
 * handoff socket surface (`/ws/handoff/{token}`, decision 2 / D10). This is the
 * external-IDE handoff live channel and was intentionally NOT part of the chat
 * socket retirement: the run/pipeline/chat transports moved to SSE + REST, but
 * the handoff surface stays a token-authenticated WebSocket.
 *
 * Behavior byte-identical to the retired shared chat socket hook it was
 * extracted from: connect + exponential backoff (no retry cap, 30s ceiling) +
 * the JWT-expired 4001 close handling + the client-side keepalive ping.
 * `ConnectionStatus` is RE-EXPORTED from here so remaining type-only consumers
 * (DashboardLayout / dashboard) keep a single source.
 *
 * The caller supplies its own `url` (HandoffWorkflow derives the handoff socket
 * URL from `ENV.API_URL`) — this hook has no default URL.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { StreamMessage } from "@/types/index";
import { clearToken, getToken } from "@/lib/api";

export type ConnectionStatus =
  | "connecting"
  | "connected"
  | "disconnected"
  | "reconnecting"
  | "failed";

export interface UseHandoffSocketConfig {
  url?: string;
  token: string | null;
  onMessage?: (msg: StreamMessage) => void;
}

export interface UseHandoffSocketReturn {
  send: (message: string) => boolean;
  connectionStatus: ConnectionStatus;
  reconnect: () => void;
  lastMessage: StreamMessage | null;
  lastError: string | null;
}

const BASE_DELAY_MS = 1000;
const MAX_RETRY_DELAY_MS = 30000; // cap backoff at 30s — never give up
const JWT_EXPIRED_CODE = 4001;

export function useHandoffSocket(
  config: UseHandoffSocketConfig,
): UseHandoffSocketReturn {
  const { url, token, onMessage } = config;

  const [connectionStatus, setConnectionStatus] =
    useState<ConnectionStatus>("disconnected");
  const [lastMessage, setLastMessage] = useState<StreamMessage | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const retryCountRef = useRef(0);
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onMessageRef = useRef(onMessage);
  const intentionalCloseRef = useRef(false);

  // Keep onMessage ref up to date without triggering reconnects
  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  const cleanup = useCallback(() => {
    if (retryTimeoutRef.current !== null) {
      clearTimeout(retryTimeoutRef.current);
      retryTimeoutRef.current = null;
    }
    if (wsRef.current) {
      // Clear ping interval if set
      const ws = wsRef.current as WebSocket & { _pingInterval?: ReturnType<typeof setInterval> };
      if (ws._pingInterval) {
        clearInterval(ws._pingInterval);
        ws._pingInterval = undefined;
      }
      wsRef.current.onopen = null;
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      wsRef.current.onmessage = null;
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const connect = useCallback(() => {
    const currentToken = getToken();
    if (!currentToken || !url) {
      setConnectionStatus("disconnected");
      return;
    }

    cleanup();
    intentionalCloseRef.current = false;

    setConnectionStatus(
      retryCountRef.current > 0 ? "reconnecting" : "connecting"
    );

    // A5: send the JWT in the Sec-WebSocket-Protocol header instead of on the
    // URL, so it doesn't leak into nginx access logs, browser history, or
    // Referer headers. Browsers can't set arbitrary headers on a WS open, but
    // each entry in the second arg of `new WebSocket(url, protocols)` is sent
    // as a comma-separated `Sec-WebSocket-Protocol`. The backend reads the
    // entry starting with `bearer.` to recover the JWT, then accepts with
    // subprotocol="flowin.v1" to complete the handshake.
    const ws = new WebSocket(url, [`bearer.${currentToken}`, "flowin.v1"]);
    wsRef.current = ws;

    ws.onopen = () => {
      retryCountRef.current = 0;
      setConnectionStatus("connected");
      setLastError(null);

      // Start client-side ping every 20s to keep the connection alive through
      // proxies and browsers that drop idle WebSocket connections.
      const pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "ping" }));
        } else {
          clearInterval(pingInterval);
        }
      }, 20000);
      // Store interval on the ws object so cleanup can clear it
      (ws as WebSocket & { _pingInterval?: ReturnType<typeof setInterval> })._pingInterval = pingInterval;
    };

    ws.onmessage = (event: MessageEvent) => {
      try {
        const parsed: StreamMessage = JSON.parse(event.data as string);
        // Ignore keepalive messages — they exist only to prevent connection drops
        if (parsed.type === "pipeline_heartbeat" || parsed.type === "pong") return;
        setLastMessage(parsed);
        onMessageRef.current?.(parsed);
      } catch {
        console.error(
          "[useHandoffSocket] Failed to parse incoming message:",
          event.data
        );
      }
    };

    ws.onerror = () => {
      // Error handling is done in onclose
    };

    ws.onclose = (event: CloseEvent) => {
      wsRef.current = null;

      if (event.code === JWT_EXPIRED_CODE) {
        // JWT expired — clear token and redirect to login
        clearToken();
        setConnectionStatus("disconnected");
        setLastError("Your session has expired. Please log in again.");
        if (typeof window !== "undefined") {
          window.location.href = "/login";
        }
        return;
      }

      if (intentionalCloseRef.current) {
        setConnectionStatus("disconnected");
        return;
      }

      // Attempt reconnection with exponential backoff — no retry limit.
      const delay = Math.min(BASE_DELAY_MS * Math.pow(2, retryCountRef.current), MAX_RETRY_DELAY_MS);
      retryCountRef.current += 1;
      setConnectionStatus("reconnecting");
      setLastError(`Connection lost. Reconnecting in ${Math.round(delay / 1000)}s… (attempt ${retryCountRef.current})`);
      retryTimeoutRef.current = setTimeout(() => {
        connect();
      }, delay);
    };
  }, [url, cleanup]);

  const send = useCallback((message: string): boolean => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(message);
      return true;
    }
    console.warn("[useHandoffSocket] Cannot send — socket not connected");
    return false;
  }, []);

  const reconnect = useCallback(() => {
    retryCountRef.current = 0;
    connect();
  }, [connect]);

  // Connect on mount when token is available, disconnect on unmount
  useEffect(() => {
    if (token) {
      connect();
    } else {
      cleanup();
      setConnectionStatus("disconnected");
    }

    return () => {
      intentionalCloseRef.current = true;
      cleanup();
    };
  }, [token, connect, cleanup]);

  return { send, connectionStatus, reconnect, lastMessage, lastError };
}
