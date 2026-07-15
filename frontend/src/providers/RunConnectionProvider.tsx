"use client";

/**
 * RunConnectionProvider — app-level ownership of the SSE run connection (Phase
 * 29, CHAT-07, D-14 a/b/c/e). SSE is the sole, unconditional run transport
 * (44-06 hard cutoff): this provider always attaches. There is no transport flag
 * and no legacy WebSocket ownership path anymore.
 *
 * Why app-level (D-14a): today the connection is owned inside
 * `dashboard/page.tsx`, so navigating away from the dashboard (wizard / handoff
 * / fullscreen) or a soft route change tears the transport down. Mounted ABOVE
 * the router, this provider keeps the per-run streams alive across route
 * changes — its connection children live in the provider subtree, not the page.
 *
 * Server-derived reattach (D-14b): on boot/reconnect it QUERIES the user's live
 * runs (`GET /api/runs`, filtered to non-terminal) and attaches a stream per run
 * — it never trusts `sessionStorage` alone to decide what is live. The persisted
 * per-run cursor (D-14c) is only a resume hint for `Last-Event-ID`; worst case
 * is a full replay, made correct by the downstream `event_id` dedup.
 *
 * State machine (D-14d) is surfaced via `phase`; reconnect fires on
 * `visibilitychange` / `online` (D-14e).
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { getToken, getWorkflows } from "@/lib/api";
import { ENV } from "@/lib/env";
import {
  useRunStream,
  type RunConnectionPhase,
  type RunStreamMessage,
} from "@/hooks/useRunStream";

/**
 * Non-terminal run statuses = the runs that still have a live stream worth
 * attaching. Terminal runs (completed/failed/cancelled) are replay-only and are
 * not attached on boot.
 *
 * This set must mirror the backend lifecycle state machine
 * (`agents/execution_engine/state_machine.py`): the six non-terminal states it
 * drives — `clarifying, waiting_for_user, planning, analyzing, generating,
 * revising` (VALID_STATES − TERMINAL_STATES) — PLUS `running`, the DB default a
 * run carries before the state machine's first transition. A run mid-clarify,
 * mid-plan, or mid-generation is still live: it has a `_PIPELINE_QUEUES` entry
 * producing SSE events, so `refreshLiveRuns` must attach it. Omitting these
 * (the pre-44 set was only `{running, revising}`) meant a run opened from
 * history — or the page reloaded — while `generating` etc. never re-attached
 * its stream and showed the empty "Pipeline trace" placeholder (DEF-44-12-3;
 * the WS transport masked this because it reconnected by run-id, status-agnostic).
 */
const NON_TERMINAL_STATUSES = new Set([
  "running",
  "clarifying",
  "waiting_for_user",
  "planning",
  "analyzing",
  "generating",
  "revising",
]);

export interface RunConnectionContextValue {
  /**
   * Whether the SSE transport is active. Always true under the provider (SSE is
   * the sole transport, 44-06); the no-provider inert default is false.
   */
  enabled: boolean;
  /** Aggregate connection phase across all attached runs (D-14d). */
  phase: RunConnectionPhase;
  /** The server-derived set of live run ids currently attached (D-14b). */
  liveRunIds: string[];
  /** Force a server-derived reattach (re-query live runs + re-attach). */
  reattach: () => void;
  /**
   * Imperatively attach a single run's SSE stream RIGHT NOW (W1/R4 launch->attach)
   * — used after a launch (`POST /api/runs`) so the fresh run streams live without
   * waiting for the next `refreshLiveRuns` poll. Idempotent: attaching an id that
   * is already live is a no-op (the `liveRunIds` identity does not change), so it
   * never remounts an existing `RunStreamConnection`.
   */
  attachRun: (runId: string) => void;
  /** Subscribe to every frame from every attached run; returns an unsubscribe. */
  subscribe: (fn: (msg: RunStreamMessage) => void) => () => void;
  /**
   * Send a command up-channel over REST (the SSE transport's up-channel). When
   * `runId` is null the command creates a run (`POST /api/runs`) and resolves to
   * the created `run_id` (so the caller can `attachRun` it — W1/R4); otherwise it
   * posts to that run (`POST /api/runs/{id}/messages`) and resolves to null.
   */
  sendCommand: (runId: string | null, payload: Record<string, unknown>) => Promise<string | null>;
}

