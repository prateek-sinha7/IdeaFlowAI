/**
 * Wave worker nesting — a wave clones one agent N times, so every worker's
 * agent_start/agent_complete carries the SAME agent_id as the parent step.
 * Stamped (per-worker) events additionally carry `task_id`; the reducer must
 * fold those into `agents[].waveWorkers` (child rows) rather than re-running
 * the parent's own start/complete reset — a wave step must stay ONE node.
 *
 * Also covers `wave_skipped` (a wave that ran with zero tasks) and
 * `wave_repair` (dropped tasks the engine caught and re-dispatched).
 */
import { describe, expect, it } from "vitest";
import { runFrames, type ReducerFrame } from "./__fixtures__/reducerHarness";

const ROSTER = [{ id: "wave-step", name: "Screen Builders", role: "Builder", icon: "🤖", order: 1 }];

const HEAD: ReducerFrame[] = [
  {
    type: "pipeline_start",
    pipeline_type: "prototype",
    pipeline_run_id: "run-1",
    resume_offset: 0,
    agents: ROSTER,
  },
  // The parent's OWN agent_start — no task_id.
  { type: "agent_start", agent_id: "wave-step" },
];

/**
 * The FULL WaveWorkerEntry shape (types/index.ts) the reducer builds for a bare
 * stamped start/complete — every declared key, compared with toStrictEqual so a
 * key that is added, dropped, or starts carrying a value fails here. The per-
 * member detail fields are present-but-undefined until their own frames
 * (agent_input, tool calls, agent_complete usage) arrive; `startedAt` is the
 * reducer's wall-clock stamp, so only its type is pinned.
 */
function workerEntry(core: {
  taskId: string;
  status: "running" | "done" | "failed" | "stranded";
  workerIndex: number;
  waveIndex: number;
  waveTotal: number;
}) {
  return {
    ...core,
    taskAuthorId: undefined,
    error: undefined,
    toolCalls: undefined,
    thinking: undefined,
    contextSources: undefined,
    output: undefined,
    inputPrompt: undefined,
    estimatedCostUsd: undefined,
    attachedSkills: undefined,
    attachedHooks: undefined,
    validationIssues: undefined,
    validationPassed: undefined,
    inputTokens: undefined,
    outputTokens: undefined,
    totalTokens: undefined,
    modelId: undefined,
    cacheReadTokens: undefined,
    cacheWriteTokens: undefined,
    earlierInputTokens: undefined,
    earlierOutputTokens: undefined,
    earlierTotalTokens: undefined,
    earlierCacheReadTokens: undefined,
    earlierCacheWriteTokens: undefined,
    startedAt: expect.any(Number),
    durationMs: undefined,
  };
}

describe("wave worker nesting (agent_start/agent_complete with task_id)", () => {
  it("folds a worker's agent_start into the parent's waveWorkers, not a second agent row", () => {
    const state = runFrames([
      ...HEAD,
      { type: "agent_start", agent_id: "wave-step", task_id: "task-1", wave_index: 0, worker_index: 0, wave_total: 50 },
    ]);

    expect(state.agents).toHaveLength(1);
    expect(state.agents[0].status).toBe("running");
    expect(state.agents[0].waveWorkers).toStrictEqual([
      workerEntry({ taskId: "task-1", status: "running", workerIndex: 0, waveIndex: 0, waveTotal: 50 }),
    ]);
  });

  it("a worker's agent_complete marks its own child row done without touching the parent's status", () => {
    const state = runFrames([
      ...HEAD,
      { type: "agent_start", agent_id: "wave-step", task_id: "task-1", wave_index: 0, worker_index: 0, wave_total: 2 },
      { type: "agent_complete", agent_id: "wave-step", task_id: "task-1", wave_index: 0, worker_index: 0, wave_total: 2 },
    ]);

    expect(state.agents).toHaveLength(1);
    // The parent's own agent_complete never fired — it must still read "running".
    expect(state.agents[0].status).toBe("running");
    expect(state.agents[0].waveWorkers).toStrictEqual([
      workerEntry({ taskId: "task-1", status: "done", workerIndex: 0, waveIndex: 0, waveTotal: 2 }),
    ]);
  });

  it("many workers of the same wave upsert into distinct child rows, keyed by task_id", () => {
    const state = runFrames([
      ...HEAD,
      { type: "agent_start", agent_id: "wave-step", task_id: "task-1", wave_index: 0, worker_index: 0, wave_total: 3 },
      { type: "agent_start", agent_id: "wave-step", task_id: "task-2", wave_index: 0, worker_index: 1, wave_total: 3 },
      { type: "agent_complete", agent_id: "wave-step", task_id: "task-1", wave_index: 0, worker_index: 0, wave_total: 3 },
    ]);

    expect(state.agents[0].waveWorkers).toHaveLength(2);
    const byId = Object.fromEntries((state.agents[0].waveWorkers ?? []).map((w) => [w.taskId, w]));
    expect(byId["task-1"].status).toBe("done");
    expect(byId["task-2"].status).toBe("running");
  });

  it("the parent's own agent_complete (no task_id) completes the parent, leaving waveWorkers as-is", () => {
    const state = runFrames([
      ...HEAD,
      { type: "agent_start", agent_id: "wave-step", task_id: "task-1", wave_index: 0, worker_index: 0, wave_total: 1 },
      { type: "agent_complete", agent_id: "wave-step", task_id: "task-1", wave_index: 0, worker_index: 0, wave_total: 1 },
      { type: "agent_complete", agent_id: "wave-step" },
    ]);

    expect(state.agents[0].status).toBe("done");
    expect(state.agents[0].waveWorkers).toHaveLength(1);
  });

  // Defensive — the backend stamp may not be merged yet: today's plain
  // agent_start/agent_complete (no task_id at all) must render exactly as
  // before, with no waveWorkers array ever appearing.
  it("is a no-op when the backend has not stamped task_id yet (today's events)", () => {
    const state = runFrames(HEAD);
    expect(state.agents[0].waveWorkers).toBeUndefined();
  });
});

