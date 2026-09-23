import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, cleanup, screen, waitFor } from "@testing-library/react";
import React from "react";
import type { AgentRunState, FamilyMember, PipelineRunState, RunFamily } from "@/types/index";

// ─────────────────────────────────────────────────────────────────────────────
// QA-PS-048 / ISS-853 + ISS-855: the path the iss853/iss855 tests never mount.
// Those render with no family at all. This one renders with the family the run
// screen already holds (PreviewPanel's `runFamily`), which is ISS-853's own
// red-test target. The divert-link row must come from that family with no run
// read of any kind, and with no family held yet it must fetch the small family
// read, never the full run record or the 100-run scan.
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

// DivertLinkRow calls useRouter.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "",
}));

import { AgentThinkingTab } from "./AgentThinkingTab";
import { setToken } from "@/lib/api";

const RUN = "r-fam";
const fetchMock = vi.fn();

function okJson(body: unknown) {
  return { ok: true, status: 200, headers: new Headers(), json: async () => body };
}

function member(partial: Partial<FamilyMember> & { id: string }): FamilyMember {
  return {
    type: "ex_a",
    title: "a run title",
    status: "completed",
    revision_index: 1,
    parent_run_id: null,
    created_at: "2026-07-01T00:00:00Z",
    completed_at: null,
    ...partial,
  };
}

const AGENTS: AgentRunState[] = [{
  id: "spec-writer", name: "spec-writer", role: "Phase", icon: "🤖", status: "done",
  output: "Final output text.", thinking: "", duration: 1, error: null, index: 0,
} as AgentRunState];
const PIPELINE: PipelineRunState = {
  isRunning: false, pipeline_type: "user_stories", agents: AGENTS, currentAgentIndex: 1,
  totalDuration: 1, completedCount: 1, pipelineRunId: RUN,
};

let familyResponse: RunFamily = { root_id: RUN, members: [] };

beforeEach(() => {
  fetchMock.mockReset();
  fetchMock.mockImplementation((url: string) => {
    const u = String(url);
    if (u.includes("/gate-events")) return Promise.resolve(okJson({ workflow_id: RUN, gate_events: [] }));
    if (u.endsWith(`/api/runs/${RUN}/family`)) return Promise.resolve(okJson(familyResponse));
    if (u.endsWith("/api/workflows")) {
      return Promise.resolve(okJson([{ id: "ex_b", name: "ex_b", short_name: "Spanish" }, { id: "ex_a", name: "ex_a", short_name: "Divert" }]));
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

const urls = () => fetchMock.mock.calls.map((c) => String(c[0]));
// Every run read the divert-link effect could make: the full record, the
// family, and the run list the old reverse scan used. Gate-events is a
// different effect and is excluded.
const runReads = () => urls().filter((u) => u.includes("/api/runs") && !u.includes("/gate-events"));

describe("Steps divert-link row reads the held revision family (QA-PS-048 / ISS-853, ISS-855)", () => {
  it("a completed root run with its family held makes no run read and no catalog read, on mount or remount", async () => {
    const family: RunFamily = { root_id: RUN, members: [member({ id: RUN })] };
    const { unmount } = render(<AgentThinkingTab agents={AGENTS} pipelineState={PIPELINE} runFamily={family} />);
    await waitFor(() => expect(urls().some((u) => u.includes("/gate-events"))).toBe(true));
    await new Promise((r) => setTimeout(r, 50));
    unmount();
    render(<AgentThinkingTab agents={AGENTS} pipelineState={PIPELINE} runFamily={family} />);
    await new Promise((r) => setTimeout(r, 50));

    expect(runReads()).toEqual([]);
    expect(urls().filter((u) => u.endsWith("/api/workflows"))).toEqual([]);
    expect(screen.queryByTestId("steps-divert-link-row")).toBeNull();
  });

  it("builds both link directions from the held family, labelled from the catalog, with no run read", async () => {
    // Source: this run diverted, and its child is a family member.
    const diverted: RunFamily = {
      root_id: RUN,
      members: [member({ id: RUN, status: "diverted" }), member({ id: "child", type: "ex_b", parent_run_id: RUN, revision_index: 2 })],
    };
    const { unmount } = render(<AgentThinkingTab agents={AGENTS} pipelineState={PIPELINE} runFamily={diverted} />);
    expect((await screen.findByTestId("steps-divert-link-row")).textContent).toContain("Diverted to Spanish →");
    unmount();

    // Target: this run's parent diverted into it.
    const continued: RunFamily = {
      root_id: "parent",
      members: [member({ id: "parent", status: "diverted" }), member({ id: RUN, type: "ex_b", parent_run_id: "parent", revision_index: 2 })],
    };
    render(<AgentThinkingTab agents={AGENTS} pipelineState={PIPELINE} runFamily={continued} />);
    expect((await screen.findByTestId("steps-divert-link-row")).textContent).toContain("← Continued from Divert");

    expect(runReads()).toEqual([]);
  });

  it("with no family held yet, fetches the family once, never the run record or the 100-run scan", async () => {
    familyResponse = {
      root_id: RUN,
      members: [member({ id: RUN, status: "diverted" }), member({ id: "child", type: "ex_b", parent_run_id: RUN, revision_index: 2 })],
    };
    render(<AgentThinkingTab agents={AGENTS} pipelineState={PIPELINE} runFamily={null} />);
    expect((await screen.findByTestId("steps-divert-link-row")).textContent).toContain("Diverted to Spanish →");

    expect(runReads().filter((u) => u.endsWith(`/api/runs/${RUN}/family`))).toHaveLength(1);
    expect(runReads().filter((u) => !u.endsWith(`/api/runs/${RUN}/family`))).toEqual([]);
  });
});
