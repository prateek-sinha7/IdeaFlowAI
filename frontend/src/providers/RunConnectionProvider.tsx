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
import { authedFetch, getToken, getWorkflows } from "@/lib/api";
import { ENV } from "@/lib/env";
import { parseSseBlock } from "@/lib/sseFrame";
import {
  useRunStream,
  type RunConnectionPhase,
  type RunStreamMessage,
} from "@/hooks/useRunStream";

/**
 * AUTO_STREAM_STATUSES = the actively-EMITTING run statuses that always hold a
 * live SSE stream. This is the non-terminal set MINUS the two BACKGROUND parked
 * statuses (`clarifying`, `waiting_for_user`): a parked run emits no events while
 * it waits on the user, so auto-streaming it wins ZERO live updates while burning
 * one of the browser's ~6-connections-per-origin sockets (BUG-013). With ≥6
 * non-terminal runs those parked streams saturate the pool and the next request
 * to the origin — the reopen `GET /api/runs/{id}` or a launch `POST /api/runs` —
 * has no free socket and hangs forever into a silent idle screen.
 *
 * The remaining members mirror the backend lifecycle state machine
 * (`agents/execution_engine/state_machine.py`): `planning, analyzing,
 * generating, revising` (the emitting non-terminal states) PLUS `running`, the
 * DB default a run carries before the state machine's first transition. Each has
 * a `_PIPELINE_QUEUES` entry producing SSE events, so `refreshLiveRuns` attaches
 * it.
 *
 * The viewed/launched run stays streamed EVEN WHILE PARKED via the single sticky
 * `focusedRunId` unioned into `liveRunIds` below (so multi-round clarify + the
 * resume→build transition still stream live) — bounding net concurrent streams
 * to (active builds) + (1 focused run), well under the per-origin cap.
 */
