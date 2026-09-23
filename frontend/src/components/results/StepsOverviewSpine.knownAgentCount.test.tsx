/**
 * ISS-722 — QA-SG-001: the run detail "Pipeline running" header reads
 * "0 / 0" against a live 5-agent run because its total is derived from
 * `agents.length` (StepsOverviewSpine.tsx:403), the client-built roster that
 * stays empty until the first roster-building SSE event lands — while the
 * bell-icon notification panel reads the run's already-known `agent_count`
 * and correctly shows "0 of 5".
 *
 * The card's own fix direction (LEDGER.md QA-SG-001 row): "Fix belongs where
 * the total is derived once (shared selector, or seed useRunStateStore with
 * the known agent_count)". `PipelineRunState` (types/index.ts) has no such
 * field today — this test pins the header to use one once the roster is
 * still empty, mirroring the `agentCount` fallback AppHeader.tsx:216 already
 * uses for the notification path (`pipelineAgentsTotal || r.agentCount`).
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { AgentRunState, PipelineRunState } from "@/types/index";
import { StepsOverviewSpine } from "./StepsOverviewSpine";

function ps(overrides: Partial<PipelineRunState> = {}): PipelineRunState {
  return {
    isRunning: true,
    pipeline_type: "prototype",
    agents: [],
    currentAgentIndex: 0,
    totalDuration: null,
    completedCount: 0,
    ...overrides,
  };
}

describe("StepsOverviewSpine — ISS-722 header total during an empty roster (QA-SG-001)", () => {
  it("shows the run's known agent_count as the total instead of 0/0 while the roster is still empty", () => {
    const agents: AgentRunState[] = [];
    // The run's real agent count (5) is already known server-side at
    // creation, same as the value AppHeader/NotificationPanel read via
    // `r.agentCount`. Cast past PipelineRunState's current shape — adding
    // this field is exactly what the fix must do.
    const pipelineState = { ...ps(), agentCount: 5 } as PipelineRunState;

    render(
      <StepsOverviewSpine
        agents={agents}
        pipelineState={pipelineState}
        onOpenAgent={vi.fn()}
      />,
    );

    // Expected/correct behaviour: the header shows the known total (5),
    // matching what the notification panel shows for the same run at the
    // same moment — never "0 / 0" while a 5-agent total is already known.
    expect(screen.getByText(/Pipeline running/)).toHaveTextContent("5");
    expect(screen.queryByText(/0 \/ 0/)).toBeNull();
  });
});
