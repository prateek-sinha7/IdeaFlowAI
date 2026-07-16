import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  RunConnectionProvider,
  useRunConnection,
} from "./RunConnectionProvider";

// ─────────────────────────────────────────────────────────────────
// BUG-013 (260716-r7d) — per-run SSE fan-out must be BOUNDED under the
// browser's ~6-connections-per-origin cap. The provider auto-streams only
// ACTIVELY-EMITTING (building) runs; BACKGROUND parked runs (waiting_for_user /
// clarifying) hold no stream. The viewed/launched run is kept streamed via a
// single sticky FOCUS (attachRun) that a new focus REPLACES (no accumulation).
//
// Drives the real provider through renderHook with useRunStream mocked so the
// RunStreamConnection children mount without a real EventSource, and @/lib/api
// partially mocked so refreshLiveRuns resolves a fixed run list. SC-001: the
// fixtures key on run STATUS strings and run IDs only — no workflow-name literal.
// ─────────────────────────────────────────────────────────────────

// The FE `WorkflowStatus` union is narrow and omits the runtime parked statuses
// the backend emits (waiting_for_user / clarifying); cast through `string` at the
// fixture boundary — the provider reads them via `Set<string>.has(r.status)`.
const RUNS = vi.hoisted(() => [
  { id: "build-run", status: "running" },
  { id: "gen-run", status: "generating" },
  { id: "parked-A", status: "waiting_for_user" },
  { id: "parked-B", status: "clarifying" },
]);

vi.mock("@/hooks/useRunStream", () => ({
  useRunStream: () => ({
    phase: "live",
    reconnect: () => {},
    lastMessage: null,
    lastError: null,
    cursor: null,
  }),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    getToken: () => "tok",
    getWorkflows: vi.fn(async () => RUNS),
  };
});

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("RunConnectionProvider — bounded per-run streams + sticky focus (BUG-013)", () => {
  it("Test 1: auto-streams ONLY building runs; BACKGROUND parked runs are excluded", async () => {
    const { result } = renderHook(() => useRunConnection(), {
      wrapper: RunConnectionProvider,
    });

    await waitFor(() => {
      expect(result.current.liveRunIds.length).toBeGreaterThan(0);
    });

    expect(result.current.liveRunIds).toContain("build-run");
    expect(result.current.liveRunIds).toContain("gen-run");
    // FAIL-BEFORE: NON_TERMINAL_STATUSES attaches every non-terminal run, so the
    // parked ids are present — RED. GREEN: AUTO_STREAM_STATUSES excludes them.
    expect(result.current.liveRunIds).not.toContain("parked-A");
    expect(result.current.liveRunIds).not.toContain("parked-B");
  });

  it("Test 2: attachRun sets a SINGLE sticky focus that a new focus REPLACES", async () => {
    const { result } = renderHook(() => useRunConnection(), {
      wrapper: RunConnectionProvider,
    });

    await waitFor(() => {
      expect(result.current.liveRunIds.length).toBeGreaterThan(0);
    });

    act(() => {
      result.current.attachRun("parked-A");
    });
    expect(result.current.liveRunIds).toContain("parked-A");

    act(() => {
      result.current.attachRun("parked-B");
    });
    // FAIL-BEFORE: attachRun APPENDS, so both parked ids remain — RED. GREEN: the
    // new focus REPLACES the prior (parked-B in, parked-A out).
    expect(result.current.liveRunIds).toContain("parked-B");
    expect(result.current.liveRunIds).not.toContain("parked-A");
  });

  it("Test 3: a building run stays streamed independent of the focus", async () => {
    const { result } = renderHook(() => useRunConnection(), {
      wrapper: RunConnectionProvider,
    });

    await waitFor(() => {
      expect(result.current.liveRunIds.length).toBeGreaterThan(0);
    });

    act(() => {
      result.current.attachRun("other");
    });

    // builds hold their stream via AUTO_STREAM_STATUSES regardless of focus.
    expect(result.current.liveRunIds).toContain("build-run");
    expect(result.current.liveRunIds).toContain("gen-run");
    expect(result.current.liveRunIds).toContain("other");
  });

  // BUG-015 — releasing the sticky focus for a COMPLETED run so its dead
  // RunStreamConnection unmounts (no reconnect, no ~14k re-replay). A PARKED id
  // is used as the focus so its presence in liveRunIds comes ONLY from the focus,
  // making detach observable in isolation.
  it("Test 4: detachRun clears the focus + drops the id; a non-focused id is a no-op", async () => {
    const { result } = renderHook(() => useRunConnection(), {
      wrapper: RunConnectionProvider,
    });

    await waitFor(() => {
      expect(result.current.liveRunIds.length).toBeGreaterThan(0);
    });

    act(() => {
      result.current.attachRun("parked-A");
    });
    expect(result.current.liveRunIds).toContain("parked-A");

    // A non-focused id (gen-run is auto-streamed, not the focus) → no-op on the
    // focus. FAIL-BEFORE: detachRun does not exist → "detachRun is not a function".
    act(() => {
      result.current.detachRun("gen-run");
    });
    expect(result.current.liveRunIds).toContain("parked-A");

    // Detaching the focused id clears the sticky focus + drops it from liveRunIds.
    act(() => {
      result.current.detachRun("parked-A");
    });
    expect(result.current.liveRunIds).not.toContain("parked-A");
  });
});
