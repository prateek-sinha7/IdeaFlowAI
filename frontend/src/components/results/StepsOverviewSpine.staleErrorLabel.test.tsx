import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { AgentRunState, PipelineRunState } from "@/types/index";
import { StepsOverviewSpine } from "./StepsOverviewSpine";

/**
 * ISS-317 — reopening/resuming a failed or cancelled run leaves the agent that
 * previously errored still carrying `status: "error"` in the `agents` array
 * (useWorkflow.ts's pipeline_start merge does not clear it). StepsOverviewSpine's
 * `failed` boolean is `pipelineState?.failed || agents.some(a => a.status ===
 * "error")`, evaluated BEFORE `isRunning`, so the panel stays pinned on
 * "Run failed" for the whole live resume even though the header/sub-header
 * correctly read "Running".
 *
 * Correct behaviour: while `pipelineState.isRunning` is true, the status
 * summary must never read "Run failed", regardless of stale per-agent error
 * status left over from before the resume.
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

describe("StepsOverviewSpine — stale error status during a live resume (ISS-317)", () => {
  it('ISS-317 — does not show "Run failed" while the pipeline is actively running', () => {
    const agents: AgentRunState[] = [
      // Left over from the pre-resume attempt: status never reset to idle.
      agent({ id: "strategist", status: "error" }),
      agent({ id: "deck-engineer", status: "running", index: 1 }),
    ];
    const pipelineState: PipelineRunState = {
      isRunning: true,
      pipeline_type: "presentation",
      agents,
      currentAgentIndex: 1,
      totalDuration: null,
      completedCount: 0,
      // pipelineState.failed itself is NOT set on this genuine live resume —
      // the API confirms status: "generating" — only the stale per-agent
      // status is polluted.
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
