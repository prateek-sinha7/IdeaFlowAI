"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { connectorsApi } from "@/store/api/connectors";
import { saveErrorMessage } from "@/lib/saveError";
import {
  AUTHORIZATION_POLL_MS,
  AUTHORIZATION_TTL_MS,
  CONNECTORS_CHANNEL,
  POPUP_FEATURES,
  isHttpsUrl,
  isOAuthCompleteMessage,
  popupNameFor,
  type CallbackReason,
} from "@/lib/connectorPopup";
import type {
  ConnectorStatus,
  ConnectorSummary,
  ProviderRevocation,
} from "@/types/connectors";

export type ConnectorPending =
  | "idle"
  | { kind: "authorizing"; deadline: number }
  | { kind: "disconnecting" };

/** The result banner the page shows (aria-live). Never contains a token or code. */
export type ConnectorNotice =
  | { kind: "connected"; connector: string }
  | { kind: "cancelled"; connector: string }
  | { kind: "timed_out"; connector: string }
  | { kind: "disconnected"; connector: string; providerRevocation: ProviderRevocation }
  | { kind: "error"; connector: string | null; reason: CallbackReason | null; message: string | null }
  | { kind: "popup_blocked"; connector: string; authorizationUrl: string };

export interface UseConnectorAuthorizationOptions {
  /** `useConnectors().refresh`: resolves with the fresh list, or null. */
  refresh: () => Promise<ConnectorSummary[] | null>;
  /** Clock, injectable for tests. */
  now?: () => number;
}

export interface UseConnectorAuthorization {
  pending: Readonly<Record<string, ConnectorPending>>;
  notice: ConnectorNotice | null;
  clearNotice: () => void;
  /** Open the sign-in popup for `key`. Call it from the click handler. */
  start: (key: string) => Promise<void>;
  /** Stop waiting for `key` and close its popup. */
  cancel: (key: string) => void;
  /** Revoke at the provider and delete the local connection. Returns null on failure. */
  disconnect: (key: string) => Promise<ProviderRevocation | null>;
  /** After a blocked popup: sign in on this tab instead. */
  continueInThisTab: () => void;
}

interface Attempt {
  baselineStatus: ConnectorStatus | undefined;
  baselineConnectedAt: string | null;
  deadline: number;
  popup: Window | null;
}

function messageOf(err: unknown, fallback: string): string {
  return saveErrorMessage(err, fallback);
}

function closeQuietly(popup: Window | null): void {
  try {
    popup?.close();
  } catch {
    /* a cross-origin popup can refuse; the user can close it */
  }
}

/**
 * The popup sign-in flow for Connectors.
 *
 * 1. `start` opens the window synchronously (so popup blockers allow it) and
 *    drops `opener`, then asks the server for the authorization URL and
 *    navigates the popup only when that URL is https.
 * 2. While a sign-in is pending it re-reads the list every 2 s. It finishes
 *    when the connector becomes connected (or its connection is replaced), a
 *    BroadcastChannel message for the key arrives, the user cancels, or the
 *    10-minute state deadline passes. `popup.closed` is deliberately not used:
 *    a provider's Cross-Origin-Opener-Policy makes it read true while the
 *    window is still open.
 * 3. A blocked popup produces a banner with a "continue in this tab" action.
 */
