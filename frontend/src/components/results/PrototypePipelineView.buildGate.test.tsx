import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import type { AgentRunState, PipelineRunState } from "@/types/index";
import { PrototypePipelineView } from "./PrototypePipelineView";

// ─────────────────────────────────────────────────────────────────
// Quick byv FIX-2 — the build checklist must NEVER flash all-tasks-completed
// during a between-task transition (buildAgent "done" while the run is still
// running and no later phase started). Real-DOM specs:
//   MID-LOOP  (isRunning true, build "done", 1/3 reported) → NOT all done.
//   TERMINAL  (isRunning false, build was the last agent)  → all done.
// ─────────────────────────────────────────────────────────────────

function makeAgent(partial: Partial<AgentRunState> & { id: string }): AgentRunState {
  return {
    name: partial.id,
    role: "Prototype phase",
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

// A plan agent whose output decomposes into exactly 3 parseable build tasks.
const PLAN_OUTPUT = [
  "## Task 1: Scaffold shell",
  "**Goal**: create the base HTML shell",
  "",
  "## Task 2: Add navigation",
  "**Goal**: wire the top nav",
  "",
  "## Task 3: Style pages",
  "**Goal**: apply the design system",
].join("\n");

const PLAN_AGENT = makeAgent({ id: "prototype-plan", name: "Task Planner", status: "done", output: PLAN_OUTPUT });
const BUILD_DONE = makeAgent({ id: "prototype-build", name: "Build Agent", status: "done" });

function makeState(isRunning: boolean, completed: number): PipelineRunState {
  return {
    isRunning,
    pipeline_type: "prototype",
    agents: [PLAN_AGENT, BUILD_DONE],
    currentAgentIndex: 1,
    totalDuration: null,
    completedCount: 1,
    protoCompletedTaskCount: completed,
  };
}

describe("PrototypePipelineView — buildTrulyDone gate (byv FIX-2)", () => {
  it("MID-LOOP: build 'done' while the run is still running does NOT mark all tasks complete", () => {
    // buildAgent "done", NO validate agent, run still running, 1/3 reported.
    render(<PrototypePipelineView agents={[PLAN_AGENT, BUILD_DONE]} pipelineState={makeState(true, 1)} />);

    // buildTrulyDone is false → checklist shows the real completed count, NOT all-done.
    expect(screen.getByText("1/3 done")).toBeInTheDocument();
    expect(screen.queryByText("3/3 done")).toBeNull();
    expect(screen.queryByText(/All 3 tasks completed/i)).toBeNull();
  });

  it("TERMINAL: build 'done' after the run has ended marks all tasks complete", () => {
    // Same fixtures but the run is no longer running (build was the last agent).
    render(<PrototypePipelineView agents={[PLAN_AGENT, BUILD_DONE]} pipelineState={makeState(false, 1)} />);

    // buildTrulyDone is true → the checklist + summary both show all tasks complete.
    expect(screen.getByText("3/3 done")).toBeInTheDocument();
    expect(screen.getByText(/All 3 tasks completed/i)).toBeInTheDocument();
  });
});