/**
 * Default (no-provider) value so `useRunConnection()` is always safe to call —
 * a consumer rendered outside the provider (e.g. the dashboard when the flag is
 * OFF) gets an inert, disabled connection and falls back to its WS path.
 */
const DEFAULT_VALUE: RunConnectionContextValue = {
  enabled: false,
  phase: "idle",
  liveRunIds: [],
  reattach: () => {},
  attachRun: () => {},
  subscribe: () => () => {},
  sendCommand: async () => null,
};

const RunConnectionContext = createContext<RunConnectionContextValue>(DEFAULT_VALUE);

/** Consume the app-level run connection. Safe outside the provider (inert). */
export function useRunConnection(): RunConnectionContextValue {
  return useContext(RunConnectionContext);
}

// ── per-run cursor persistence (D-14c) ────────────────────────────────────────
function cursorKey(runId: string): string {
  return `run_cursor:${runId}`;
}
function readCursor(runId: string): number | null {
  try {
    const v = sessionStorage.getItem(cursorKey(runId));
    if (v == null || v === "") return null;
    const n = Number(v);
    return Number.isNaN(n) ? null : n;
  } catch {
    return null;
  }
}
function writeCursor(runId: string, seq: number): void {
  try {
    sessionStorage.setItem(cursorKey(runId), String(seq));
  } catch {
    /* non-fatal (private mode / quota) */
  }
}

/**
 * Aggregate the per-run phases into one connection phase (D-14d): live if any
 * run is live, else the "busiest" transitional phase, else idle.
 */
function aggregatePhase(
  phases: RunConnectionPhase[],
): RunConnectionPhase {
  if (phases.length === 0) return "idle";
  if (phases.includes("live")) return "live";
  if (phases.includes("replaying")) return "replaying";
  if (phases.includes("connecting")) return "connecting";
  if (phases.includes("reconnecting")) return "reconnecting";
  if (phases.includes("failed")) return "failed";
  if (phases.includes("disconnected")) return "disconnected";
  return "idle";
}

/**
 * One attached run stream. A child component (not an inline hook) so the
 * provider can attach N runs by `.map()` while still calling `useRunStream`
 * exactly once per run (Rules of Hooks). It reports its phase up and persists
 * its resume cursor (D-14c).
 */
function RunStreamConnection({
  runId,
  token,
  epoch,
  onMessage,
  onPhase,
}: {
  runId: string;
  token: string | null;
  epoch: number;
  onMessage: (msg: RunStreamMessage) => void;
  onPhase: (runId: string, phase: RunConnectionPhase) => void;
}): null {
  const { phase, reconnect } = useRunStream({
    runId,
    token,
    enabled: true,
    afterSeq: readCursor(runId),
    onMessage,
    onCursor: (seq) => writeCursor(runId, seq),
  });

  // D-14e: a wake/online bump (epoch change) forces an immediate reconnect.
  const epochRef = useRef(epoch);
  useEffect(() => {
    if (epochRef.current !== epoch) {
      epochRef.current = epoch;
      reconnect();
    }
  }, [epoch, reconnect]);

  useEffect(() => {
    onPhase(runId, phase);
  }, [runId, phase, onPhase]);

  return null;
}

export interface RunConnectionProviderProps {
  children: ReactNode;
}

