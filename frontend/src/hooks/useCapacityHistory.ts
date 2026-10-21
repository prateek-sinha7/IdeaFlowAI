"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { adminGetCapacityHistory } from "@/lib/api";
import type { AdminCapacityHistory, CapacityHistoryRange } from "@/lib/api";

/**
 * useCapacityHistory — fetches `GET /api/admin/capacity/history` for the Machines
 * tab's charts (ADR-0056), separate from `useCapacityMatrix`'s 15s table poll.
 *
 * - Refetches whenever the instance, range or period changes, then every 60s while
 *   the tab is visible (the backend caches for 60s, so polling faster buys
 *   nothing) and immediately on return to a visible tab.
 * - `refresh()` forces a fetch on demand and sets `refreshing` until it settles.
 * - A failed background refresh keeps the last good charts and reports
 *   `refreshError` instead of blanking them; only a failed first load for the
 *   current selection is an `error` state.
 *
 * "Loading" is derived, not stored: the state is `loading` whenever the last
 * settled result belongs to a different instance/range/period than the one asked
 * for now, so a selection change can never show the previous instance's charts.
 */
export type CapacityHistoryState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; message: string }
  | {
      status: "ready";
      history: AdminCapacityHistory;
      refreshing: boolean;
      refreshError: string | null;
    };

export interface UseCapacityHistoryResult {
  state: CapacityHistoryState;
  refresh: () => void;
}

export const HISTORY_REFRESH_INTERVAL_MS = 60_000;

type Settled =
  | { key: string; ok: true; history: AdminCapacityHistory; refreshError: string | null }
  | { key: string; ok: false; message: string };

function selectionKey(
  instanceId: string,
  range: CapacityHistoryRange,
  periodSeconds: number | null,
): string {
  return `${instanceId}|${range}|${periodSeconds ?? "auto"}`;
}

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : "Failed to load metric history";
}

/**
 * @param token Bearer token. Nothing is fetched while it is falsy.
 * @param instanceId Instance from the capacity matrix; `null` = nothing selected.
 * @param range Time range to chart.
 * @param periodSeconds Bucket size, or `null` for the range default.
 */
export function useCapacityHistory(
  token: string | null,
  instanceId: string | null,
  range: CapacityHistoryRange,
  periodSeconds: number | null,
): UseCapacityHistoryResult {
  const key = token && instanceId ? selectionKey(instanceId, range, periodSeconds) : null;
  const [settled, setSettled] = useState<Settled | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  // Out-of-order guard: only the newest request may write state.
  const requestIdRef = useRef(0);

  const load = useCallback(async () => {
    if (!token || !instanceId || key === null) return;
    const requestId = ++requestIdRef.current;
    try {
      const history = await adminGetCapacityHistory(token, instanceId, range, periodSeconds);
      if (requestId !== requestIdRef.current) return;
      setSettled({ key, ok: true, history, refreshError: null });
    } catch (err) {
      if (requestId !== requestIdRef.current) return;
      const message = errorMessage(err);
      setSettled((prev) =>
        prev && prev.key === key && prev.ok
          ? { ...prev, refreshError: message }
          : { key, ok: false, message },
      );
    } finally {
      if (requestId === requestIdRef.current) setRefreshing(false);
    }
  }, [token, instanceId, range, periodSeconds, key]);

  useEffect(() => {
    if (key === null) return;

    // Same accepted shape as useCapacityMatrix: `load` only sets state after its
    // `await`, in a later microtask, never synchronously in this effect body —
    // fetching when the selection changes is what this hook exists for.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();

    let intervalId: ReturnType<typeof setInterval> | null = null;
    const startInterval = () => {
      if (intervalId !== null) return;
      intervalId = setInterval(() => {
        void load();
      }, HISTORY_REFRESH_INTERVAL_MS);
    };
    const stopInterval = () => {
      if (intervalId === null) return;
      clearInterval(intervalId);
      intervalId = null;
    };
    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        void load();
        startInterval();
      } else {
        stopInterval();
      }
    };

    if (document.visibilityState === "visible") startInterval();
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      stopInterval();
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [key, load]);

  const refresh = useCallback(() => {
    if (key === null) return;
    setRefreshing(true);
    void load();
  }, [key, load]);

  let state: CapacityHistoryState;
  if (key === null) {
    state = { status: "idle" };
  } else if (settled === null || settled.key !== key) {
    state = { status: "loading" };
  } else if (!settled.ok) {
    state = { status: "error", message: settled.message };
  } else {
    state = {
      status: "ready",
      history: settled.history,
      refreshing,
      refreshError: settled.refreshError,
    };
  }
  return { state, refresh };
}

export default useCapacityHistory;
