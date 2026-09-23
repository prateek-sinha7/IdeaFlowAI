import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, cleanup, waitFor } from "@testing-library/react";
import React from "react";
import type { AgentRunState, PipelineRunState } from "@/types/index";

// ─────────────────────────────────────────────────────────────────────────────
// QA-PS-048 / ISS-854 (sibling of ISS-853) — the SAME divert-link effect
// (`AgentThinkingTab.tsx:201-258`) also calls `getWorkflowDefinitions(token)`
// (`:215`, -> `api.ts:1929`, `GET /api/workflows`, ~22-30 KB) on every
// Steps-tab mount, BEFORE it even knows whether the run has a divert link to
// label. `getWorkflowDefinitions` has no dedupe of any kind — not even the
// StrictMode-only guard `getWorkflow` got from FIX-637's singleFlightGet.
//
// A run with no parent and no divert never renders a divert-link row, so this
// fetch is pure waste for the common case. ISS-853's chosen fix (reading
// status/parentRunId from runFamily) removes the need to call
// getWorkflowDefinitions at all until a link is actually known to exist.
// ─────────────────────────────────────────────────────────────────────────────

vi.mock("motion/react", () => ({
  motion: new Proxy(
    {},
    {
      get: (_t, prop: string) =>
        ({ children, ...rest }: { children?: React.ReactNode } & Record<string, unknown>) =>
          React.createElement(prop, rest, children),
    },
  ),
  AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));

vi.mock("@/components/workflow/TokenUsageSummary", () => ({
  TokenUsageSummary: () => <div data-testid="token-usage" />,
}));

import { AgentThinkingTab } from "./AgentThinkingTab";
import { setToken } from "@/lib/api";

const RUN = "r-854";
const fetchMock = vi.fn();

function okJson(body: unknown) {
  return { ok: true, status: 200, headers: new Headers(), json: async () => body };
}

function makeAgent(partial: Partial<AgentRunState> & { id: string }): AgentRunState {
  return {
    name: partial.id,
    role: "Phase",
    icon: "🤖",
    status: "done",
    output: "Final output text.",
    thinking: "",
    duration: 1,
    error: null,
    index: 0,
    ...partial,
  };
}
const AGENTS: AgentRunState[] = [makeAgent({ id: "spec-writer" })];
function makePipelineState(): PipelineRunState {
  return {
    isRunning: false,
    pipeline_type: "user_stories",
    agents: AGENTS,
    currentAgentIndex: 1,
    totalDuration: 1,
    completedCount: 1,
    pipelineRunId: RUN,
  };
}

beforeEach(() => {
  fetchMock.mockReset();
  fetchMock.mockImplementation((url: string) => {
    const u = String(url);
    if (u.includes("/gate-events")) return Promise.resolve(okJson({ workflow_id: RUN, gate_events: [] }));
    if (u.includes("/validation-results")) return Promise.resolve(okJson({ workflow_id: RUN, validation_results: [] }));
    if (u.includes("/exec-runs")) return Promise.resolve(okJson({ workflow_id: RUN, exec_runs: [] }));
    if (u.includes("/hook-runs")) return Promise.resolve(okJson({ workflow_id: RUN, hook_runs: [] }));
    if (u.includes("/api/workflows")) return Promise.resolve(okJson([]));
    if (new RegExp(`/api/runs/${RUN}$`).test(u)) {
      // Completed, no parent, no divert — no link is ever shown for this run.
      return Promise.resolve(
        okJson({
          id: RUN,
          title: "t",
          type: "prototype",
          status: "completed",
          input: "in",
          output: "out",
          agent_outputs: null,
          agent_count: 1,
          duration: 10,
          error: null,
          token_usage: null,
          model_id: null,
          parent_run_id: null,
          created_at: "2026-07-01T00:00:00Z",
          completed_at: null,
        }),
      );
    }
    return Promise.resolve(okJson({}));
  });
  vi.stubGlobal("fetch", fetchMock);
  setToken("tok");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("Steps tab must not fetch the whole workflow catalog for a run with no divert link (QA-PS-048 / ISS-854)", () => {
  it("does not call getWorkflowDefinitions when the run has no parent and no live divert marker", async () => {
    render(<AgentThinkingTab agents={AGENTS} pipelineState={makePipelineState()} />);
    await waitFor(() => {
      expect(fetchMock.mock.calls.length).toBeGreaterThan(0);
    });
    await new Promise((r) => setTimeout(r, 50));

    const catalogCalls = fetchMock.mock.calls.filter((c) => String(c[0]).includes("/api/workflows"));
    // BUG (ISS-854): getWorkflowDefinitions fires unconditionally, before the
    // effect even checks whether a divert link exists — this is > 0 today.
    expect(catalogCalls.length).toBe(0);
  });
});