const AUTO_STREAM_STATUSES = new Set([
  "running",
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
  /**
   * Release the sticky focus for a run that has completed (BUG-015). When `runId`
   * is the current focus it clears it and recomputes `liveRunIds`, unmounting the
   * finished run's `RunStreamConnection` so its stream does not reconnect + re-replay.
   * A non-focused id is a no-op.
   */
  detachRun: (runId: string) => void;
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
  detachRun: () => {},
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

  // BUG-013: liveRunIds = union(autoIds, focusedRunId). Both inputs live in refs
  // (not state) so `refreshLiveRuns`/`attachRun` stay dependency-free useCallbacks
  // — the union is materialized into the liveRunIds STATE by recomputeLiveRunIds.
  const autoIdsRef = useRef<string[]>([]);
  const focusedRunIdRef = useRef<string | null>(null);

  // Materialize union(autoIds, focus) into liveRunIds behind the set-diff identity
  // guard so an unchanged union keeps the SAME array identity (no child remount).
  // CRITICAL: the guard is applied to the UNION, not to autoIds alone — otherwise
  // the focused run would be dropped on every refresh that leaves autoIds intact.
  const recomputeLiveRunIds = useCallback(() => {
    const autoIds = autoIdsRef.current;
    const focus = focusedRunIdRef.current;
    const union = focus
      ? [...autoIds.filter((id) => id !== focus), focus]
      : autoIds;
    setLiveRunIds((prev) =>
      prev.length === union.length && prev.every((id, i) => id === union[i])
        ? prev
        : union,
    );
  }, []);

  // Server-derived reattach (D-14b): query the user's live runs and attach each
  // actively-emitting one (AUTO_STREAM_STATUSES); the viewed/launched run is kept
  // via the sticky focus (recomputeLiveRunIds unions it in).
  const refreshLiveRuns = useCallback(async () => {
    const t = getToken();
    setTokenState(t);
    if (!t) {
      autoIdsRef.current = [];
      focusedRunIdRef.current = null;
      setLiveRunIds([]);
      return;
    }
    try {
      const { runs } = await getWorkflows(t, { limit: 50 });
      // KAN-125 MULTI-TAB FIX: only auto-attach runs that this browser TAB
      // actually launched (restored from sessionStorage). A new tab has an
      // empty sessionStorage set and should not inherit another tab's running
      // workflows — those runs will have their SSE events blocked by the
      // isForeignFrame guard in handleWebSocketMessage anyway, but not creating
      // the SSE connections at all is cleaner and avoids wasting connections.
      // Exception: the focusedRunId (set when the user explicitly attaches a
      // run via attachRun) is always included regardless.
      let tabOwnedIds = new Set<string>();
      try {
        const raw = sessionStorage.getItem("tab_launched_run_ids");
        if (raw) {
          const ids = JSON.parse(raw) as string[];
          if (Array.isArray(ids)) tabOwnedIds = new Set<string>(ids);
        }
      } catch { /* ignore — non-fatal */ }

      autoIdsRef.current = runs
        .filter((r) =>
          AUTO_STREAM_STATUSES.has(r.status) &&
          // Only auto-attach if this tab owns the run (has launched it previously)
          // OR if the set is empty (e.g. a first-ever load where the active_pipeline_run_id
          // session key is set — handled separately below).
          (tabOwnedIds.size === 0 ? false : tabOwnedIds.has(r.id))
        )
        .map((r) => r.id);
      recomputeLiveRunIds();
    } catch {
      /* keep the prior attach set on a transient query failure */
    }
  }, [recomputeLiveRunIds]);

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

  // W1/R4 + BUG-013 — imperative single-run attach. Sets the SINGLE sticky focus
  // (a new focus REPLACES the prior, so opening run B drops run A's parked stream —
  // no accumulation) and re-materializes the union. A still-building prior run is
  // retained regardless of focus because it stays in autoIdsRef via
  // AUTO_STREAM_STATUSES. Idempotent for an already-focused id (the identity guard
  // in recomputeLiveRunIds keeps the same array → no remount).
  const attachRun = useCallback(
    (runId: string) => {
      if (!runId) return;
      focusedRunIdRef.current = runId;
      recomputeLiveRunIds();
    },
    [recomputeLiveRunIds],
  );

  // BUG-015 — release the sticky focus for a completed run so its dead
  // RunStreamConnection unmounts (no reconnect, no ~14k re-replay). Clears the
  // focus ONLY when it matches (a non-focused id is a no-op — a still-building
  // run stays in autoIdsRef regardless), then re-materializes the union.
  const detachRun = useCallback(
    (runId: string) => {
      if (focusedRunIdRef.current === runId) {
        focusedRunIdRef.current = null;
        recomputeLiveRunIds();
      }
    },
    [recomputeLiveRunIds],
  );

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
      // FR-015: authedFetch, not bare fetch — this POST can't use request()
      // (it content-negotiates an SSE body below), so it needs the shared
      // 401 -> handleSessionExpiry() guard explicitly.
      const res = await authedFetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${t}`,
        },
        body: JSON.stringify(payload),
      });
      // A per-run message carries no new run to attach. m0o: content-negotiate —
      // the fresh-Concierge /messages response streams as `text/event-stream`
      // (Plan 01); drain its body and dispatch each parsed frame through the
      // EXISTING subscriber fan-out (so useRunChat's chat_reply_chunk case renders
      // the growing bubble on BOTH live and completed runs, no SSE re-attach).
      // GENERIC (SC-001): the branch is on the content-type header, NEVER on a
      // `concierge` literal — every other /messages response stays JSON and takes
      // the unchanged `return null` path below.
      if (runId) {
        // D2 (KAN-139): check res.ok BEFORE reading the body. A 429/404/409/5xx
        // response previously returned null silently, leaving the chat message as
        // an orphan optimistic bubble forever with no error shown. Throw ApiError
        // on any non-ok response so the caller can surface it to the user.
        if (!res.ok) {
          let detail: unknown;
          try {
            const body = (await res.json()) as Record<string, unknown>;
            detail = body.detail ?? body;
          } catch {
            detail = `HTTP ${res.status}`;
          }
          throw new Error(
            typeof detail === "string" ? detail : JSON.stringify(detail),
          );
        }
        const contentType = res.headers.get("content-type") ?? "";
        if (res.body && contentType.includes("text/event-stream")) {
          // Drain with the SAME reader-loop shape as useRunStream (split on
          // "\n\n", CRLF-normalized, parseSseBlock each block, drop keepalives,
          // flush the trailing block). The streamed frames reach the transcript
          // through the SAME fanout → subscribersRef → useRunChat.handleFrame seam
          // SSE frames already use (no third streaming path, INV-12).
          const drain = (block: string) => {
            const frame = parseSseBlock(block);
            if (!frame) return;
            if (frame.type === "pipeline_heartbeat" || frame.type === "pong") {
              return; // keepalive — never reaches the reducer (WS parity)
            }
            // Stamp the source run so these frames are run-scopable downstream,
            // exactly like the per-run SSE stream frames (useRunStream stamps its
            // own). `runId` is non-null in this branch.
            fanout({ ...frame, _sourceRunId: runId });
          };
          const reader = res.body.getReader();
          const decoder = new TextDecoder();
          let buf = "";
          for (;;) {
            const { value, done } = await reader.read();
            if (done) break;
            buf += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
            let idx: number;
            while ((idx = buf.indexOf("\n\n")) !== -1) {
              const rawBlock = buf.slice(0, idx);
              buf = buf.slice(idx + 2);
              drain(rawBlock);
            }
          }
          // Flush any trailing block (server closed without a terminal blank line).
          if (buf.trim()) drain(buf);
          // SSE path: no run_id to return (frames already dispatched via fanout).
          return null;
        }
        // Non-SSE /messages response (e.g. confirm-proposal JSON). Parse it to
        // extract the revision_run_id when a concierge-confirmed revision launched
        // a child run — this lets the caller attachRun + switchViewTo the new run.
        try {
          const body = (await res.json()) as Record<string, unknown> | null;
          const proposal = body?.proposal as Record<string, unknown> | undefined;
          const revisionRunId = proposal?.revision_run_id as string | undefined;
          return revisionRunId ?? null;
        } catch {
          return null;
        }
      }
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
    [fanout],
  );

  const phase = useMemo(
    () => aggregatePhase(Object.values(phases)),
    [phases],
  );

  const value = useMemo<RunConnectionContextValue>(
    () => ({ enabled, phase, liveRunIds, reattach, attachRun, detachRun, subscribe, sendCommand }),
    [enabled, phase, liveRunIds, reattach, attachRun, detachRun, subscribe, sendCommand],
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
              // KAN-125 FIX: inject _sourceRunId so handleWebSocketMessage can
              // route frames without pipeline_run_id (agent_start/agent_chunk/
              // agent_complete etc.) to the correct pipelineState reducer.
              onMessage={(msg) => fanout({ ...msg, _sourceRunId: runId })}
              onPhase={onPhase}
            />
          ))
        : null}
      {children}
    </RunConnectionContext.Provider>
  );
}
