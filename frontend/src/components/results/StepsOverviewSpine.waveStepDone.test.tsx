/**
 * A finished WAVE step shows DONE, and counts.
 *
 * FIX-182 added a guard so a task-loop build agent does not flash DONE between
 * iterations: it withholds DONE until every task_progress count agrees. The
 * guard was selected by an agent-id regex (/build|construct/i) alone, so a
 * wave-scheduled step called `pb-build` matched it — and a wave step reports no
 * task_progress at all, so the count it waits on stays 0 and the condition can
 * never be satisfied. Live symptom (run ef341493): "Builders" sat with an empty
 * circle beside its own 1m 46s duration, and the header read "2 / 4 agents"
 * with three of them finished.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { AgentRunState, PipelineRunState } from "@/types/index";
import { StepsOverviewSpine } from "./StepsOverviewSpine";

vi.mock("@/components/workflow/TokenUsageSummary", () => ({
  TokenUsageSummary: () => <div data-testid="token-usage" />,
}));

const agent = (p: Partial<AgentRunState> & { id: string }): AgentRunState => ({
  name: p.id, role: "Phase", icon: "🤖", status: "done", output: "", thinking: "",
  duration: 40, error: null, index: 0, ...p,
});

/** Spec Writer + Plan Lead + a finished wave "Builders" + a running Assembler. */
const AGENTS: AgentRunState[] = [
  agent({ id: "custom-agent:pb-spec", name: "Spec Writer", status: "done" }),
  agent({ id: "custom-agent:pb-plan", name: "Plan Lead", status: "done" }),
  agent({ id: "custom-agent:pb-build", name: "Builders", status: "done", duration: 105.72 }),
  agent({ id: "custom-agent:pb-assemble", name: "Assembler", status: "running" }),
];

/** A wave step reports waves and subagents — never protoCompletedTaskCount. */
const WAVE_PIPELINE: PipelineRunState = {
  isRunning: true, pipeline_type: "custom", agents: AGENTS,
  currentAgentIndex: 3, totalDuration: 300, completedCount: 3,
};

const spine = (ps: PipelineRunState) =>
  render(<StepsOverviewSpine agents={ps.agents} pipelineState={ps} onOpenAgent={vi.fn()} />);

describe("StepsOverviewSpine — a finished wave step is done", () => {
  it("counts the finished wave step in the header", () => {
    spine(WAVE_PIPELINE);
    // Three of four have finished; the wave step is one of them.
    expect(screen.getByText(/3\s*\/\s*4 agents/)).toBeInTheDocument();
  });

  it("still holds a task-loop build back until its tasks agree", () => {
    // The guard's real purpose: agent_complete fires per iteration, so a build
    // agent reporting 2 of 5 tasks must NOT read as done mid-loop.
    const ps: PipelineRunState = {
      ...WAVE_PIPELINE,
      protoTotalTasks: 5,
      protoCompletedTaskCount: 2,
    };
    spine(ps);
    expect(screen.getByText(/2\s*\/\s*4 agents/)).toBeInTheDocument();
  });

  it("releases a task-loop build once every task is confirmed", () => {
    const ps: PipelineRunState = {
      ...WAVE_PIPELINE,
      protoTotalTasks: 5,
      protoCompletedTaskCount: 5,
    };
    spine(ps);
    expect(screen.getByText(/3\s*\/\s*4 agents/)).toBeInTheDocument();
  });

  it("a settled run counts every done step either way", () => {
    const ps: PipelineRunState = {
      ...WAVE_PIPELINE,
      isRunning: false,
      agents: AGENTS.map(a => ({ ...a, status: "done" as const })),
    };
    spine(ps);
    expect(screen.getByText(/4\s*\/\s*4 agents/)).toBeInTheDocument();
  });
});
