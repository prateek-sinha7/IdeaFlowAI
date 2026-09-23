import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { AgentRunState, PipelineRunState } from "@/types/index";
import { StepsOverviewSpine } from "./StepsOverviewSpine";

/**
 * ISS-764 — sibling of ISS-701. StepsOverviewSpine.tsx:408 ORs
 * `agents.some(a => a.status === "error")` into `failed` without ever
 * checking `pipelineState?.cancelled`. useWorkflow.ts's `pipeline_cancelled`
 * handler explicitly leaves an already-errored agent's status untouched on
 * Stop (only `thinking`/`running` agents reset to `idle`), so a run stopped
 * after one agent already errored reaches this component with
 * `pipelineState.cancelled: true`, `pipelineState.failed` unset, and one
 * agent still carrying `status: "error"` — the same OR-precedence bug
 * ISS-701 targets for `degraded`, triggered instead by the cancelled marker.
 *
 * Correct behaviour: a terminal cancelled run must never read "Run failed"
 * purely because of a pre-cancel errored agent; `failed` must come from
 * `pipelineState.failed` alone.
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

describe("StepsOverviewSpine — terminal cancelled run with an errored agent (ISS-764)", () => {
  it('ISS-764 — does not show "Run failed" for a terminal cancelled run with a pre-cancel error-status agent', () => {
    const agents: AgentRunState[] = [
      agent({ id: "strategist", status: "error" }),
      agent({ id: "deck-engineer", status: "idle", index: 1 }),
    ];
    const pipelineState: PipelineRunState = {
      isRunning: false,
      pipeline_type: "presentation",
      agents,
      currentAgentIndex: 1,
      totalDuration: null,
      completedCount: 0,
      cancelled: true,
      // pipelineState.failed is NOT set — only cancelled is true.
    };

    render(
      <StepsOverviewSpine
        agents={agents}
        pipelineState={pipelineState}
        onOpenAgent={vi.fn()}
      />,
    );

    expect(screen.queryByText("Run failed")).not.toBeInTheDocument();
  });
});
