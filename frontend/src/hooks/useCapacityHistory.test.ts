/**
 * ADR-0056 — useCapacityHistory fetch/refresh hook.
 *
 * Mocks `@/lib/api`'s `adminGetCapacityHistory` (the hook's only collaborator)
 * and drives the 60s refresh + visibility pause with fake timers, following
 * useCapacityMatrix.test.ts.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { HISTORY_REFRESH_INTERVAL_MS, useCapacityHistory } from "./useCapacityHistory";
import type { AdminCapacityHistory, CapacityHistoryRange } from "@/lib/api";

async function flushMicrotasks() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });
}

const { adminGetCapacityHistory } = vi.hoisted(() => ({
  adminGetCapacityHistory: vi.fn(),
}));
vi.mock("@/lib/api", () => ({ adminGetCapacityHistory }));

function buildHistory(instanceId = "i-a", range: CapacityHistoryRange = "3h"): AdminCapacityHistory {
  return {
    instance_id: instanceId,
    range,
    period_seconds: 60,
    allowed_periods: [60, 300, 900, 3600],
    start: "2026-10-21T07:00:00Z",
    end: "2026-10-21T10:00:00Z",
    fetched_at: "2026-10-21T10:00:05Z",
    cached: false,
    cpu_threshold_percent: 75,
    mem_threshold_percent: 75,
    series: [],
  };
}

function setVisibility(value: DocumentVisibilityState) {
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => value });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

beforeEach(() => {
  vi.useFakeTimers();
  adminGetCapacityHistory.mockReset();
  setVisibility("visible");
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useCapacityHistory — gating", () => {
  it("is idle and fetches nothing without a token", () => {
    const { result } = renderHook(() => useCapacityHistory(null, "i-a", "3h", null));
    expect(result.current.state.status).toBe("idle");
    expect(adminGetCapacityHistory).not.toHaveBeenCalled();
  });

  it("is idle and fetches nothing without an instance", () => {
    const { result } = renderHook(() => useCapacityHistory("tok", null, "3h", null));
    expect(result.current.state.status).toBe("idle");
    result.current.refresh();
    expect(adminGetCapacityHistory).not.toHaveBeenCalled();
  });
});

describe("useCapacityHistory — fetch states", () => {
  it("loads, then becomes ready with the fetched history", async () => {
    adminGetCapacityHistory.mockResolvedValue(buildHistory());
    const { result } = renderHook(() => useCapacityHistory("tok", "i-a", "3h", 300));
    expect(result.current.state.status).toBe("loading");

    await flushMicrotasks();

    expect(result.current.state).toMatchObject({ status: "ready", refreshing: false, refreshError: null });
    expect(adminGetCapacityHistory).toHaveBeenCalledWith("tok", "i-a", "3h", 300);
  });

  it("becomes an error with the thrown message when the first load fails", async () => {
    adminGetCapacityHistory.mockRejectedValue(new Error("Unknown instance."));
    const { result } = renderHook(() => useCapacityHistory("tok", "i-a", "3h", null));
    await flushMicrotasks();
    expect(result.current.state).toEqual({ status: "error", message: "Unknown instance." });
  });

  it("uses a generic message when the rejection is not an Error", async () => {
    adminGetCapacityHistory.mockRejectedValue("nope");
    const { result } = renderHook(() => useCapacityHistory("tok", "i-a", "3h", null));
    await flushMicrotasks();
    expect(result.current.state).toEqual({ status: "error", message: "Failed to load metric history" });
  });

  it("shows loading — never the previous instance's charts — after the selection changes", async () => {
    adminGetCapacityHistory.mockResolvedValueOnce(buildHistory("i-a"));
    const pending = deferred<AdminCapacityHistory>();
    adminGetCapacityHistory.mockReturnValueOnce(pending.promise);

    const { result, rerender } = renderHook(
      ({ id }: { id: string }) => useCapacityHistory("tok", id, "3h", null),
      { initialProps: { id: "i-a" } },
    );
    await flushMicrotasks();
    expect(result.current.state.status).toBe("ready");

    rerender({ id: "i-b" });
    expect(result.current.state.status).toBe("loading");

    pending.resolve(buildHistory("i-b"));
    await flushMicrotasks();
    expect(result.current.state.status === "ready" && result.current.state.history.instance_id).toBe("i-b");
  });

  it("ignores a slow response that a newer request has superseded", async () => {
    const slow = deferred<AdminCapacityHistory>();
    adminGetCapacityHistory.mockReturnValueOnce(slow.promise);
    adminGetCapacityHistory.mockResolvedValueOnce(buildHistory("i-a", "1d"));

    const { result, rerender } = renderHook(
      ({ range }: { range: CapacityHistoryRange }) => useCapacityHistory("tok", "i-a", range, null),
      { initialProps: { range: "3h" as CapacityHistoryRange } },
    );
    rerender({ range: "1d" });
    await flushMicrotasks();

    slow.resolve(buildHistory("i-a", "3h"));
    await flushMicrotasks();

    expect(result.current.state.status === "ready" && result.current.state.history.range).toBe("1d");
  });
});

describe("useCapacityHistory — refresh", () => {
  it("refreshes every 60s while visible and stops on unmount", async () => {
    adminGetCapacityHistory.mockResolvedValue(buildHistory());
    const { unmount } = renderHook(() => useCapacityHistory("tok", "i-a", "3h", null));
    await flushMicrotasks();
    expect(adminGetCapacityHistory).toHaveBeenCalledTimes(1);

    await act(async () => {
      vi.advanceTimersByTime(HISTORY_REFRESH_INTERVAL_MS);
    });
    await flushMicrotasks();
    expect(adminGetCapacityHistory).toHaveBeenCalledTimes(2);

    unmount();
    await act(async () => {
      vi.advanceTimersByTime(HISTORY_REFRESH_INTERVAL_MS * 2);
    });
    expect(adminGetCapacityHistory).toHaveBeenCalledTimes(2);
  });

  it("pauses while hidden and refreshes immediately on return", async () => {
    adminGetCapacityHistory.mockResolvedValue(buildHistory());
    renderHook(() => useCapacityHistory("tok", "i-a", "3h", null));
    await flushMicrotasks();

    act(() => {
      setVisibility("hidden");
      document.dispatchEvent(new Event("visibilitychange"));
    });
    await act(async () => {
      vi.advanceTimersByTime(HISTORY_REFRESH_INTERVAL_MS * 3);
    });
    expect(adminGetCapacityHistory).toHaveBeenCalledTimes(1);

    act(() => {
      setVisibility("visible");
      document.dispatchEvent(new Event("visibilitychange"));
    });
    await flushMicrotasks();
    expect(adminGetCapacityHistory).toHaveBeenCalledTimes(2);
  });

  it("flags refreshing during a manual refresh and clears it when the fetch settles", async () => {
    adminGetCapacityHistory.mockResolvedValueOnce(buildHistory());
    const { result } = renderHook(() => useCapacityHistory("tok", "i-a", "3h", null));
    await flushMicrotasks();

    const pending = deferred<AdminCapacityHistory>();
    adminGetCapacityHistory.mockReturnValueOnce(pending.promise);
    act(() => result.current.refresh());
    expect(result.current.state).toMatchObject({ status: "ready", refreshing: true });

    pending.resolve(buildHistory());
    await flushMicrotasks();
    expect(result.current.state).toMatchObject({ status: "ready", refreshing: false });
  });

  it("keeps the last good charts and reports refreshError when a refresh fails", async () => {
    adminGetCapacityHistory.mockResolvedValueOnce(buildHistory());
    adminGetCapacityHistory.mockRejectedValueOnce(new Error("CloudWatch slow"));
    const { result } = renderHook(() => useCapacityHistory("tok", "i-a", "3h", null));
    await flushMicrotasks();

    act(() => result.current.refresh());
    await flushMicrotasks();

    expect(result.current.state).toMatchObject({
      status: "ready",
      refreshing: false,
      refreshError: "CloudWatch slow",
    });

    adminGetCapacityHistory.mockResolvedValueOnce(buildHistory());
    act(() => result.current.refresh());
    await flushMicrotasks();
    expect(result.current.state).toMatchObject({ status: "ready", refreshError: null });
  });
});
