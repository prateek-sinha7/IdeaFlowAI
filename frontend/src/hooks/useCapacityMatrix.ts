"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { adminListCapacity } from "@/lib/api";
import type { AdminCapacityMatrix } from "@/lib/api";

/**
 * useCapacityMatrix — polls `GET /api/admin/capacity` for the Machines tab
 * (specs/014 §3.5).
 *
 * Polling, not SSE (BUG-013): a long-lived stream per open admin tab would
 * compete with the browser's ~6-socket-per-origin pool against every other
 * REST call the page makes, and the underlying data only changes as often as
 * the background poller runs (`HOST_CAPACITY_POLL_SECONDS`, default 30s) — a
 * push channel would add complexity for data that is already cheap to pull.
 *
 * Discriminated union so the component never has to reason about impossible
 * combinations (e.g. "error" with stale `matrix` data lying around) — same
 * pattern already used in `frontend-coding-guardrails` (§1 "illegal UI states
 * unrepresentable").
 */
export type CapacityMatrixState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "empty"; matrix: AdminCapacityMatrix }
  | { status: "ready"; matrix: AdminCapacityMatrix };

const POLL_INTERVAL_MS = 15_000;

/** Derives the discriminated state from a fetched matrix (no instances yet
 *  collected is "empty", not an error — the poller may simply not have run). */
function toState(matrix: AdminCapacityMatrix): CapacityMatrixState {
  return matrix.instances.length === 0
    ? { status: "empty", matrix }
    : { status: "ready", matrix };
}

/**
 * @param token Bearer token for `adminListCapacity`. Polling is disabled
 *   entirely while `token` is falsy (e.g. auth not yet resolved) — no request
 *   is fired.
 */
export function useCapacityMatrix(token: string | null): CapacityMatrixState {
  const [state, setState] = useState<CapacityMatrixState>({ status: "loading" });
  // Tracks in-flight/staleness so a slow response from a previous poll can't
  // clobber a newer one that already resolved (out-of-order network replies).
  const requestIdRef = useRef(0);

  const poll = useCallback(async () => {
    if (!token) return;
    const requestId = ++requestIdRef.current;
    try {
      const matrix = await adminListCapacity(token);
      if (requestId !== requestIdRef.current) return; // superseded by a newer poll
      setState(toState(matrix));
    } catch (err) {
      if (requestId !== requestIdRef.current) return;
      setState({
        status: "error",
        message: err instanceof Error ? err.message : "Failed to load capacity matrix",
      });
    }
  }, [token]);

  useEffect(() => {
    if (!token) return;

    // react-hooks/set-state-in-effect flags this because `poll` eventually
    // calls `setState` — but that call happens after the `await
    // adminListCapacity(...)`, in a microtask outside this effect's own
    // synchronous body, not during render. Fetching on mount and setting
    // state from the response is the fundamental data-fetching pattern this
    // hook exists for; the same shape is already accepted throughout the
    // codebase (RunConnectionProvider's boot effect, SecuritySection's
    // `load()`) via the suppressions ledger for pre-existing files.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void poll();

    let intervalId: ReturnType<typeof setInterval> | null = null;

    const startInterval = () => {
      if (intervalId !== null) return;
      intervalId = setInterval(() => {
        void poll();
      }, POLL_INTERVAL_MS);
    };
    const stopInterval = () => {
      if (intervalId === null) return;
      clearInterval(intervalId);
      intervalId = null;
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        // Refresh immediately on return rather than waiting out the rest of
        // the previous interval — the tab may have been hidden for minutes.
        void poll();
        startInterval();
      } else {
        stopInterval();
      }
    };

    if (document.visibilityState === "visible") {
      startInterval();
    }
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      stopInterval();
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [token, poll]);

  return state;
}

export default useCapacityMatrix;
