/**
 * useWorkflow — public hook contract and the handlePipelineMessage reducer
 * cases not exercised by the other colocated useWorkflow.*.test.ts files.
 * Real hook + reducer logic runs; only the REST transport boundaries
 * (`@/lib/api`, `@/providers/RunConnectionProvider`) are mocked.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import {
  advanceTimeline,
  applyTerminalStatus,
  deriveSpecRevisionCount,
  terminalMarkers,
  useWorkflow,
} from "./useWorkflow";
import type { PipelineRunState } from "@/types/index";

const mocks = vi.hoisted(() => ({
  getToken: vi.fn(),
  postAnswers: vi.fn(),
  sendCommand: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  getToken: mocks.getToken,
  postAnswers: mocks.postAnswers,
}));

const connection = vi.hoisted(() => ({ value: null as unknown }));
vi.mock("@/providers/RunConnectionProvider", () => ({
  useRunConnection: () => connection.value,
}));

type Msg = { type: string; [key: string]: unknown };

const ROSTER = [
  { id: "a1", name: "One", role: "r", icon: "", order: 0 },
  { id: "a2", name: "Two", role: "r", icon: "X", order: 1 },
  { id: "a3", name: "Three", role: "r", icon: "Y", order: 2 },
];

function setup() {
  const hook = renderHook(() => useWorkflow());
  const emit = (msg: Msg): boolean => {
    let handled = false;
    act(() => {
      handled = hook.result.current.handleMessage(msg);
    });
    return handled;
  };
  const state = () => hook.result.current.pipelineState;
  const agent = (id: string) => state().agents.find((a) => a.id === id)!;
  const start = (extra: Record<string, unknown> = {}) =>
    emit({ type: "pipeline_start", pipeline_type: "custom", agents: ROSTER, ...extra });
  return { hook, emit, state, agent, start };
}

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  mocks.getToken.mockReturnValue("tok");
  mocks.postAnswers.mockResolvedValue(undefined);
  mocks.sendCommand.mockResolvedValue("run-9");
  connection.value = { sendCommand: mocks.sendCommand };
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("useWorkflow hook API", () => {
  it("starts idle with an empty roster", () => {
    const { hook } = setup();
    expect(hook.result.current.isRunning).toBe(false);
    expect(hook.result.current.pipelineState).toEqual({
      isRunning: false,
      pipeline_type: "",
      agents: [],
      currentAgentIndex: -1,
      totalDuration: null,
      completedCount: 0,
      clarifications: [],
    });
  });

  it("startPipeline posts a bare run_pipeline payload and returns the run id", async () => {
    const { hook, state } = setup();
    let id: string | null = null;
    await act(async () => {
      id = await hook.result.current.startPipeline("custom", "build it");
    });
    expect(id).toBe("run-9");
    expect(mocks.sendCommand).toHaveBeenCalledWith(null, {
      type: "run_pipeline",
      pipeline_type: "custom",
      message: "build it",
    });
    expect(state().isRunning).toBe(true);
    expect(state().pipeline_type).toBe("custom");
  });

  it("startPipeline adds agent ids, hooks and context but strips _display_title", async () => {
    const { hook } = setup();
    await act(async () => {
      await hook.result.current.startPipeline(
        "custom",
        "m",
        ["a1", "a2"],
        [
          { id: "h1", name: "Audit", event: "e", trigger: "t", description: "full desc" },
          { id: "h2", name: "NoDesc", event: "e2", trigger: "trig" },
        ] as never,
        { template_id: "tpl", _display_title: "secret title" },
      );
    });
    expect(mocks.sendCommand).toHaveBeenCalledWith(null, {
      type: "run_pipeline",
      pipeline_type: "custom",
      message: "m",
      agent_ids: ["a1", "a2"],
      attached_hooks: [
        { id: "h1", name: "Audit", event: "e", trigger: "t", description: "full desc" },
        { id: "h2", name: "NoDesc", event: "e2", trigger: "trig", description: "NoDesc: trig" },
      ],
      template_id: "tpl",
    });
  });

  it("startPipeline omits empty agent id and hook lists", async () => {
    const { hook } = setup();
    await act(async () => {
      await hook.result.current.startPipeline("custom", "m", [], []);
    });
    expect(mocks.sendCommand.mock.calls[0][1]).toEqual({
      type: "run_pipeline",
      pipeline_type: "custom",
      message: "m",
    });
  });

  it("resetPipeline returns to the initial state", async () => {
    const { hook, state } = setup();
    await act(async () => {
      await hook.result.current.startPipeline("custom", "m");
    });
    act(() => hook.result.current.resetPipeline());
    expect(state().isRunning).toBe(false);
    expect(state().pipeline_type).toBe("");
  });

  it("submitQuestionnaire posts answers with the stored token", () => {
    const { hook } = setup();
    const responses = [{ question_id: "q1", answer: "yes" }];
    act(() => hook.result.current.submitQuestionnaire("run-1", responses, true));
    expect(mocks.postAnswers).toHaveBeenCalledWith("tok", "run-1", {
      responses,
      skip_clarification: true,
    });
  });

  it("submitQuestionnaire falls back to an empty token and defaults skip to false", () => {
    mocks.getToken.mockReturnValue(null);
    const { hook } = setup();
    act(() => hook.result.current.submitQuestionnaire("run-1", []));
    expect(mocks.postAnswers).toHaveBeenCalledWith("", "run-1", {
      responses: [],
      skip_clarification: false,
    });
  });

  it("submitQuestionnaire logs a failed post instead of throwing", async () => {
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    const boom = new Error("nope");
    mocks.postAnswers.mockRejectedValue(boom);
    const { hook } = setup();
    act(() => hook.result.current.submitQuestionnaire("run-1", []));
    await vi.waitFor(() => expect(err).toHaveBeenCalledWith("postAnswers failed", boom));
  });

  it("retainClarifyRound appends rounds in order", () => {
    const { hook, state } = setup();
    const r1 = { round: 1 } as never;
    const r2 = { round: 2 } as never;
    act(() => hook.result.current.retainClarifyRound(r1));
    act(() => hook.result.current.retainClarifyRound(r2));
    expect(state().clarifications).toEqual([r1, r2]);
  });

  it("retainAgentEdit overwrites a known agent's output and ignores unknown ids", () => {
    const { hook, state, start, agent } = setup();
    start();
    act(() => hook.result.current.retainAgentEdit("a2", "edited"));
    expect(agent("a2").output).toBe("edited");
    const before = state();
    act(() => hook.result.current.retainAgentEdit("ghost", "x"));
    expect(state()).toBe(before);
  });

  it("reconcileTerminalStatus applies a terminal status with warnings and persisted usage", () => {
    const { hook, state, start, emit, agent } = setup();
    start();
    emit({ type: "agent_start", agent_id: "a1" });
    act(() =>
      hook.result.current.reconcileTerminalStatus("completed", ["w"], {
        total_tokens: 10,
        total_input_tokens: 6,
        total_output_tokens: 4,
        total_cache_read_tokens: 2,
        total_cache_write_tokens: 1,
        estimated_cost_usd: 0.5,
      }),
    );
    expect(state().isRunning).toBe(false);
    expect(agent("a1").status).toBe("done");
    expect(state().completedCount).toBe(3);
    expect(state().warnings).toEqual(["w"]);
    expect(state()).toMatchObject({
      totalTokens: 10,
      totalInputTokens: 6,
      totalOutputTokens: 4,
      cacheReadTokens: 2,
      cacheWriteTokens: 1,
      estimatedCostUsd: 0.5,
    });
  });

  it("reconcileTerminalStatus ignores non-terminal statuses", () => {
    const { hook, state, start } = setup();
    start();
    const before = state();
    act(() => hook.result.current.reconcileTerminalStatus("running"));
    expect(state()).toBe(before);
  });
});

describe("exported pure helpers", () => {
  const base: PipelineRunState = {
    isRunning: true,
    pipeline_type: "c",
    agents: [],
    currentAgentIndex: -1,
    totalDuration: null,
    completedCount: 0,
  };
  const agentOf = (id: string, status: string) =>
    ({ id, name: id, role: "r", icon: "", status, output: "", thinking: "", duration: null, error: null, index: 0 }) as never;

  it.each([
    ["completed", { isRunning: false }],
    ["diverted", { isRunning: false }],
    ["cancelled", { isRunning: false, cancelled: true }],
    ["failed", { isRunning: false, failed: true }],
    ["degraded", { isRunning: false, degraded: true }],
  ])("terminalMarkers(%s) yields the documented markers", (status, expected) => {
    expect(terminalMarkers(status)).toEqual(expected);
  });

  it("deriveSpecRevisionCount counts head restarts beyond the first", () => {
    const agents = [agentOf("h", "done")];
    expect(deriveSpecRevisionCount(undefined)).toBe(0);
    expect(deriveSpecRevisionCount({ agents: [] })).toBe(0);
    expect(deriveSpecRevisionCount({ agents, agentStartEventIds: { h: ["e1"] } })).toBe(0);
    expect(deriveSpecRevisionCount({ agents })).toBe(0);
    expect(deriveSpecRevisionCount({ agents, agentStartEventIds: { h: ["e1", "e2", "e3"] } })).toBe(2);
  });

  it("applyTerminalStatus on failure idles animating agents but keeps done/error ones", () => {
    const next = applyTerminalStatus(
      { ...base, agents: [agentOf("r", "running"), agentOf("t", "thinking"), agentOf("d", "done"), agentOf("e", "error"), agentOf("i", "idle")] },
      "failed",
    );
    expect(next.agents.map((a) => a.status)).toEqual(["idle", "idle", "done", "error", "idle"]);
    expect(next.failed).toBe(true);
    expect(next.completedCount).toBe(1);
    expect(next.warnings).toBeUndefined();
  });

  it("applyTerminalStatus returns the same object for an unknown status", () => {
    expect(applyTerminalStatus(base, "bogus")).toBe(base);
  });

  it("advanceTimeline seeds the cursor, then splits busy and waiting time", () => {
    const t0 = "2024-01-01T00:00:00Z";
    const seeded = advanceTimeline(base, t0);
    expect(seeded.timelineTs).toBe(t0);
    const busy = advanceTimeline(
      { ...seeded, agents: [agentOf("r", "running")] },
      "2024-01-01T00:00:10Z",
    );
    expect(busy).toMatchObject({ busySeconds: 10, waitingSeconds: 0 });
    const waiting = advanceTimeline(
      { ...busy, agents: [agentOf("d", "done")], gateOpen: true },
      "2024-01-01T00:00:15Z",
    );
    expect(waiting).toMatchObject({ busySeconds: 10, waitingSeconds: 5 });
    const idleNoGate = advanceTimeline({ ...waiting, gateOpen: false }, "2024-01-01T00:00:20Z");
    expect(idleNoGate).toMatchObject({ busySeconds: 10, waitingSeconds: 5 });
  });

  it("advanceTimeline ignores invalid, same-instant and out-of-order timestamps", () => {
    const seeded = advanceTimeline(base, "2024-01-01T00:00:10Z");
    expect(advanceTimeline(seeded, "garbage")).toBe(seeded);
    expect(advanceTimeline(seeded, "2024-01-01T00:00:10Z")).toBe(seeded);
    expect(advanceTimeline(seeded, "2024-01-01T00:00:01Z")).toBe(seeded);
  });
});

describe("handlePipelineMessage via useWorkflow.handleMessage", () => {
  it("returns false for an unknown frame type", () => {
    const { emit } = setup();
    expect(emit({ type: "totally_unknown" })).toBe(false);
  });

  it("pipeline_start builds the roster, defaults icons and persists the run id", () => {
    const { emit, state, agent } = setup();
    expect(
      emit({ type: "pipeline_start", pipeline_type: "custom", pipeline_run_id: "r1", created_at: "2024-01-01", agents: ROSTER }),
    ).toBe(true);
    expect(state()).toMatchObject({ isRunning: true, pipelineRunId: "r1", createdAt: "2024-01-01", currentAgentIndex: 0 });
    expect(agent("a1").icon).toBe("🤖");
    expect(agent("a2").icon).toBe("X");
    expect(state().agents.map((a) => a.status)).toEqual(["idle", "idle", "idle"]);
    expect(sessionStorage.getItem("active_pipeline_run_id")).toBe("r1");
    expect(sessionStorage.getItem("active_pipeline_type")).toBe("custom");
  });

  it("pipeline_start reads the run id from nested data and tolerates a missing roster", () => {
    const { emit, state } = setup();
    emit({ type: "pipeline_start", data: { pipeline_run_id: "nested" } });
    expect(state().pipelineRunId).toBe("nested");
    expect(state().agents).toEqual([]);
  });

  it("pipeline_start with resume_offset marks earlier agents done", () => {
    const { emit, state } = setup();
    emit({ type: "pipeline_start", agents: ROSTER, resume_offset: 2 });
    expect(state().agents.map((a) => a.status)).toEqual(["done", "done", "idle"]);
    expect(state().completedCount).toBe(2);
    expect(state().currentAgentIndex).toBe(2);
  });

  it("pipeline_start re-announcing the same run keeps live agent state and resets stale errors", () => {
    const { emit, state, agent } = setup();
    emit({ type: "pipeline_start", pipeline_run_id: "r1", agents: ROSTER });
    emit({ type: "agent_start", agent_id: "a1" });
    emit({ type: "agent_chunk", agent_id: "a1", chunk: "kept" });
    emit({ type: "agent_error", agent_id: "a2", error: "boom" });
    emit({ type: "task_progress", completed_tasks: [{ number: 1, title: "t", summary: "s" }] });
    emit({ type: "pipeline_start", pipeline_run_id: "r1", agents: ROSTER, resume_offset: 2 });
    expect(agent("a1").output).toBe("kept");
    expect(agent("a2")).toMatchObject({ status: "done", error: null });
    expect(state().protoCompletedTasks).toHaveLength(1);
    expect(state().agentStartEventIds).toEqual({ a1: ["unstamped:0"] });
  });

  it("pipeline_start for a different run clears per-run accumulators", () => {
    const { emit, state } = setup();
    emit({ type: "pipeline_start", pipeline_run_id: "r1", agents: ROSTER });
    emit({ type: "task_progress", completed_tasks: [{ number: 1, title: "t", summary: "s" }] });
    emit({ type: "pipeline_cancelled" });
    emit({ type: "pipeline_start", pipeline_run_id: "r2", agents: ROSTER });
    expect(state().protoCompletedTasks).toEqual([]);
    expect(state().cancelled).toBeUndefined();
    expect(state().agentStartEventIds).toEqual({});
  });

  it("agent lifecycle: start, thinking, chunk, complete accumulate and total tokens", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2024-01-01T00:00:00Z"));
    const { emit, state, agent } = setup();
    emit({ type: "pipeline_start", agents: ROSTER });
    emit({ type: "agent_start", agent_id: "a1", model_id: "m1", visit_count: 0 });
    expect(agent("a1")).toMatchObject({ status: "running", modelId: "m1", passCount: 1, visitCount: 0 });
    emit({ type: "agent_thinking", agent_id: "a1", thinking: "ab" });
    emit({ type: "agent_thinking", agent_id: "a1", thinking: "cd" });
    expect(agent("a1")).toMatchObject({ status: "thinking", thinking: "cd", thinkingText: "abcd" });
    emit({ type: "agent_chunk", agent_id: "a1", chunk: "x" });
    emit({ type: "agent_chunk", agent_id: "a1" });
    emit({ type: "agent_chunk", agent_id: "a1", chunk: "y" });
    expect(agent("a1")).toMatchObject({ status: "running", output: "xy" });
    vi.setSystemTime(new Date("2024-01-01T00:00:04Z"));
    emit({
      type: "agent_complete",
      agent_id: "a1",
      input_tokens: 3,
      output_tokens: 4,
      total_tokens: 7,
      estimated_cost_usd: 0.2,
      total_cache_read_tokens: 5,
      total_cache_write_tokens: 6,
      model_id: "m2",
    });
    expect(agent("a1")).toMatchObject({
      status: "done",
      duration: 4,
      cumulativeDuration: 4,
      inputTokens: 3,
      outputTokens: 4,
      estimatedCostUsd: 0.2,
      modelId: "m2",
      thinking: "",
    });
    expect(state()).toMatchObject({
      completedCount: 1,
      totalInputTokens: 3,
      totalOutputTokens: 4,
      totalTokens: 7,
      cacheReadTokens: 5,
      cacheWriteTokens: 6,
    });
  });

  it("agent_complete prefers the server duration and works without a measured start", () => {
    const { emit, agent } = setup();
    emit({ type: "pipeline_start", agents: ROSTER });
    emit({ type: "agent_complete", agent_id: "a2", duration: 9 });
    expect(agent("a2")).toMatchObject({ duration: 9, inputTokens: 0, totalTokens: 0, modelId: undefined });
    emit({ type: "agent_complete", agent_id: "a3" });
    expect(agent("a3").duration).toBeNull();
  });

  it("ignores events addressed to unknown agents", () => {
    const { emit, state, start } = setup();
    start();
    const before = state().agents;
    for (const type of [
      "agent_start", "agent_thinking", "agent_chunk", "agent_complete", "agent_error",
      "agent_skipped", "agent_input", "agent_skills", "tool_call", "tool_result",
      "wave_skipped", "wave_repair", "gate_passed", "gate_blocked",
    ]) {
      expect(emit({ type, agent_id: "ghost" })).toBe(true);
    }
    expect(state().agents).toBe(before);
  });

  it("a backwards visit_count restart idles later non-idle agents but keeps their output", () => {
    const { emit, agent } = setup();
    emit({ type: "pipeline_start", agents: ROSTER });
    emit({ type: "agent_start", agent_id: "a1" });
    emit({ type: "agent_chunk", agent_id: "a1", chunk: "o1" });
    emit({ type: "agent_complete", agent_id: "a1" });
    emit({ type: "agent_start", agent_id: "a2" });
    emit({ type: "agent_chunk", agent_id: "a2", chunk: "o2" });
    emit({ type: "agent_complete", agent_id: "a2" });
    emit({ type: "agent_start", agent_id: "a1", visit_count: 1 });
    expect(agent("a2")).toMatchObject({ status: "idle", output: "o2" });
    expect(agent("a1")).toMatchObject({ status: "running", visitCount: 1, passCount: 2, output: "" });
  });

  it("agent_error records the message, with a default when none is given", () => {
    const { emit, agent } = setup();
    emit({ type: "pipeline_start", agents: ROSTER });
    emit({ type: "agent_error", agent_id: "a1", error: "bad" });
    emit({ type: "agent_error", agent_id: "a2" });
    expect(agent("a1")).toMatchObject({ status: "error", error: "bad" });
    expect(agent("a2").error).toBe("Unknown error");
  });

  it("agent_skipped marks the agent skipped", () => {
    const { emit, agent } = setup();
    emit({ type: "pipeline_start", agents: ROSTER });
    emit({ type: "agent_skipped", agent_id: "a3" });
    expect(agent("a3").status).toBe("skipped");
  });

  it("review gate frames toggle gateOpen without claiming the frame", () => {
    const { emit, state } = setup();
    emit({ type: "pipeline_start", agents: ROSTER });
    expect(emit({ type: "review_gate_ready" })).toBe(false);
    expect(state().gateOpen).toBe(true);
    emit({ type: "review_gate_ready" });
    expect(state().gateOpen).toBe(true);
    expect(emit({ type: "review_gate_approved" })).toBe(false);
    expect(state().gateOpen).toBe(false);
    emit({ type: "review_gate_approved" });
    expect(state().gateOpen).toBe(false);
  });

  it("timeline frames with ts accumulate waiting time while a gate is open", () => {
    const { emit, state } = setup();
    emit({ type: "pipeline_start", agents: ROSTER, ts: "2024-01-01T00:00:00Z" });
    emit({ type: "review_gate_ready", ts: "2024-01-01T00:00:01Z" });
    emit({ type: "review_gate_approved", ts: "2024-01-01T00:00:06Z" });
    expect(state().waitingSeconds).toBe(5);
    expect(state().busySeconds).toBe(0);
  });

  it("agent_start clears an open gate", () => {
    const { emit, state } = setup();
    emit({ type: "pipeline_start", agents: ROSTER });
    emit({ type: "review_gate_ready" });
    emit({ type: "agent_start", agent_id: "a1" });
    expect(state().gateOpen).toBe(false);
  });

  it("pipeline_complete resolves unfinished agents and uses event totals as fallback", () => {
    const { emit, state, agent } = setup();
    emit({ type: "pipeline_start", agents: ROSTER });
    emit({ type: "agent_start", agent_id: "a1" });
    sessionStorage.setItem("active_pipeline_run_id", "r");
    emit({
      type: "pipeline_complete",
      total_duration: 12,
      total_input_tokens: 1,
      total_output_tokens: 2,
      total_tokens: 3,
      estimated_cost_usd: 0.1,
      model_id: "mm",
      deliverable_filename: "f.md",
      deliverable_version: 2,
      warnings: ["loop cap"],
    });
    expect(state().agents.every((a) => a.status === "done")).toBe(true);
    expect(agent("a1").thinking).toBe("");
    expect(state()).toMatchObject({
      isRunning: false,
      totalDuration: 12,
      totalInputTokens: 1,
      totalOutputTokens: 2,
      totalTokens: 3,
      estimatedCostUsd: 0.1,
      modelId: "mm",
      deliverableFilename: "f.md",
      deliverableVersion: 2,
      warnings: ["loop cap"],
      completedCount: 3,
      degraded: undefined,
    });
    expect(sessionStorage.getItem("active_pipeline_run_id")).toBeNull();
  });

  it("pipeline_complete ignores an empty warnings array", () => {
    const { emit, state } = setup();
    emit({ type: "pipeline_complete", warnings: [] });
    expect(state().warnings).toBeUndefined();
    expect(state().totalDuration).toBeNull();
  });

  it("degraded pipeline_complete marks failed agents as errors", () => {
    const { emit, state, agent } = setup();
    emit({ type: "pipeline_start", agents: ROSTER });
    emit({ type: "agent_error", agent_id: "a2", error: "own detail" });
    emit({
      type: "pipeline_complete",
      status: "degraded",
      agents_failed: ["a1", "a2"],
    });
    expect(state()).toMatchObject({ degraded: true, degradedFailedAgents: ["a1", "a2"], isRunning: false });
    expect(agent("a1")).toMatchObject({ status: "error", error: "Agent failed (run degraded)" });
    expect(agent("a2").error).toBe("own detail");
    expect(agent("a3").status).toBe("done");
  });

  it("degraded pipeline_complete without agents_failed lists none", () => {
    const { emit, state } = setup();
    emit({ type: "pipeline_complete", status: "degraded" });
    expect(state().degradedFailedAgents).toEqual([]);
  });

  it("error frame stores the reason and ignores frames without one", () => {
    const { emit, state } = setup();
    expect(emit({ type: "error" })).toBe(false);
    expect(state().pipelineError).toBeUndefined();
    expect(emit({ type: "error", error: "kaput" })).toBe(true);
    expect(state().pipelineError).toBe("kaput");
  });

  it("pipeline_failed errors the named agents and idles the animating ones", () => {
    const { emit, state, agent } = setup();
    emit({ type: "pipeline_start", agents: ROSTER });
    emit({ type: "agent_error", agent_id: "a1", error: "mine" });
    emit({ type: "agent_start", agent_id: "a3" });
    emit({ type: "agent_thinking", agent_id: "a3", thinking: "t" });
    emit({ type: "pipeline_failed", agents_failed: ["a1", "a2"], total_duration: 3 });
    expect(agent("a1").error).toBe("mine");
    expect(agent("a2")).toMatchObject({ status: "error", error: "Pipeline failed" });
    expect(agent("a3").status).toBe("idle");
    expect(state()).toMatchObject({ failed: true, isRunning: false, totalDuration: 3, failedAgents: ["a1", "a2"] });
  });

  it("pipeline_failed uses the supplied error text and defaults to no failed agents", () => {
    const { emit, state } = setup();
    emit({ type: "pipeline_failed", error: "why" });
    expect(state()).toMatchObject({ failed: true, failedAgents: [], totalDuration: null });
  });

  it("pipeline_cancelled idles running agents and reads flat or nested duration", () => {
    const { emit, state, agent } = setup();
    emit({ type: "pipeline_start", agents: ROSTER });
    emit({ type: "agent_start", agent_id: "a1" });
    emit({ type: "pipeline_cancelled", duration: 7 });
    expect(agent("a1").status).toBe("idle");
    expect(state()).toMatchObject({ cancelled: true, isRunning: false, totalDuration: 7 });
    emit({ type: "pipeline_cancelled", data: { duration: 11 } });
    expect(state().totalDuration).toBe(11);
    emit({ type: "pipeline_cancelled" });
    expect(state().totalDuration).toBeNull();
  });

  it("pipeline_diverted records the destination without a cancelled marker", () => {
    const { emit, state, agent } = setup();
    emit({ type: "pipeline_start", agents: ROSTER });
    emit({ type: "agent_start", agent_id: "a1" });
    emit({ type: "pipeline_diverted", diverted_to_run_id: "r2", diverted_to_workflow: "wf" });
    expect(agent("a1").status).toBe("idle");
    expect(state()).toMatchObject({ isRunning: false, divertedTo: { runId: "r2", workflowId: "wf" } });
    expect(state().cancelled).toBeUndefined();
  });

  it("agent_input stores prompts and context sources", () => {
    const { emit, agent } = setup();
    emit({ type: "pipeline_start", agents: ROSTER });
    emit({
      type: "agent_input",
      agent_id: "a1",
      system_prompt: "sys",
      context_message: "ctx",
      context_sources: [{ id: "s" }],
    });
    expect(agent("a1")).toMatchObject({ systemPrompt: "sys", inputPrompt: "ctx", contextSources: [{ id: "s" }] });
    emit({ type: "agent_input", agent_id: "a2" });
    expect(agent("a2")).toMatchObject({ systemPrompt: undefined, inputPrompt: undefined, contextSources: [] });
  });

  it("agent_skills stores injected skills and hooks, with empty defaults", () => {
    const { emit, agent } = setup();
    emit({ type: "pipeline_start", agents: ROSTER });
    emit({
      type: "agent_skills",
      agent_id: "a1",
      attached_skills: [{ id: "sk" }],
      attached_hooks: [{ id: "hk" }],
      skills_load_errors: ["e"],
      estimated_tokens: 42,
    });
    expect(agent("a1")).toMatchObject({
      attachedSkills: [{ id: "sk" }],
      attachedHooks: [{ id: "hk" }],
      skillsLoadErrors: ["e"],
      estimatedTokens: 42,
    });
    emit({ type: "agent_skills", agent_id: "a2" });
    expect(agent("a2")).toMatchObject({ attachedSkills: [], attachedHooks: [], skillsLoadErrors: [] });
  });

  it("tool_call and tool_result pair the latest unresolved call of the same tool", () => {
    const { emit, agent } = setup();
    emit({ type: "pipeline_start", agents: ROSTER });
    emit({ type: "tool_call", agent_id: "a1", tool: "read", args: { p: 1 } });
    emit({ type: "tool_call", agent_id: "a1", tool: "read" });
    emit({ type: "tool_result", agent_id: "a1", tool: "read", result: "R" });
    emit({ type: "tool_result", agent_id: "a1", tool: "other" });
    const calls = agent("a1").toolCalls!;
    expect(calls).toHaveLength(2);
    expect(calls[0]).toMatchObject({ tool: "read", args: { p: 1 }, result: null });
    expect(calls[1]).toMatchObject({ tool: "read", args: {}, result: "R" });
  });

  it("hook_run appends audit entries with defaults", () => {
    const { emit, state } = setup();
    emit({ type: "hook_run", data: { hook: "h", event: "e", outcome: "block", timestamp: "T" } });
    emit({ type: "hook_run" });
    expect(state().hookRuns).toHaveLength(2);
    expect(state().hookRuns![0]).toMatchObject({ hook: "h", event: "e", outcome: "block", created_at: "T" });
    expect(state().hookRuns![1]).toMatchObject({ hook: "audit_logger", event: "", outcome: "continue" });
  });

  it("planner frames drive plannerStatus, summary and the execution gate", () => {
    const { emit, state } = setup();
    emit({ type: "planner_start", data: { pipeline_run_id: "pr" } });
    expect(state()).toMatchObject({ isRunning: true, pipelineRunId: "pr", plannerStatus: "running" });
    expect(sessionStorage.getItem("active_pipeline_run_id")).toBe("pr");
    emit({ type: "planner_complete", data: { planning_context: { inferred_intent: "intent", execution_gate: "CLARIFY_REQUIRED" } } });
    expect(state()).toMatchObject({ plannerStatus: "complete", plannerSummary: "intent", executionGate: "CLARIFY_REQUIRED" });
    emit({ type: "planner_complete", data: { execution_gate: "PROCEED" } });
    expect(state()).toMatchObject({ plannerSummary: "intent", executionGate: "PROCEED" });
    emit({ type: "planner_timeout" });
    expect(state().plannerStatus).toBe("timeout");
    emit({ type: "planner_error" });
    expect(state().plannerStatus).toBe("error");
  });

  it("planner_start without a run id leaves storage and id untouched; planner_complete defaults to PROCEED", () => {
    const { emit, state } = setup();
    emit({ type: "planner_start" });
    expect(state().pipelineRunId).toBeUndefined();
    expect(sessionStorage.getItem("active_pipeline_run_id")).toBeNull();
    emit({ type: "planner_complete" });
    expect(state().executionGate).toBe("PROCEED");
  });

  it("gate_status sets the execution gate from nested or flat verdicts", () => {
    const { emit, state } = setup();
    emit({ type: "gate_status", data: { verdict: "CLARIFY_REQUIRED" } });
    expect(state().executionGate).toBe("CLARIFY_REQUIRED");
    emit({ type: "gate_status" });
    expect(state().executionGate).toBe("PROCEED");
  });

  it("task_progress merges tasks by number and never lowers the count", () => {
    const { emit, state } = setup();
    const t = (n: number, title: string) => ({ number: n, title, summary: "" });
    emit({ type: "task_progress", completed_tasks: [t(2, "b"), t(1, "a")], completed_count: 2 });
    expect(state().protoCompletedTasks!.map((x) => x.number)).toEqual([1, 2]);
    emit({ type: "task_progress", completed_tasks: [t(3, "c"), t(2, "b2")] });
    expect(state().protoCompletedTasks!.map((x) => x.title)).toEqual(["a", "b2", "c"]);
    expect(state().protoCompletedTaskCount).toBe(3);
    emit({ type: "task_progress" });
    expect(state().protoCompletedTaskCount).toBe(3);
  });

  it("task_loop_progress extracts planned task titles on the first iteration", () => {
    const { emit, state } = setup();
    emit({ type: "pipeline_start", agents: ROSTER });
    emit({ type: "agent_start", agent_id: "a1" });
    emit({ type: "agent_chunk", agent_id: "a1", chunk: "## Task 1: Alpha\n## Task 2: Beta\n" });
    emit({ type: "task_loop_progress", task_number: 1, total_tasks: 2, agent_id: "a2" });
    expect(state().protoPlannedTasks).toEqual([
      { number: 1, title: "Alpha" },
      { number: 2, title: "Beta" },
    ]);
    expect(state()).toMatchObject({ protoTotalTasks: 2, protoCurrentTask: 1, protoTaskAgentId: "a2", protoCompletedTaskCount: 0 });
    emit({ type: "task_loop_progress", task_number: 3, total_tasks: 1 });
    expect(state()).toMatchObject({ protoCompletedTaskCount: 2, protoTotalTasks: 2, protoCurrentTask: 3, protoTaskAgentId: "a2" });
  });

  it("task_loop_progress leaves planned tasks unset when no planner output matches", () => {
    const { emit, state } = setup();
    emit({ type: "pipeline_start", agents: ROSTER });
    emit({ type: "task_loop_progress", task_number: 1, total_tasks: 2 });
    expect(state().protoPlannedTasks).toBeUndefined();
    emit({ type: "task_loop_progress" });
    expect(state().protoCurrentTask).toBe(1);
  });

  it("clarification_limit_reached and workflow_validated store their flags and edges", () => {
    const { emit, state } = setup();
    emit({ type: "clarification_limit_reached" });
    expect(state().clarificationLimitReached).toBe(true);
    emit({ type: "workflow_validated", data: { dag_edges: [{ from: "a", to: "b", artifact_type: "x" }] } });
    expect(state().dagEdges).toEqual([{ from: "a", to: "b", artifact_type: "x" }]);
    expect(state().unresolvedEdges).toEqual([]);
    emit({ type: "workflow_validated" });
    expect(state().dagEdges).toEqual([]);
  });

  it("validator_result appends issues to the owning agent and ignores empty results", () => {
    const { emit, agent } = setup();
    emit({ type: "pipeline_start", agents: ROSTER });
    emit({ type: "validator_result", data: { agent_id: "a1", issues: [{ id: 1 }] } });
    emit({ type: "validator_result", data: { agent_id: "a1", issues: [{ id: 2 }] } });
    expect(agent("a1").validationIssues).toEqual([{ id: 1 }, { id: 2 }]);
    expect(emit({ type: "validator_result", data: { agent_id: "a2", issues: [] } })).toBe(true);
    expect(emit({ type: "validator_result" })).toBe(true);
    expect(agent("a2").validationIssues).toBeUndefined();
  });

  it("gate_passed and gate_blocked set validationPassed; missing agent ids are no-ops", () => {
    const { emit, state, agent } = setup();
    emit({ type: "pipeline_start", agents: ROSTER });
    emit({ type: "gate_passed", data: { agent_id: "a1" } });
    emit({ type: "gate_blocked", data: { agent_id: "a2" } });
    expect(agent("a1").validationPassed).toBe(true);
    expect(agent("a2").validationPassed).toBe(false);
    const before = state().agents;
    emit({ type: "gate_passed" });
    emit({ type: "gate_blocked" });
    expect(state().agents).toBe(before);
  });

  it("wave_skipped and wave_repair annotate the agent with defaults", () => {
    const { emit, agent } = setup();
    emit({ type: "pipeline_start", agents: ROSTER });
    emit({ type: "wave_skipped", agent_id: "a1", reason: "nothing", source_step: "s" });
    emit({ type: "wave_skipped", agent_id: "a2" });
    expect(agent("a1").waveSkipped).toEqual({ reason: "nothing", sourceStep: "s" });
    expect(agent("a2").waveSkipped).toEqual({ reason: "", sourceStep: undefined });
    emit({ type: "wave_repair", agent_id: "a1", wave_index: 2, missing_task_ids: ["t1"], count: 1 });
    emit({ type: "wave_repair", agent_id: "a2", missing_task_ids: "bad" });
    expect(agent("a1").waveRepair).toEqual({ waveIndex: 2, missingTaskIds: ["t1"], count: 1 });
    expect(agent("a2").waveRepair).toEqual({ waveIndex: 0, missingTaskIds: [], count: 0 });
  });

  it("chain_context_unavailable and run_finalization_failed store bounded reasons", () => {
    const { emit, state } = setup();
    emit({ type: "chain_context_unavailable", data: { reason: "incompatible_backend" } });
    expect(state().chainContextUnavailableReason).toBe("incompatible_backend");
    emit({ type: "chain_context_unavailable" });
    expect(state().chainContextUnavailableReason).toBe("unknown");
    emit({ type: "run_finalization_failed", data: { reason: "degraded" } });
    expect(state().finalizationFailedReason).toBe("degraded");
    emit({ type: "run_finalization_failed" });
    expect(state().finalizationFailedReason).toBe("unknown");
  });

  it("a live pipeline_reconnected clears stale terminal markers; a pipeline_error one too", () => {
    const { emit, state } = setup();
    emit({ type: "error", error: "old" });
    emit({ type: "pipeline_reconnected", live: true });
    expect(state()).toMatchObject({ isRunning: true, pipelineError: undefined });
  });

  it("pipeline_reconnected live:false completed finalizes; failed leaves agents alone", () => {
    const { emit, state } = setup();
    emit({ type: "pipeline_start", agents: ROSTER });
    emit({ type: "pipeline_reconnected", live: false, status: "failed" });
    expect(state().isRunning).toBe(false);
    expect(state().agents.every((a) => a.status === "idle")).toBe(true);
  });

  describe("wave worker (task_id) frames", () => {
    const worker = (id: string) => ({ agent_id: "a1", task_id: id });

    it("builds a per-worker row from start, thinking, chunk, tool and input frames", () => {
      const { emit, agent } = setup();
      emit({ type: "pipeline_start", agents: ROSTER });
      emit({ type: "agent_start", ...worker("t1"), worker_index: 1, wave_index: 0, wave_total: 3, task_author_id: "au", task_block: "block" });
      emit({ type: "agent_thinking", ...worker("t1"), thinking: "hm" });
      emit({ type: "agent_chunk", ...worker("t1"), chunk: "out" });
      emit({ type: "tool_call", ...worker("t1"), tool: "grep", args: { q: 1 } });
      emit({ type: "tool_result", ...worker("t1"), tool: "grep", result: "found" });
      emit({ type: "agent_input", ...worker("t1"), context_message: "msg", context_sources: [{ id: "c" }] });
      emit({ type: "agent_skills", ...worker("t1"), attached_skills: [{ id: "s" }], attached_hooks: [{ id: "h" }] });
      const w = agent("a1").waveWorkers![0];
      expect(w).toMatchObject({
        taskId: "t1",
        status: "running",
        workerIndex: 1,
        waveIndex: 0,
        waveTotal: 3,
        taskAuthorId: "au",
        thinking: "hm",
        output: "out",
        inputPrompt: "msg",
        contextSources: [{ id: "c" }],
        attachedSkills: [{ id: "s" }],
        attachedHooks: [{ id: "h" }],
      });
      expect(w.toolCalls).toMatchObject([{ tool: "grep", result: "found" }]);
      expect(agent("a1").output).toBe("");
      expect(agent("a1").status).toBe("idle");
    });

    it("seeds a row when thinking, chunk, tool and input arrive before agent_start", () => {
      const { emit, agent } = setup();
      emit({ type: "pipeline_start", agents: ROSTER });
      emit({ type: "agent_thinking", ...worker("t1") });
      emit({ type: "agent_chunk", ...worker("t2"), chunk: "c" });
      emit({ type: "tool_call", ...worker("t3"), tool: "x" });
      emit({ type: "agent_input", ...worker("t4") });
      emit({ type: "tool_result", ...worker("missing"), tool: "x", result: "r" });
      expect(agent("a1").waveWorkers!.map((w) => w.taskId)).toEqual(["t1", "t2", "t3", "t4"]);
    });

    it("tool_result leaves earlier resolved calls alone and unmatched tools unresolved", () => {
      const { emit, agent } = setup();
      emit({ type: "pipeline_start", agents: ROSTER });
      emit({ type: "tool_call", ...worker("t1"), tool: "a" });
      emit({ type: "tool_result", ...worker("t1"), tool: "b", result: "no" });
      emit({ type: "tool_result", ...worker("t1"), tool: "a" });
      expect(agent("a1").waveWorkers![0].toolCalls).toMatchObject([{ tool: "a", result: "" }]);
    });

    it("completion keeps chunk output, uses server duration and tokens; errors mark failed", () => {
      const { emit, agent } = setup();
      emit({ type: "pipeline_start", agents: ROSTER });
      emit({ type: "agent_chunk", ...worker("t1"), chunk: "built" });
      emit({
        type: "agent_complete",
        ...worker("t1"),
        duration: 2,
        input_tokens: 1,
        output_tokens: 2,
        total_tokens: 3,
        estimated_cost_usd: 0.3,
        input_prompt: "ip",
      });
      emit({ type: "agent_error", ...worker("t2"), error: "dead" });
      const [w1, w2] = agent("a1").waveWorkers!;
      expect(w1).toMatchObject({
        status: "done",
        output: "built",
        durationMs: 2000,
        inputTokens: 1,
        outputTokens: 2,
        totalTokens: 3,
        estimatedCostUsd: 0.3,
        inputPrompt: "ip",
      });
      expect(w2).toMatchObject({ status: "failed", error: "dead" });
    });

    it("a completed worker with no server duration reports measured time only past one second", () => {
      vi.useFakeTimers();
      vi.setSystemTime(new Date("2024-01-01T00:00:00Z"));
      const { emit, agent } = setup();
      emit({ type: "pipeline_start", agents: ROSTER });
      emit({ type: "agent_start", ...worker("slow") });
      emit({ type: "agent_start", ...worker("fast") });
      vi.setSystemTime(new Date("2024-01-01T00:00:03Z"));
      emit({ type: "agent_complete", ...worker("slow") });
      emit({ type: "agent_complete", ...worker("fast") });
      const [slow, fast] = agent("a1").waveWorkers!;
      expect(slow.durationMs).toBe(3000);
      expect(fast.durationMs).toBe(3000);
      emit({ type: "agent_start", ...worker("quick") });
      emit({ type: "agent_complete", ...worker("quick") });
      expect(agent("a1").waveWorkers![2].durationMs).toBeUndefined();
    });

    it("validator_result with task_id and issues flags that worker's validation failed", () => {
      const { emit, agent } = setup();
      emit({ type: "pipeline_start", agents: ROSTER });
      emit({ type: "validator_result", data: { agent_id: "a1", task_id: "t1", issues: [{ id: 1 }] } });
      emit({ type: "validator_result", data: { agent_id: "a1", task_id: "t1", issues: [{ id: 2 }] } });
      expect(agent("a1").waveWorkers![0]).toMatchObject({ validationIssues: [{ id: 1 }, { id: 2 }], validationPassed: false });
      expect(agent("a1").validationIssues).toBeUndefined();
    });

    it("a finishing parent step strands workers that never reported", () => {
      const { emit, agent } = setup();
      emit({ type: "pipeline_start", agents: ROSTER });
      emit({ type: "agent_start", agent_id: "a1" });
      emit({ type: "agent_start", ...worker("t1") });
      emit({ type: "agent_start", ...worker("t2") });
      emit({ type: "agent_error", ...worker("t2"), error: "e2" });
      emit({ type: "agent_complete", agent_id: "a1" });
      const [w1, w2] = agent("a1").waveWorkers!;
      expect(w1).toMatchObject({ status: "stranded", error: "the step ended before this worker reported a result" });
      expect(w2.status).toBe("failed");
    });

    it("a failing parent step also strands running workers", () => {
      const { emit, agent } = setup();
      emit({ type: "pipeline_start", agents: ROSTER });
      emit({ type: "agent_start", ...worker("t1") });
      emit({ type: "agent_error", agent_id: "a1", error: "step died" });
      expect(agent("a1").status).toBe("error");
      expect(agent("a1").waveWorkers![0].status).toBe("stranded");
    });
  });

  describe("re-delivery gate for accumulating frames", () => {
    it("drops a repeated seq so output is not appended twice, and advances the cursor", () => {
      const { emit, state, agent } = setup();
      emit({ type: "pipeline_start", agents: ROSTER });
      emit({ type: "agent_chunk", agent_id: "a1", chunk: "A", seq: 1 });
      emit({ type: "agent_chunk", agent_id: "a1", chunk: "A", seq: 1 });
      emit({ type: "agent_chunk", agent_id: "a1", chunk: "B", seq: 2 });
      expect(agent("a1").output).toBe("AB");
      expect(state().lastAppliedSeq).toBe(2);
    });

    it("drops a repeated event_id when no seq is present", () => {
      const { emit, state, agent } = setup();
      emit({ type: "pipeline_start", agents: ROSTER });
      emit({ type: "agent_chunk", agent_id: "a1", chunk: "A", event_id: "e1" });
      emit({ type: "agent_chunk", agent_id: "a1", chunk: "A", event_id: "e1" });
      expect(agent("a1").output).toBe("A");
      expect(state().appliedUnsequencedIds).toEqual(["e1"]);
    });

    it("applies unstamped frames every time", () => {
      const { emit, agent } = setup();
      emit({ type: "pipeline_start", agents: ROSTER });
      emit({ type: "agent_chunk", agent_id: "a1", chunk: "A" });
      emit({ type: "agent_chunk", agent_id: "a1", chunk: "A" });
      expect(agent("a1").output).toBe("AA");
    });

    it("does not advance the cursor for a frame whose handler bailed", () => {
      const { emit, state } = setup();
      emit({ type: "pipeline_start", agents: ROSTER });
      emit({ type: "agent_chunk", agent_id: "ghost", chunk: "A", seq: 5 });
      expect(state().lastAppliedSeq).toBeUndefined();
    });

    it("records stamped agent_start identities from seq and event_id", () => {
      const { emit, state } = setup();
      emit({ type: "pipeline_start", agents: ROSTER });
      emit({ type: "agent_start", agent_id: "a1", seq: 1 });
      emit({ type: "agent_start", agent_id: "a1", event_id: "ev", seq: undefined });
      expect(state().agentStartEventIds).toEqual({ a1: ["seq:1", "ev"] });
    });
  });
});
