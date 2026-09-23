import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { AgentDetailPanel } from "./AgentDetailPanel";

// A wave step's per-worker rows moved OFF the master Steps list (StepsOverviewSpine)
// and onto this L2 drill-down instead — the user wants the workers "inside the step
// detail page and list there like task[s] have it" (the construction-task-row idiom).

function agent(overrides: Record<string, unknown> = {}) {
  return {
    id: "wave-step",
    name: "Screen Builders",
    role: "Builder",
    status: "running",
    output: "",
    thinkingText: "",
    thinking: "",
    contextSources: [],
    toolCalls: [],
    ...overrides,
  } as never;
}

describe("AgentDetailPanel — wave workers list", () => {
  it("lists every worker for a wave step, with the done/total count matching", () => {
    render(
      <AgentDetailPanel
        agent={agent({
          waveWorkers: [
            { taskId: "t1", status: "done", workerIndex: 0, waveIndex: 0, waveTotal: 3 },
            { taskId: "t2", status: "running", workerIndex: 1, waveIndex: 0, waveTotal: 3 },
            { taskId: "t3", status: "running", workerIndex: 2, waveIndex: 0, waveTotal: 3 },
          ],
        })}
        onBack={() => {}}
      />,
    );

    expect(screen.getByTestId("wave-workers-block")).toBeInTheDocument();
    expect(screen.getAllByTestId("wave-worker-row")).toHaveLength(3);
    // The header counts waves; the per-wave row is where the task count lives.
    expect(screen.getByTestId("wave-workers-progress")).toHaveTextContent("0 / 1 wave");
    expect(screen.getByTestId("wave-section-progress")).toHaveTextContent("1 / 3 done");
    // The row is now labelled by the task it owns (its shard id when the backend
    // sends one, else the task id) rather than "Worker N" — a wave row means "this
    // shard", and the ordinal said nothing the id doesn't say better.
    expect(screen.getByText("t1")).toBeInTheDocument();
  });

  it("renders no wave workers block for a non-wave step", () => {
    render(
      <AgentDetailPanel
        agent={agent({ waveWorkers: undefined })}
        onBack={() => {}}
      />,
    );

    expect(screen.queryByTestId("wave-workers-block")).not.toBeInTheDocument();
    expect(screen.queryByTestId("wave-worker-row")).not.toBeInTheDocument();
  });
});

describe("AgentDetailPanel — the plan's totals", () => {
  // A run whose plan holds four waves and 34 tasks read "0 / 1 done" through the
  // whole of wave 1: the panel could only count the workers it had been sent, and
  // nothing on screen distinguished the first hundredth of a build from a
  // finished one. `wave_started` now carries the totals it always knew.
  // The totals ride on the run store's wave GROUPS (a panel prop), while the rows
  // come off the agent — so the test has to supply both, exactly as the run view does.
  const groups = [
    { waveIndex: 0, step: "pb-build", taskIds: ["layout"], status: "running",
      waveTotal: 4, taskTotal: 34, workers: [] },
  ] as never;
  const rows = {
    waveWorkers: [{ taskId: "layout", status: "running", workerIndex: 0, waveIndex: 0 }],
  };

  it("counts WAVES in the header and tasks in the wave row", () => {
    render(<AgentDetailPanel agent={agent(rows)} waveGroups={groups} onBack={() => {}} />);
    // The header is the build's progress: no wave finished yet, four in the plan.
    expect(screen.getByTestId("wave-workers-progress")).toHaveTextContent("0 / 4 waves");
    // The row is this wave's progress, and counts its own tasks.
    expect(screen.getByTestId("wave-section-progress")).toHaveTextContent("0 / 1 done");
  });

  it("falls back to the waves on screen when no plan totals were sent", () => {
    render(<AgentDetailPanel agent={agent({
      waveWorkers: [
        { taskId: "t1", status: "done", workerIndex: 0, waveIndex: 0 },
        { taskId: "t2", status: "running", workerIndex: 1, waveIndex: 0 },
      ],
    })} onBack={() => {}} />);
    expect(screen.getByTestId("wave-workers-progress")).toHaveTextContent("0 / 1 wave");
    expect(screen.getByTestId("wave-section-progress")).toHaveTextContent("1 / 2 done");
  });
});
