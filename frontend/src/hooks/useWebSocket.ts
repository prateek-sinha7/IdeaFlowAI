"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { StreamMessage } from "@/types/index";
import { clearToken, getToken } from "@/lib/api";
import { ENV } from "@/lib/env";

export type ConnectionStatus =
  | "connecting"
  | "connected"
  | "disconnected"
  | "reconnecting"
  | "failed";

export interface UseWebSocketConfig {
  url?: string;
  token: string | null;
  onMessage?: (msg: StreamMessage) => void;
}

export interface UseWebSocketReturn {
  send: (message: string) => void;
  connectionStatus: ConnectionStatus;
  reconnect: () => void;
  lastMessage: StreamMessage | null;
  lastError: string | null;
}

const DEFAULT_WS_URL = ENV.WS_URL;
const BASE_DELAY_MS = 1000;
const MAX_RETRY_DELAY_MS = 30000; // cap backoff at 30s — never give up
const JWT_EXPIRED_CODE = 4001;

export function useWebSocket(config: UseWebSocketConfig): UseWebSocketReturn {
  const { url = DEFAULT_WS_URL, token, onMessage } = config;

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
    console.log("[useWebSocket] connect() called, token from localStorage:", currentToken ? "present" : "null");
    if (!currentToken) {
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
    //
    // We MUST offer two subprotocols: a credential one (`bearer.<jwt>`) and a
    // protocol-selector one (`flowin.v1`). The server echoes the selector,
    // never the credential. RFC 6455 + browser strict mode require the
    // server to echo a value that was in the client's offered list — if we
    // sent only `bearer.<jwt>`, echoing `flowin.v1` would be rejected as
    // "unsupported subprotocol". This is the same pattern used by k8s and
    // similar projects.
    const ws = new WebSocket(url, [`bearer.${currentToken}`, "flowin.v1"]);
    wsRef.current = ws;

    ws.onopen = () => {
      retryCountRef.current = 0;
      setConnectionStatus("connected");
      setLastError(null);

      // Start client-side ping every 20s to keep the connection alive through
      // proxies and browsers that drop idle WebSocket connections.
      // Prototype build tasks can take 2-4 min each with no messages flowing.
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
        // Malformed message — log and discard per requirement 19.4
        console.error(
          "[useWebSocket] Failed to parse incoming message:",
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
      // Long-running pipelines (2-6 hours) must survive extended network
      // outages. The delay is capped at 30s to avoid waiting too long.
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
    console.warn("[useWebSocket] Cannot send — WebSocket not connected");
    return false;
  }, []);

  const reconnect = useCallback(() => {
    retryCountRef.current = 0;
    connect();
  }, [connect]);

  // Connect on mount when token is available, disconnect on unmount
  useEffect(() => {
    console.log("[useWebSocket] Effect triggered, token:", token ? "present" : "null", "localStorage token:", typeof window !== "undefined" ? (localStorage.getItem("auth_token") ? "present" : "null") : "ssr");
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
