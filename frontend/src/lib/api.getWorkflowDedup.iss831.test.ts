import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getWorkflow, getRunFamily } from "@/lib/api";

// ─────────────────────────────────────────────────────────────────
// QA-PS-048 / ISS-831 (sibling of ISS-800) — getWorkflow() (the 829 KB full
// run record) and getRunFamily() both call `request()` directly with no
// dedup guard, unlike getWorkflows() (FIX-616 / ISS-783's inFlightWorkflows
// map) or the catalog/preferences/analytics GETs (cachedGet(), ISS-782).
// getWorkflow has 8+ unguarded call sites app-wide and getRunFamily has 4
// (DashboardLayout.tsx, PreviewPanel.tsx, AgentThinkingTab.tsx, FilesTab.tsx,
// StartingPointCard.tsx, WorkflowHistory.tsx, page.tsx) — this is the
// mechanism behind BUGS.md QA-PS-048's reported "full run record fetched 3x"
// and the family x2 ISS-800 additionally observed live.
//
// This pins the fix at its root, the same way api.getWorkflowDetailDedup.test.ts
// and api.getWorkflowsDedup.test.ts do for their own endpoints: concurrent
// calls for the SAME run id must share one in-flight fetch.
// ─────────────────────────────────────────────────────────────────

const fetchMock = vi.fn();

function okWorkflow() {
  return {
    ok: true,
    status: 200,
    headers: new Headers(),
    json: async () => ({
      id: "run-1",
      title: "t",
      type: "prototype",
      status: "completed",
      input: "in",
      output: "out",
      agent_outputs: null,
      agent_count: 3,
      duration: 10,
      error: null,
      token_usage: null,
      model_id: null,
      created_at: "2026-07-01T00:00:00Z",
      completed_at: null,
    }),
  };
}

function okFamily() {
  return {
    ok: true,
    status: 200,
    headers: new Headers(),
    json: async () => ({ root_id: "run-1", members: [] }),
  };
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("getWorkflow() concurrent-call dedup (QA-PS-048 / ISS-831)", () => {
  it("coalesces concurrent calls for the SAME run id into a single fetch", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(okWorkflow()));

    const [a, b] = await Promise.all([
      getWorkflow("tok", "run-1"),
      getWorkflow("tok", "run-1"),
    ]);

    expect(a).toEqual(b);

    const calls = fetchMock.mock.calls.filter((call) => String(call[0]).includes("/api/runs/run-1"));
    // Without a dedup guard this is 2 — the mechanism behind the reported
    // full run record fetched 3x on an Audit tab switch (multiple unguarded
    // call sites, each doubled again by React StrictMode).
    expect(calls).toHaveLength(1);
  });
});

describe("getRunFamily() concurrent-call dedup (QA-PS-048 / ISS-831)", () => {
  it("coalesces concurrent calls for the SAME run id into a single fetch", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(okFamily()));

    const [a, b] = await Promise.all([
      getRunFamily("tok", "run-1"),
      getRunFamily("tok", "run-1"),
    ]);

    expect(a).toEqual(b);

    const calls = fetchMock.mock.calls.filter((call) => String(call[0]).includes("/api/runs/run-1/family"));
    // Without a dedup guard this is 2 — matching ISS-800's own live
    // observation of GET /api/runs/<id>/family duplicating 2x on Audit open.
    expect(calls).toHaveLength(1);
  });
});
