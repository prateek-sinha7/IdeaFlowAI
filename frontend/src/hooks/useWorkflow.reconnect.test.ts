/**
 * Phase 12 / 12-08 (RESUME-04 FE half, UAT Gap 2b) — handlePipelineMessage's
 * `pipeline_reconnected` branch. Previously the event was silently dropped, so
 * after a backend restart mid-run the FE never resolved isRunning ("running
 * forever" hang). Asserts the three branches:
 *   (1) live:false + terminal status → isRunning=false, agents finalized;
 *   (2) live:false + non-terminal status → keeps running (no premature resolve);
 *   (3) live:true → keeps running for the live tail (12-09 engine→WS attach).
 */
import { beforeEach, describe, expect, it } from "vitest";
import { handlePipelineMessage } from "./useWorkflow";
import type { AgentRunState, PipelineRunState } from "@/types/index";

function makeAgent(id: string, status: AgentRunState["status"]): AgentRunState {
  return {
    id,
    name: id,
    role: "test",
    icon: "🤖",
    status,
    output: "",
    thinking: "",
    duration: null,
    error: null,
    index: 0,
  };
}

/** Seed state: a mid-run pipeline with 2 idle agents. */
function seedState(): PipelineRunState {
  return {
    isRunning: true,
    pipeline_type: "custom",
    agents: [makeAgent("a1", "idle"), makeAgent("a2", "idle")],
    currentAgentIndex: -1,
    totalDuration: null,
    completedCount: 0,
  };
}

/**
 * Fake setPipelineState: captures functional updaters and applies them to the
 * seed so the test can inspect the resulting state. Mirrors how the hook
 * exercises handlePipelineMessage (msg + setPipelineState + ref stub).
 */
function makeHarness() {
  let state = seedState();
  let updaterCalled = false;
  const setPipelineState = ((updater: unknown) => {
    updaterCalled = true;
    state = typeof updater === "function"
      ? (updater as (p: PipelineRunState) => PipelineRunState)(state)
      : (updater as PipelineRunState);
  }) as React.Dispatch<React.SetStateAction<PipelineRunState>>;
  const agentStartTimesRef = { current: {} as Record<string, number> };
  return {
    setPipelineState,
    agentStartTimesRef,
    get state() { return state; },
    get updaterCalled() { return updaterCalled; },
  };
}

describe("handlePipelineMessage — pipeline_reconnected (12-08 Gap 2 FE half)", () => {
  beforeEach(() => {
    sessionStorage.setItem("active_pipeline_run_id", "run-1");
    sessionStorage.setItem("active_pipeline_type", "custom");
  });

  it("live:false + terminal 'completed' resolves the run (isRunning=false, agents done)", () => {
    const h = makeHarness();
    const handled = handlePipelineMessage(
      { type: "pipeline_reconnected", live: false, status: "completed", pipeline_run_id: "run-1" },
      h.setPipelineState,
      h.agentStartTimesRef,
    );

    expect(handled).toBe(true);
    expect(h.state.isRunning).toBe(false);
    expect(h.state.agents.every((a) => a.status === "done")).toBe(true);
    expect(h.state.completedCount).toBe(2);
    // Persisted run id cleared — no stale reconnect on the next load.
    expect(sessionStorage.getItem("active_pipeline_run_id")).toBeNull();
    expect(sessionStorage.getItem("active_pipeline_type")).toBeNull();
  });

  it("live:false + terminal 'failed' resolves isRunning=false but leaves agents as-is", () => {
    const h = makeHarness();
    const handled = handlePipelineMessage(
      { type: "pipeline_reconnected", live: false, status: "failed", pipeline_run_id: "run-1" },
      h.setPipelineState,
      h.agentStartTimesRef,
    );

    expect(handled).toBe(true);
    expect(h.state.isRunning).toBe(false);
    expect(h.state.agents.every((a) => a.status === "idle")).toBe(true);
    expect(sessionStorage.getItem("active_pipeline_run_id")).toBeNull();
  });

  it("live:false + non-terminal 'running' keeps isRunning true (no premature resolve)", () => {
    const h = makeHarness();
    const handled = handlePipelineMessage(
      { type: "pipeline_reconnected", live: false, status: "running", pipeline_run_id: "run-1" },
      h.setPipelineState,
      h.agentStartTimesRef,
    );

    expect(handled).toBe(true);
    expect(h.updaterCalled).toBe(false);
    expect(h.state.isRunning).toBe(true);
    // Run id stays persisted — re-replay rides the next connection cycle.
    expect(sessionStorage.getItem("active_pipeline_run_id")).toBe("run-1");
  });

  it("live:false + missing status keeps isRunning true", () => {
    const h = makeHarness();
    const handled = handlePipelineMessage(
      { type: "pipeline_reconnected", live: false, status: null, pipeline_run_id: "run-1" },
      h.setPipelineState,
      h.agentStartTimesRef,
    );

    expect(handled).toBe(true);
    expect(h.state.isRunning).toBe(true);
  });

  it("live:true keeps isRunning true and returns true (live tail will stream)", () => {
    const h = makeHarness();
    const handled = handlePipelineMessage(
      { type: "pipeline_reconnected", live: true, pipeline_run_id: "run-1" },
      h.setPipelineState,
      h.agentStartTimesRef,
    );

    expect(handled).toBe(true);
    expect(h.updaterCalled).toBe(false);
    expect(h.state.isRunning).toBe(true);
    expect(sessionStorage.getItem("active_pipeline_run_id")).toBe("run-1");
  });

  it("absent live (legacy live reconnect) keeps isRunning true and returns true", () => {
    const h = makeHarness();
    const handled = handlePipelineMessage(
      { type: "pipeline_reconnected", pipeline_run_id: "run-1", message: "Reconnected — resuming pipeline stream" },
      h.setPipelineState,
      h.agentStartTimesRef,
    );

    expect(handled).toBe(true);
    expect(h.updaterCalled).toBe(false);
    expect(h.state.isRunning).toBe(true);
  });
});
