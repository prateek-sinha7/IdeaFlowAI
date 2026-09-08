/**
 * specs/014 §3.5/3.8 — useCapacityMatrix polling hook.
 *
 * Mocks `@/lib/api`'s `adminListCapacity` (the hook's only collaborator) and
 * drives the interval + visibility-pause behavior with fake timers, mirroring
 * the fake-timer convention `ServiceBusyProvider.test.tsx` already uses for
 * its own countdown.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useCapacityMatrix } from "./useCapacityMatrix";
import type { AdminCapacityMatrix } from "@/lib/api";

// `waitFor` polls on real timers internally, which never fires under
// `vi.useFakeTimers()`. The hook's initial fetch is a plain microtask (no
// `setInterval` involved until the FIRST poll resolves), so flushing the
// microtask queue directly is both correct and immediate.
async function flushMicrotasks() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

const { adminListCapacity } = vi.hoisted(() => ({
  adminListCapacity: vi.fn(),
}));
vi.mock("@/lib/api", () => ({ adminListCapacity }));

function buildMatrix(instanceCount = 1): AdminCapacityMatrix {
  return {
    collected_at: "2026-09-08T12:00:00Z",
    self_instance_id: instanceCount > 0 ? "i-self0001" : null,
    instance_source: instanceCount > 0 ? "discovery" : "none",
    instances: Array.from({ length: instanceCount }, (_, i) => ({
      instance_id: `i-${i}`,
      instance_type: "t3.large",
      is_self: i === 0,
      cpu_used_percent: 30,
      mem_used_percent: 40,
      cpu_user_percent: 20,
      cpu_system_percent: 10,
      cpu_iowait_percent: 0,
      reading_age_seconds: 5,
      stale: false,
    })),
    gate: {
      enabled: true,
      state: "allowing",
      blind_reason: null,
      cpu_threshold_percent: 75,
      mem_threshold_percent: 75,
      signals: [],
      engaged_at: null,
      evaluated_at: "2026-09-08T12:00:00Z",
    },
  };
}

function setVisibility(value: DocumentVisibilityState) {
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    get: () => value,
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  adminListCapacity.mockReset();
  setVisibility("visible");
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useCapacityMatrix — token gating", () => {
  it("stays in 'loading' and never calls the API when token is null", () => {
    const { result } = renderHook(() => useCapacityMatrix(null));
    expect(result.current.status).toBe("loading");
    expect(adminListCapacity).not.toHaveBeenCalled();
  });
});

describe("useCapacityMatrix — fetch + discriminated state", () => {
  it("starts loading, then resolves to 'ready' with instances present", async () => {
    adminListCapacity.mockResolvedValue(buildMatrix(1));
    const { result } = renderHook(() => useCapacityMatrix("tok"));
    expect(result.current.status).toBe("loading");

    await flushMicrotasks();
    expect(result.current.status).toBe("ready");
    expect(adminListCapacity).toHaveBeenCalledWith("tok");
  });

  it("resolves to 'empty' when the matrix has zero instances", async () => {
    adminListCapacity.mockResolvedValue(buildMatrix(0));
    const { result } = renderHook(() => useCapacityMatrix("tok"));

    await flushMicrotasks();
    expect(result.current.status).toBe("empty");
  });

  it("resolves to 'error' with the thrown message when the fetch rejects", async () => {
    adminListCapacity.mockRejectedValue(new Error("boom"));
    const { result } = renderHook(() => useCapacityMatrix("tok"));

    await flushMicrotasks();
    expect(result.current).toMatchObject({ status: "error", message: "boom" });
  });
});

describe("useCapacityMatrix — polling interval", () => {
  it("polls again after 15s and stops polling on unmount", async () => {
    adminListCapacity.mockResolvedValue(buildMatrix(1));
    const { result, unmount } = renderHook(() => useCapacityMatrix("tok"));
    await flushMicrotasks();
    expect(result.current.status).toBe("ready");
    expect(adminListCapacity).toHaveBeenCalledTimes(1);

    await act(async () => {
      vi.advanceTimersByTime(15_000);
    });
    await flushMicrotasks();
    expect(adminListCapacity).toHaveBeenCalledTimes(2);

    unmount();
    await act(async () => {
      vi.advanceTimersByTime(30_000);
    });
    await flushMicrotasks();
    expect(adminListCapacity).toHaveBeenCalledTimes(2);
  });
});

describe("useCapacityMatrix — pause on hidden tab", () => {
  it("does not poll while the tab is hidden, and refreshes immediately on returning to visible", async () => {
    adminListCapacity.mockResolvedValue(buildMatrix(1));
    const { result } = renderHook(() => useCapacityMatrix("tok"));
    await flushMicrotasks();
    expect(result.current.status).toBe("ready");
    expect(adminListCapacity).toHaveBeenCalledTimes(1);

    act(() => {
      setVisibility("hidden");
      document.dispatchEvent(new Event("visibilitychange"));
    });

    await act(async () => {
      vi.advanceTimersByTime(30_000);
    });
    await flushMicrotasks();
    // No new poll while hidden, even though 2 interval periods elapsed.
    expect(adminListCapacity).toHaveBeenCalledTimes(1);

    act(() => {
      setVisibility("visible");
      document.dispatchEvent(new Event("visibilitychange"));
    });
    await flushMicrotasks();
    // Returning to visible triggers an immediate refresh, not a wait for the
    // next interval tick.
    expect(adminListCapacity).toHaveBeenCalledTimes(2);
  });
});
