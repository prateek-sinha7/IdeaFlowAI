import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, cleanup, waitFor } from "@testing-library/react";
import React from "react";
import type { AgentRunState, PipelineRunState } from "@/types/index";

// ─────────────────────────────────────────────────────────────────────────────
// QA-PS-048 / ISS-829 (sibling of ISS-800) — AgentThinkingTab.tsx:167-180's
// gate-events effect (RUNUI-06 comment: "REUSES the existing getRunGateEvents
// endpoint — the Audit tab's source") is a second, independent consumer of the
// exact same endpoint AuditTab already fetches for the same run. Neither
// caller shares a cache (getRunGateEvents calls api.ts's bare `request()`,
// never the `cachedGet()` TTL helper ISS-800 root-caused), so visiting Audit
// then Steps for the SAME run fetches gate-events twice — the "expected" repro
// step this bug's own card set names ("Steps tab: no new fetch — agent steps
// already in the run's durable event replay").
//
// api.ts is left UNMOCKED here (only global fetch is stubbed) so the real
// getRunGateEvents/request() path is exercised end to end — the dedupe (or
// its absence) lives in api.ts, not in either component.
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

import { AuditTab } from "./AuditTab";
import { AgentThinkingTab } from "./AgentThinkingTab";
import { setToken } from "@/lib/api";

const RUN = "r1";
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
    if (String(url).includes("/gate-events")) {
      return Promise.resolve(okJson({ workflow_id: RUN, gate_events: [] }));
    }
    if (String(url).includes("/validation-results")) {
      return Promise.resolve(okJson({ workflow_id: RUN, validation_results: [] }));
    }
    if (String(url).includes("/exec-runs")) {
      return Promise.resolve(okJson({ workflow_id: RUN, exec_runs: [] }));
    }
    if (String(url).includes("/hook-runs")) {
      return Promise.resolve(okJson({ workflow_id: RUN, hook_runs: [] }));
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

describe("gate-events shared across Audit and Steps tabs for the same run (QA-PS-048 / ISS-829)", () => {
  it("visiting Audit then Steps fetches gate-events once for the run, not twice", async () => {
    const { unmount } = render(<AuditTab workflowRunId={RUN} />);
    await waitFor(() => {
      expect(fetchMock.mock.calls.some((c) => String(c[0]).includes("/gate-events"))).toBe(true);
    });
    unmount();

    render(<AgentThinkingTab agents={AGENTS} pipelineState={makePipelineState()} />);
    // AgentThinkingTab's gate-events fetch goes through a dynamic
    // `await import("@/lib/api")` inside its effect — give that microtask
    // chain time to settle before reading the final count (a `waitFor` here
    // would stop polling the instant the pre-existing count of 1 from
    // AuditTab happens to match, before this second caller's own request
    // lands).
    await new Promise((r) => setTimeout(r, 50));
    const gateEventCalls = fetchMock.mock.calls.filter((c) => String(c[0]).includes("/gate-events"));
    // Without a shared cache, the Steps tab's own independent caller fires a
    // second gate-events request for a run the Audit tab already fetched it
    // for — this bug's own repro step names the Steps tab as needing "no new
    // fetch" for exactly this data.
    expect(gateEventCalls.length).toBe(1);
  });
});
