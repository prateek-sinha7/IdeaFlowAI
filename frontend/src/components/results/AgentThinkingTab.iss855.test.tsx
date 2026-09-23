import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, cleanup, waitFor } from "@testing-library/react";
import React from "react";
import type { AgentRunState, PipelineRunState } from "@/types/index";

// ─────────────────────────────────────────────────────────────────────────────
// QA-PS-048 / ISS-855 (sibling of ISS-853, inverse-direction divert case) —
// when the OPENED run has itself already diverted (`self.status === "diverted"`),
// `AgentThinkingTab.tsx:236-241` reverse-scans the run list
// (`getWorkflows(token, { limit: 100 })`) to find the one run whose
// `parentRunId === runId`, instead of reading the diverted child from
// `runFamily.members`, which the backend's `_owned_family_members` BFS
// (`backend/app/api/runs.py:1564-1603`) already includes ("a divert ... a
// cross-type child is admitted").
//
// This is wasteful (a 100-row fetch to find one id) AND fragile (the child
// silently falls out of the window past 100 runs, dropping the "Diverted to
// X" row with no error). ISS-853's chosen fix threads runFamily into
// AgentThinkingTab as a prop; ISS-855 is the same fix applied to this branch.
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

// The child IS found via today's reverse scan, so divertLink resolves
// non-null and StepsOverviewSpine's DivertLinkRow mounts, which needs a
// router context this render tree does not provide.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

import { AgentThinkingTab } from "./AgentThinkingTab";
import { setToken } from "@/lib/api";

const RUN = "r-855";
const CHILD = "r-855-child";
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
    if (u.includes("/api/workflows") && !u.includes("/api/runs")) {
      return Promise.resolve(okJson([]));
    }
    if (new RegExp(`/api/runs/${RUN}$`).test(u)) {
      // The opened run has already diverted.
      return Promise.resolve(
        okJson({
          id: RUN,
          title: "t",
          type: "prototype",
          status: "diverted",
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
    if (u.includes("/api/runs?") && u.includes("limit=100")) {
      // The reverse-scan endpoint the bug uses today.
      return Promise.resolve(
        okJson([
          {
            id: CHILD,
            title: "child",
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
            parent_run_id: RUN,
            created_at: "2026-07-01T00:01:00Z",
            completed_at: null,
          },
        ]),
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

describe("Diverted run must not reverse-scan the run list to find its child (QA-PS-048 / ISS-855)", () => {
  it("does not call getWorkflows({limit:100}) when self.status is 'diverted'", async () => {
    render(<AgentThinkingTab agents={AGENTS} pipelineState={makePipelineState()} />);
    await waitFor(() => {
      expect(fetchMock.mock.calls.length).toBeGreaterThan(0);
    });
    await new Promise((r) => setTimeout(r, 50));

    const reverseScanCalls = fetchMock.mock.calls.filter((c) => {
      const u = String(c[0]);
      return u.includes("/api/runs?") && u.includes("limit=100");
    });
    // BUG (ISS-855): the effect reverse-scans getWorkflows({limit:100}) for a
    // diverted child that runFamily.members already carries — this is > 0
    // today. The fix should read the child from a runFamily prop instead.
    expect(reverseScanCalls.length).toBe(0);
  });
});