export function RunConnectionProvider({
  children,
}: RunConnectionProviderProps) {
  // SSE is the sole run transport (44-06) — always enabled under the provider.
  const enabled = true;
  const [token, setTokenState] = useState<string | null>(null);
  const [liveRunIds, setLiveRunIds] = useState<string[]>([]);
  const [phases, setPhases] = useState<Record<string, RunConnectionPhase>>({});
  const [epoch, setEpoch] = useState(0);
  const subscribersRef = useRef<Set<(m: RunStreamMessage) => void>>(new Set());

  // Server-derived reattach (D-14b): query the user's live runs and attach each.
  const refreshLiveRuns = useCallback(async () => {
    const t = getToken();
    setTokenState(t);
    if (!t) {
      setLiveRunIds([]);
      return;
    }
    try {
      const runs = await getWorkflows(t, { limit: 50 });
      const ids = runs
        .filter((r) => NON_TERMINAL_STATUSES.has(r.status))
        .map((r) => r.id);
      // Only replace when the set actually changed, to avoid remounting the
      // connection children (which would drop + re-attach unnecessarily).
      setLiveRunIds((prev) =>
        prev.length === ids.length && prev.every((id, i) => id === ids[i])
          ? prev
          : ids,
      );
    } catch {
      /* keep the prior attach set on a transient query failure */
    }
  }, []);

  // Boot: resolve the token client-side and do the first server-derived attach.
  useEffect(() => {
    setTokenState(getToken());
    void refreshLiveRuns();
  }, [refreshLiveRuns]);

  // D-14e: reconnect on tab focus / network online. A wake re-queries live runs
  // (the set may have changed while backgrounded) AND bumps the epoch so already
  // attached streams reconnect immediately from their cursor.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const onWake = () => {
      if (document.visibilityState === "visible") {
        setEpoch((e) => e + 1);
        void refreshLiveRuns();
      }
    };
    const onOnline = () => {
      setEpoch((e) => e + 1);
      void refreshLiveRuns();
    };
    document.addEventListener("visibilitychange", onWake);
    window.addEventListener("online", onOnline);
    return () => {
      document.removeEventListener("visibilitychange", onWake);
      window.removeEventListener("online", onOnline);
    };
  }, [refreshLiveRuns]);

  const fanout = useCallback((msg: RunStreamMessage) => {
    subscribersRef.current.forEach((fn) => {
      try {
        fn(msg);
      } catch {
        /* a bad subscriber must not break the fan-out */
      }
    });
  }, []);

  const onPhase = useCallback((runId: string, p: RunConnectionPhase) => {
    setPhases((prev) => (prev[runId] === p ? prev : { ...prev, [runId]: p }));
  }, []);

  const subscribe = useCallback((fn: (m: RunStreamMessage) => void) => {
    subscribersRef.current.add(fn);
    return () => {
      subscribersRef.current.delete(fn);
    };
  }, []);

  const reattach = useCallback(() => {
    setEpoch((e) => e + 1);
    void refreshLiveRuns();
  }, [refreshLiveRuns]);

  // W1/R4 — imperative single-run attach. Mirrors refreshLiveRuns's set-diff so a
  // repeat attach of an already-live id keeps the SAME `liveRunIds` identity (no
  // remount of the existing RunStreamConnection). A brand-new id is appended,
  // mounting exactly one new stream.
  const attachRun = useCallback((runId: string) => {
    if (!runId) return;
    setLiveRunIds((prev) => (prev.includes(runId) ? prev : [...prev, runId]));
  }, []);

  const sendCommand = useCallback(
    async (
      runId: string | null,
      payload: Record<string, unknown>,
    ): Promise<string | null> => {
      const t = getToken();
      if (!t) return null;
      const url = runId
        ? `${ENV.API_URL}/api/runs/${runId}/messages`
        : `${ENV.API_URL}/api/runs`;
      const res = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${t}`,
        },
        body: JSON.stringify(payload),
      });
      // A per-run message carries no new run to attach.
      if (runId) return null;
      // Launch (POST /api/runs): parse the created run_id so the caller can
      // attachRun it (W1/R4). A non-2xx create yields no id to attach.
      if (!res.ok) return null;
      try {
        const body = (await res.json()) as
          | { run_id?: string; id?: string }
          | null;
        return body?.run_id ?? body?.id ?? null;
      } catch {
        return null;
      }
    },
    [],
  );

  const phase = useMemo(
    () => aggregatePhase(Object.values(phases)),
    [phases],
  );

  const value = useMemo<RunConnectionContextValue>(
    () => ({ enabled, phase, liveRunIds, reattach, attachRun, subscribe, sendCommand }),
    [enabled, phase, liveRunIds, reattach, attachRun, subscribe, sendCommand],
  );

  return (
    <RunConnectionContext.Provider value={value}>
      {token
        ? liveRunIds.map((runId) => (
            <RunStreamConnection
              key={runId}
              runId={runId}
              token={token}
              epoch={epoch}
              onMessage={fanout}
              onPhase={onPhase}
            />
          ))
        : null}
      {children}
    </RunConnectionContext.Provider>
  );
}
