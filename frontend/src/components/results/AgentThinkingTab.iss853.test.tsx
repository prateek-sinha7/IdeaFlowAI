import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, cleanup, waitFor } from "@testing-library/react";
import React from "react";
import type { AgentRunState, PipelineRunState } from "@/types/index";

// ─────────────────────────────────────────────────────────────────────────────
// QA-PS-048 / ISS-853 — AgentThinkingTab's divert-link effect
// (`AgentThinkingTab.tsx:201-258`) calls `getWorkflow(token, runId)` on every
// Steps-tab mount just to read `self.status` / `self.parentRunId`, re-fetching
// the full 829 KB run record every time the tab is opened even though nothing
// about it changes between opens for a completed run. The reopen path
// (`page.tsx:2999`) already fetched this exact record moments earlier.
//
// Re-analysis (ISS-853's own card, "Re-analysis (2026-09-23): settled") names
// the fix and the red test target: the effect must stop calling getWorkflow
// for the run's own id at all once it can read status/parentRunId from state
// the page already holds (`runFamily`, threaded down as a prop). Today no
// such prop exists, so this must fail.
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

const RUN = "r-853";
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
      // A completed run with no parent and no divert — the common case ISS-853
      // names ("self is fetched for every run, not only for revisions").
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

describe("Steps tab must not re-fetch the full run record it was just given (QA-PS-048 / ISS-853)", () => {
  it("does not call getWorkflow for the run's own id, on an initial mount or a remount", async () => {
    const { unmount } = render(<AgentThinkingTab agents={AGENTS} pipelineState={makePipelineState()} />);
    await waitFor(() => {
      // Give the divert-link effect's async chain (getWorkflowDefinitions then
      // getWorkflow) a chance to have fired at least once if it is going to.
      expect(fetchMock.mock.calls.length).toBeGreaterThan(0);
    });
    await new Promise((r) => setTimeout(r, 50));
    unmount();

    // Remount — simulates Steps -> another tab -> Steps, per the card's own
    // "What would settle it" repro.
    render(<AgentThinkingTab agents={AGENTS} pipelineState={makePipelineState()} />);
    await new Promise((r) => setTimeout(r, 50));

    const ownRecordCalls = fetchMock.mock.calls.filter((c) =>
      new RegExp(`/api/runs/${RUN}$`).test(String(c[0])),
    );
    // BUG (ISS-853): the effect calls getWorkflow(token, runId) unconditionally
    // on every mount today — this is > 0. The fix is to read status/parentRunId
    // from runFamily state the page already holds instead of re-fetching.
    expect(ownRecordCalls.length).toBe(0);
  });
});
