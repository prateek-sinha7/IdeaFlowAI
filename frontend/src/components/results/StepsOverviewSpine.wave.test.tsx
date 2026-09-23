import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { AgentRunState, PipelineRunState } from "@/types/index";
import { StepsOverviewSpine } from "./StepsOverviewSpine";

// ─── StepsOverviewSpine — wave step as ONE ordinary row + wave_skipped ────────
// A wave step (e.g. "Screen Builders") must render as ONE row in the master
// Steps list, exactly like any other step — no worker rows, no nested worker
// block, no collapse/expand toggle. The per-worker rows live on the step's L2
// detail page instead (AgentDetailPanel), not here. The row still carries the
// wave progress summary ("Wave 2 · 2/3") so progress is visible at a glance.
// A `waveSkipped` step must render visually distinct from a plain "done" check.

function agent(overrides: Partial<AgentRunState> = {}): AgentRunState {
  return {
    id: "wave-step",
    name: "Screen Builders",
    role: "Builder",
    icon: "🤖",
    status: "running",
    output: "",
    thinking: "",
    duration: null,
    error: null,
    index: 0,
    ...overrides,
  };
}

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

describe("StepsOverviewSpine — wave step renders as ONE ordinary row", () => {
  it("renders exactly one row for a wave step and NO worker rows, but does show the wave progress summary", () => {
    const a = agent({
      waveWorkers: [
        { taskId: "t1", status: "done", workerIndex: 0, waveIndex: 0, waveTotal: 3 },
        { taskId: "t2", status: "running", workerIndex: 1, waveIndex: 0, waveTotal: 3 },
        { taskId: "t3", status: "running", workerIndex: 2, waveIndex: 0, waveTotal: 3 },
      ],
    });
    render(
      <StepsOverviewSpine
        agents={[a]}
        pipelineState={ps({ agents: [a] })}
        onOpenAgent={vi.fn()}
      />,
    );

    // Exactly one row for this step, however many workers it has.
    expect(screen.getAllByTestId("steps-agent-row")).toHaveLength(1);
    // No worker rows and no collapse/expand toggle anywhere in the master list.
    expect(screen.queryByTestId("wave-worker-row")).toBeNull();
    expect(screen.queryByTestId("wave-toggle")).toBeNull();
    // The row still shows wave progress (1 done + 1 in-flight of 3 → "Wave 2/3").
    expect(screen.getByText("Wave 2/3")).toBeInTheDocument();
  });

  it("scopes the progress line to the CURRENT wave and names it, when a step ran more than one wave — still no worker rows", () => {
    const a = agent({
      waveWorkers: [
        // Wave 0 — fully done.
        { taskId: "t1", status: "done", workerIndex: 0, waveIndex: 0, waveTotal: 2 },
        { taskId: "t2", status: "done", workerIndex: 1, waveIndex: 0, waveTotal: 2 },
        // Wave 1 — in flight.
        { taskId: "t3", status: "done", workerIndex: 0, waveIndex: 1, waveTotal: 3 },
        { taskId: "t4", status: "running", workerIndex: 1, waveIndex: 1, waveTotal: 3 },
        { taskId: "t5", status: "running", workerIndex: 2, waveIndex: 1, waveTotal: 3 },
      ],
    });
    render(
      <StepsOverviewSpine
        agents={[a]}
        pipelineState={ps({ agents: [a] })}
        onOpenAgent={vi.fn()}
      />,
    );

    // Still one row, no worker rows nested underneath it.
    expect(screen.getAllByTestId("steps-agent-row")).toHaveLength(1);
    expect(screen.queryByTestId("wave-worker-row")).toBeNull();
    // Progress reads wave 1's in-flight count (2/3), named "Wave 2" (1-based), not
    // the sum of both waves' workers (5) or wave 0's already-finished count.
    expect(screen.getByText("Wave 2 · 2/3")).toBeInTheDocument();
  });

  it("renders no worker rows and no crash for a plain agent with no waveWorkers (defensive default)", () => {
    const a = agent({ waveWorkers: undefined });
    render(
      <StepsOverviewSpine
        agents={[a]}
        pipelineState={ps({ agents: [a] })}
        onOpenAgent={vi.fn()}
      />,
    );

    expect(screen.getAllByTestId("steps-agent-row")).toHaveLength(1);
    expect(screen.queryByTestId("wave-worker-row")).toBeNull();
  });

  it("navigates via onOpenAgent when the row is clicked, wave step or not", async () => {
    const onOpenAgent = vi.fn();
    const a = agent({
      status: "done",
      waveWorkers: [
        { taskId: "t1", status: "done", workerIndex: 0, waveIndex: 0, waveTotal: 1 },
      ],
    });
    render(
      <StepsOverviewSpine
        agents={[a]}
        pipelineState={ps({ isRunning: false, agents: [a] })}
        onOpenAgent={onOpenAgent}
      />,
    );

    screen.getByTestId("steps-agent-row").click();
    expect(onOpenAgent).toHaveBeenCalledWith("wave-step");
  });
});

describe("StepsOverviewSpine — wave_skipped", () => {
  it("renders a distinct skipped card with the reason, not a plain done check", () => {
    const a = agent({
      status: "done",
      waveSkipped: { reason: "no eligible tasks after planning", sourceStep: "planner" },
    });
    render(
      <StepsOverviewSpine
        agents={[a]}
        pipelineState={ps({ isRunning: false, agents: [a] })}
        onOpenAgent={vi.fn()}
      />,
    );

    expect(screen.getByTestId("wave-skipped-card")).toBeInTheDocument();
    expect(screen.getByText("no eligible tasks after planning")).toBeInTheDocument();
    expect(screen.getByText("Skipped — 0 tasks")).toBeInTheDocument();
  });
});

describe("StepsOverviewSpine — wave_repair", () => {
  it("renders a warning row with the repaired count", () => {
    const a = agent({ status: "done", waveRepair: { waveIndex: 1, missingTaskIds: ["t4"], count: 1 } });
    render(
      <StepsOverviewSpine
        agents={[a]}
        pipelineState={ps({ isRunning: false, agents: [a] })}
        onOpenAgent={vi.fn()}
      />,
    );

    expect(screen.getByTestId("wave-repair-row")).toBeInTheDocument();
    expect(screen.getByText("1 dropped task repaired")).toBeInTheDocument();
  });
});
