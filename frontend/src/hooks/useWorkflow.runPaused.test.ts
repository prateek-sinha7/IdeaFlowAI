/**
 * handlePipelineMessage's `run_paused` branch. A paused run is non-terminal: the
 * reducer must mark it paused with the backend kind/reason and stop `isRunning`,
 * but must not set any terminal marker (cancelled / failed / degraded).
 */
import { describe, expect, it } from "vitest";
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

function seedState(): PipelineRunState {
  return {
    isRunning: true,
    pipeline_type: "custom",
    agents: [makeAgent("a1", "running"), makeAgent("a2", "done")],
    currentAgentIndex: 0,
    totalDuration: null,
    completedCount: 1,
  };
}

function run(msg: { type: string; [key: string]: unknown }, seed: PipelineRunState = seedState()) {
  let state = seed;
  const setPipelineState = ((updater: unknown) => {
    state = typeof updater === "function"
      ? (updater as (p: PipelineRunState) => PipelineRunState)(state)
      : (updater as PipelineRunState);
  }) as React.Dispatch<React.SetStateAction<PipelineRunState>>;
  const agentStartTimesRef = { current: {} as Record<string, number> };
  const handled = handlePipelineMessage(msg, setPipelineState, agentStartTimesRef);
  return { handled, state };
}

describe("handlePipelineMessage — run_paused", () => {
  it("marks the run paused with kind and reason, stops isRunning, and is handled", () => {
    const { handled, state } = run({ type: "run_paused", kind: "budget", reason: "Time budget exhausted" });
    expect(handled).toBe(true);
    expect(state.isRunning).toBe(false);
    expect(state.paused).toEqual({ kind: "budget", reason: "Time budget exhausted" });
  });

  it("sets no terminal marker (not cancelled, failed or degraded)", () => {
    const { state } = run({ type: "run_paused", kind: "credentials", reason: "401 from provider" });
    expect(state.cancelled).toBeUndefined();
    expect(state.failed).toBeUndefined();
    expect(state.degraded).toBeUndefined();
  });

  it("returns still-running agents to idle, leaving finished agents as done", () => {
    const { state } = run({ type: "run_paused", kind: "poison", reason: "Same error 3 times" });
    expect(state.agents.find((a) => a.id === "a1")?.status).toBe("idle");
    expect(state.agents.find((a) => a.id === "a2")?.status).toBe("done");
  });
});