describe("wave/fan-out model id", () => {
  const HAIKU = "eu.anthropic.claude-haiku-4-5-20251001-v1:0";

  it("records each member's model and lends the first one to the step, whose own agent_start has none", () => {
    const state = runFrames([
      ...HEAD,
      { type: "agent_start", agent_id: "wave-step", task_id: "task-1", wave_index: 0, worker_index: 0, model_id: HAIKU },
    ]);

    expect(state.agents[0].waveWorkers?.[0].modelId).toBe(HAIKU);
    expect(state.agents[0].modelId).toBe(HAIKU);
  });

  it("keeps the step's model when the step's own agent_complete has none", () => {
    const state = runFrames([
      ...HEAD,
      { type: "agent_start", agent_id: "wave-step", task_id: "task-1", wave_index: 0, worker_index: 0, model_id: HAIKU },
      { type: "agent_complete", agent_id: "wave-step", task_id: "task-1", wave_index: 0, worker_index: 0, model_id: HAIKU },
      { type: "agent_complete", agent_id: "wave-step" },
    ]);

    expect(state.agents[0].status).toBe("done");
    expect(state.agents[0].modelId).toBe(HAIKU);
  });

  it("keeps a member's model when its agent_complete arrives without one", () => {
    const state = runFrames([
      ...HEAD,
      { type: "agent_start", agent_id: "wave-step", task_id: "task-1", wave_index: 0, worker_index: 0, model_id: HAIKU },
      { type: "agent_complete", agent_id: "wave-step", task_id: "task-1", wave_index: 0, worker_index: 0 },
    ]);

    expect(state.agents[0].waveWorkers?.[0].modelId).toBe(HAIKU);
  });
});

describe("wave_skipped — a wave that ran with zero tasks", () => {
  it("flags the parent agent without altering its status", () => {
    const state = runFrames([
      ...HEAD,
      { type: "agent_complete", agent_id: "wave-step" },
      { type: "wave_skipped", agent_id: "wave-step", step: "wave-step", reason: "no eligible tasks", source_step: "planner" },
    ]);

    expect(state.agents[0].status).toBe("done");
    expect(state.agents[0].waveSkipped).toEqual({ reason: "no eligible tasks", sourceStep: "planner" });
  });
});

describe("wave_repair — dropped tasks re-dispatched", () => {
  it("flags the parent agent with the repair detail", () => {
    const state = runFrames([
      ...HEAD,
      { type: "wave_repair", agent_id: "wave-step", wave_index: 2, missing_task_ids: ["task-9", "task-10"], count: 2 },
    ]);

    expect(state.agents[0].waveRepair).toEqual({ waveIndex: 2, missingTaskIds: ["task-9", "task-10"], count: 2 });
  });
});
