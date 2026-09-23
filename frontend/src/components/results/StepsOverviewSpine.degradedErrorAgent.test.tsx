import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { AgentRunState, PipelineRunState } from "@/types/index";
import { StepsOverviewSpine } from "./StepsOverviewSpine";

/**
 * ISS-701 / ISS-764 — StepsOverviewSpine.tsx:408 ORs
 * `agents.some(a => a.status === "error")` into the `failed` boolean ahead
 * of the `pipelineState?.degraded` (and `cancelled`) checks. ISS-317/FIX-379
 * only gated this with `!isRunning`, which protects a live resume but not a
 * genuinely TERMINAL degraded or cancelled run: a degraded/cancelled run
 * legitimately has an agent left in `status: "error"` (that is what
 * "degraded"/"stopped after a partial failure" means), yet the per-agent OR
 * still wins the ternary over the correct terminal-marker branch.
 *
 * Correct behaviour: once the run is terminal (`isRunning: false`), the
 * "Run failed" label must come from `pipelineState.failed` alone, never from
 * per-agent status — a terminal `degraded` run must read "Run degraded".
 */
function agent(over: Partial<AgentRunState> & { id: string }): AgentRunState {
  return {
    name: over.id,
    role: "writer",
    icon: "🤖",
    status: "idle",
    output: "",
    thinking: "",
    duration: null,
    error: null,
    index: 0,
    ...over,
  };
}

describe("StepsOverviewSpine — terminal degraded run with an errored agent (ISS-701)", () => {
  it('ISS-701 — shows "Run degraded", not "Run failed", for a terminal degraded run with an error-status agent', () => {
    const agents: AgentRunState[] = [
      agent({ id: "strategist", status: "done" }),
      agent({ id: "validator", status: "error", index: 1 }),
    ];
    const pipelineState: PipelineRunState = {
      isRunning: false,
      pipeline_type: "presentation",
      agents,
      currentAgentIndex: 1,
      totalDuration: null,
      completedCount: 1,
      degraded: true,
      // pipelineState.failed is NOT set — only degraded is true, which is the
      // correct persisted terminal marker for this run.
    };

    render(
      <StepsOverviewSpine
        agents={agents}
        pipelineState={pipelineState}
        onOpenAgent={vi.fn()}
      />,
    );

    expect(screen.getByText("Run degraded")).toBeInTheDocument();
    expect(screen.queryByText("Run failed")).not.toBeInTheDocument();
  });
});