export function useConnectorAuthorization({
  refresh,
  now = Date.now,
}: UseConnectorAuthorizationOptions): UseConnectorAuthorization {
  const [pending, setPending] = useState<Record<string, ConnectorPending>>({});
  const [notice, setNotice] = useState<ConnectorNotice | null>(null);
  const attemptsRef = useRef(new Map<string, Attempt>());
  const polling = useRef(false);
  const refreshRef = useRef(refresh);
  const nowRef = useRef(now);
  useEffect(() => {
    refreshRef.current = refresh;
    nowRef.current = now;
  }, [refresh, now]);

  const setPendingFor = useCallback((key: string, value: ConnectorPending) => {
    setPending((prev) => {
      const next = { ...prev };
      if (value === "idle") delete next[key];
      else next[key] = value;
      return next;
    });
  }, []);

  const finish = useCallback(
    (key: string, next: ConnectorNotice | null) => {
      const attempt = attemptsRef.current.get(key);
      attemptsRef.current.delete(key);
      closeQuietly(attempt?.popup ?? null);
      setPendingFor(key, "idle");
      if (next) setNotice(next);
    },
    [setPendingFor],
  );

  const hasAuthorizing = Object.values(pending).some(
    (p) => p !== "idle" && p.kind === "authorizing",
  );

  // Poll the list while a sign-in is pending.
  useEffect(() => {
    if (!hasAuthorizing) return;
    const tick = async () => {
      if (polling.current) return;
      polling.current = true;
      try {
        const current = nowRef.current();
        for (const [key, attempt] of [...attemptsRef.current]) {
          if (current >= attempt.deadline) finish(key, { kind: "timed_out", connector: key });
        }
        if (attemptsRef.current.size === 0) return;
        const connectors = await refreshRef.current();
        if (!connectors) return;
        for (const [key, attempt] of [...attemptsRef.current]) {
          const summary = connectors.find((c) => c.key === key);
          if (
            summary?.status === "connected" &&
            (attempt.baselineStatus !== "connected" ||
              summary.connected_at !== attempt.baselineConnectedAt)
          ) {
            finish(key, { kind: "connected", connector: key });
          }
        }
      } finally {
        polling.current = false;
      }
    };
    const id = setInterval(() => void tick(), AUTHORIZATION_POLL_MS);
    return () => clearInterval(id);
  }, [hasAuthorizing, finish]);

  // The landing page posts the result here; it is a hint, so re-read the list.
  useEffect(() => {
    if (typeof BroadcastChannel === "undefined") return;
    const channel = new BroadcastChannel(CONNECTORS_CHANNEL);
    channel.onmessage = (event: MessageEvent<unknown>) => {
      const message = event.data;
      if (!isOAuthCompleteMessage(message)) return;
      if (!attemptsRef.current.has(message.connector)) return;
      if (message.result === "error") {
        finish(message.connector, {
          kind: "error",
          connector: message.connector,
          reason: message.reason,
          message: null,
        });
        void refreshRef.current();
        return;
      }
      void refreshRef.current().then(() => {
        // The poll may have finished this attempt while the refresh was in flight.
        if (!attemptsRef.current.has(message.connector)) return;
        finish(message.connector, { kind: "connected", connector: message.connector });
      });
    };
    return () => channel.close();
  }, [finish]);

  const start = useCallback(
    async (key: string) => {
      if (attemptsRef.current.has(key)) return;
      // Synchronously, inside the click handler, or the popup blocker refuses it.
      const popup = window.open("", popupNameFor(key), POPUP_FEATURES);
      if (popup) popup.opener = null;
      setNotice(null);
      try {
        // The list read before sign-in is the baseline: a reconnect starts from
        // "connected" or "expired", so a status of "connected" alone proves nothing.
        const [{ authorization_url, expires_at }, before] = await Promise.all([
          connectorsApi.authorize(key),
          refreshRef.current().then((list) => list?.find((c) => c.key === key)),
        ]);
        if (!isHttpsUrl(authorization_url)) {
          closeQuietly(popup);
          setNotice({
            kind: "error",
            connector: key,
            reason: null,
            message: "The sign-in address was not secure, so it was not opened.",
          });
          return;
        }
        if (!popup) {
          setNotice({ kind: "popup_blocked", connector: key, authorizationUrl: authorization_url });
          return;
        }
        popup.location.href = authorization_url;
        const parsedExpiry = Date.parse(expires_at);
        const startedAt = nowRef.current();
        const deadline = Number.isNaN(parsedExpiry)
          ? startedAt + AUTHORIZATION_TTL_MS
          : Math.min(parsedExpiry, startedAt + AUTHORIZATION_TTL_MS);
        attemptsRef.current.set(key, {
          baselineStatus: before?.status,
          baselineConnectedAt: before?.connected_at ?? null,
          deadline,
          popup,
        });
        setPendingFor(key, { kind: "authorizing", deadline });
      } catch (err) {
        closeQuietly(popup);
        setNotice({
          kind: "error",
          connector: key,
          reason: null,
          message: messageOf(err, "Could not start the sign-in."),
        });
      }
    },
    [setPendingFor],
  );

  const cancel = useCallback(
    (key: string) => {
      if (!attemptsRef.current.has(key)) return;
      finish(key, { kind: "cancelled", connector: key });
    },
    [finish],
  );

  const disconnect = useCallback(
    async (key: string): Promise<ProviderRevocation | null> => {
      setNotice(null);
      setPendingFor(key, { kind: "disconnecting" });
      try {
        const { provider_revocation } = await connectorsApi.disconnect(key);
        setNotice({ kind: "disconnected", connector: key, providerRevocation: provider_revocation });
        await refreshRef.current();
        return provider_revocation;
      } catch (err) {
        setNotice({
          kind: "error",
          connector: key,
          reason: null,
          message: messageOf(err, "Could not disconnect."),
        });
        return null;
      } finally {
        setPendingFor(key, "idle");
      }
    },
    [setPendingFor],
  );

  const continueInThisTab = useCallback(() => {
    if (notice?.kind !== "popup_blocked") return;
    if (!isHttpsUrl(notice.authorizationUrl)) return;
    window.location.assign(notice.authorizationUrl);
  }, [notice]);

  const clearNotice = useCallback(() => setNotice(null), []);

  return { pending, notice, clearNotice, start, cancel, disconnect, continueInThisTab };
}

export default useConnectorAuthorization;
