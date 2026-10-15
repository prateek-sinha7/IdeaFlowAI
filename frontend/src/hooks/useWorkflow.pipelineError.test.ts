/**
 * Gap fix — the REST driver's generic run-failure frame
 * ({type:"error", data:{error, code:"pipeline_error", recoverable}}, run_commands.py
 * ~3420) had no `case "error"` in the reducer, so a user watching a run fail LIVE saw
 * only the generic "run stopped" message. The real reason only surfaced after history
 * re-fetched `WorkflowRun.error` on reopen. Asserts: the event sets `pipelineError`
 * verbatim; a fresh `pipeline_start` and a live `pipeline_reconnected` clear it; it
 * never clobbers a more specific per-agent `error` already set by `agent_error`.
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

function seedState(overrides: Partial<PipelineRunState> = {}): PipelineRunState {
  return {
    isRunning: true,
    pipeline_type: "custom",
    agents: [makeAgent("a1", "idle")],
    currentAgentIndex: -1,
    totalDuration: null,
    completedCount: 0,
    ...overrides,
  };
}

function makeHarness(initial: PipelineRunState = seedState()) {
  let state = initial;
  const setPipelineState = ((updater: unknown) => {
    state = typeof updater === "function"
      ? (updater as (p: PipelineRunState) => PipelineRunState)(state)
      : (updater as PipelineRunState);
  }) as React.Dispatch<React.SetStateAction<PipelineRunState>>;
  const agentStartTimesRef = { current: {} as Record<string, number> };
  return {
    setPipelineState,
    agentStartTimesRef,
    get state() { return state; },
  };
}

describe("handlePipelineMessage — top-level error frame", () => {
  it("sets pipelineError verbatim from the error event", () => {
    const h = makeHarness();
    const message = "json_tasks: could not parse task list as JSON — Expecting value: line 1 column 1 (char 0)";

    const handled = handlePipelineMessage(
      { type: "error", error: message, code: "pipeline_error", recoverable: true },
      h.setPipelineState,
      h.agentStartTimesRef,
    );

    expect(handled).toBe(true);
    expect(h.state.pipelineError).toBe(message);
  });

  it("a fresh pipeline_start clears a stale pipelineError from a prior run", () => {
    const h = makeHarness(seedState({ pipelineError: "stale error from previous run" }));

    handlePipelineMessage(
      { type: "pipeline_start", agents: [{ id: "a1", name: "a1", role: "test", icon: "🤖", order: 0 }], pipeline_run_id: "run-2" },
      h.setPipelineState,
      h.agentStartTimesRef,
    );

    expect(h.state.pipelineError).toBeUndefined();
  });

  it("a live pipeline_reconnected (resume) clears a stale pipelineError", () => {
    const h = makeHarness(seedState({ isRunning: false, pipelineError: "stale error", pipelineRunId: "run-1" }));

    handlePipelineMessage(
      { type: "pipeline_reconnected", live: true, pipeline_run_id: "run-1" },
      h.setPipelineState,
      h.agentStartTimesRef,
    );

    expect(h.state.isRunning).toBe(true);
    expect(h.state.pipelineError).toBeUndefined();
  });

  it("does not clobber a more specific per-agent error already set by agent_error", () => {
    const h = makeHarness();

    handlePipelineMessage(
      { type: "agent_error", agent_id: "a1", error: "agent-specific failure" },
      h.setPipelineState,
      h.agentStartTimesRef,
    );
    handlePipelineMessage(
      { type: "error", error: "generic pipeline failure" },
      h.setPipelineState,
      h.agentStartTimesRef,
    );

    expect(h.state.agents[0].error).toBe("agent-specific failure");
    expect(h.state.pipelineError).toBe("generic pipeline failure");
  });

  it("ignores an error event with no message (returns false, no state change)", () => {
    const h = makeHarness();

    const handled = handlePipelineMessage(
      { type: "error" },
      h.setPipelineState,
      h.agentStartTimesRef,
    );

    expect(handled).toBe(false);
    expect(h.state.pipelineError).toBeUndefined();
  });
});

// ISS-107 (QA-KB-005) — hook_run reads only msg.data; page.tsx:1570 hands the reducer a
// FLAT frame, so every field fell back to "audit_logger"/""/"continue".
describe("hook_run payload (ISS-107)", () => {
  const payload = {
    hook: "secret_scan",
    event: "before_write",
    outcome: "block",
    agent_id: "writer",
    timestamp: "2026-10-01T10:00:00.000Z",
  };
  const expectAllFive = (row: PipelineRunState["hookRuns"]) => {
    expect(row).toHaveLength(1);
    expect(row![0].hook).toBe("secret_scan");
    expect(row![0].event).toBe("before_write");
    expect(row![0].outcome).toBe("block");
    expect(row![0].created_at).toBe("2026-10-01T10:00:00.000Z");
    expect(row![0].detail).toMatchObject({ agent_id: "writer" });
  };

  it("keeps all five fields from a nested {type, data} frame", () => {
    const h = makeHarness();
    handlePipelineMessage({ type: "hook_run", data: payload }, h.setPipelineState, h.agentStartTimesRef);
    expectAllFive(h.state.hookRuns);
  });

  it("keeps all five fields from a flat frame (the shape page.tsx sends)", () => {
    const h = makeHarness();
    handlePipelineMessage({ type: "hook_run", ...payload }, h.setPipelineState, h.agentStartTimesRef);
    expectAllFive(h.state.hookRuns);
  });
});
