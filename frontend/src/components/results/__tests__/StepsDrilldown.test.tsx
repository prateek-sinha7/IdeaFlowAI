import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import type { AgentRunState, PipelineRunState, WaveGroup } from "@/types/index";

// ─────────────────────────────────────────────────────────────────────────────
// Phase 32 plan 08 (SC-2, STEPS-ARTIFACT-DERIVATION-CONTRACT) — the Steps
// drill-down construction contract, proven off SCRIPTED events:
//   §2 dual-source: task_progress (completed_count) AND wave_*/subagent_*
//       (WaveTreePanel) both feed the construction block.
//   §3 KAN-99: the checklist caps at N-1 until agent_complete; completed_count
//       == total-1 is the expected fix-loop steady state, NOT a stall.
//   ISS-019: WaveTreePanel is mounted INSIDE the drill-down (not below the fold).
// TokenUsageSummary is stubbed (parity with the sibling AgentThinkingTab specs).
// ─────────────────────────────────────────────────────────────────────────────

vi.mock("@/components/workflow/TokenUsageSummary", () => ({
  TokenUsageSummary: () => <div data-testid="token-usage" />,
}));

import { AgentThinkingTab } from "../AgentThinkingTab";

function makeAgent(partial: Partial<AgentRunState> & { id: string }): AgentRunState {
  return {
    name: partial.id,
    role: "Build",
    icon: "🤖",
    status: "idle",
    output: "",
    thinking: "",
    duration: null,
    error: null,
    index: 0,
    ...partial,
  };
}

// Source B — the fan-out waves + workers (subagent_spawned → subagent_result).
const WAVES: WaveGroup[] = [
  {
    waveIndex: 0,
    step: "build",
    taskIds: ["t1", "t2"],
    status: "running",
    workers: [
      { agent: "worker-alpha", status: "done", worker: 0 },
      { agent: "worker-beta", status: "running", worker: 1 },
    ],
  },
  {
    waveIndex: 1,
    step: "build",
    taskIds: ["t3"],
    status: "pending",
    workers: [],
  },
];

function buildState(over: Partial<PipelineRunState> = {}): PipelineRunState {
  return {
    isRunning: true,
    pipeline_type: "prototype",
    agents: [makeAgent({ id: "prototype-build", name: "Build Agent", status: "running" })],
    currentAgentIndex: 0,
    totalDuration: null,
    completedCount: 0,
    // Source A — the task-loop checklist (task_progress.completed_count).
    protoCompletedTaskCount: 2,
    ...over,
  };
}

describe("Steps drill-down — construction dual-source + KAN-99 cap (SC-2)", () => {
  it("renders BOTH sources: the task_progress checklist AND the wave/subagent tree (ISS-019 mounted in the drill-down)", () => {
    render(
      <AgentThinkingTab
        agents={buildState().agents}
        pipelineState={buildState()}
        waves={WAVES}
      />,
    );

    // Source B — WaveTreePanel is mounted INSIDE the Steps drill-down (ISS-019).
    expect(screen.getByText("Wave / Subagent Tree")).toBeInTheDocument();
    expect(screen.getByText("Wave 0")).toBeInTheDocument();
    expect(screen.getByText("worker-alpha")).toBeInTheDocument();
    expect(screen.getByText("worker-beta")).toBeInTheDocument();

    // Source A — the task-loop checklist renders its progress counter.
    expect(screen.getByTestId("construction-progress")).toBeInTheDocument();
  });

  it("KAN-99: caps the checklist at N-1 while the pipeline runs (completed_count == total-1 is not a stall)", () => {
    // total tasks = unique wave taskIds = t1,t2,t3 = 3; completed_count = 2 = N-1.
    render(
      <AgentThinkingTab
        agents={buildState().agents}
        pipelineState={buildState({ isRunning: true, protoCompletedTaskCount: 2 })}
        waves={WAVES}
      />,
    );

    const progress = screen.getByTestId("construction-progress");
    // Capped at N-1 (2/3) — NOT prematurely 3/3.
    expect(progress).toHaveTextContent("2/3");
    // No stall / error affordance for the expected fix-loop steady state.
    const block = screen.getByTestId("construction-block");
    expect(within(block).queryByText(/stall|stalled|error/i)).toBeNull();
  });

  it("KAN-99: reaches N only on agent_complete (build done + pipeline terminal)", () => {
    render(
      <AgentThinkingTab
        agents={[makeAgent({ id: "prototype-build", name: "Build Agent", status: "done" })]}
        pipelineState={buildState({
          isRunning: false,
          protoCompletedTaskCount: 3,
          agents: [makeAgent({ id: "prototype-build", name: "Build Agent", status: "done" })],
        })}
        waves={WAVES.map((w) => ({ ...w, status: "completed" }))}
      />,
    );

    expect(screen.getByTestId("construction-progress")).toHaveTextContent("3/3");
  });
});
