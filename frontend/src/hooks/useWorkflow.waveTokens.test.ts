/**
 * Wave step token transparency — a wave step never calls a model itself, so its
 * own agent_complete carries no usage. The step's total is its members' sum, and
 * a wave-repair re-run of a member (same task_id) adds to that member's usage
 * instead of replacing it.
 */
import { describe, expect, it } from "vitest";
import { runFrames, type ReducerFrame } from "./__fixtures__/reducerHarness";

const HEAD: ReducerFrame[] = [
  {
    type: "pipeline_start",
    pipeline_type: "backlog",
    pipeline_run_id: "run-1",
    resume_offset: 0,
    agents: [{ id: "wave-step", name: "Story Writers", role: "Writer", icon: "x", order: 1 }],
  },
  { type: "agent_start", agent_id: "wave-step" },
];
const start = (task: string): ReducerFrame => ({ type: "agent_start", agent_id: "wave-step", task_id: task, wave_index: 0 });
const done = (task: string, input: number, output: number): ReducerFrame => ({
  type: "agent_complete", agent_id: "wave-step", task_id: task, wave_index: 0,
  input_tokens: input, output_tokens: output, total_tokens: input + output,
  cache_read_tokens: input - 1, cache_write_tokens: 1,
});

describe("wave step token totals", () => {
  it("a running wave's finished members count in the run totals before the step ends", () => {
    const state = runFrames([...HEAD, start("a"), done("a", 100, 10), start("b")]);
    expect(state.agents[0].status).toBe("running");
    expect(state.totalInputTokens).toBe(100);
    expect(state.totalOutputTokens).toBe(10);
    expect(state.totalTokens).toBe(110);
  });

  it("the step's total is the sum of its members, re-runs included", () => {
    const state = runFrames([
      ...HEAD,
      start("a"), done("a", 100, 10),
      start("b"), done("b", 200, 20),
      // wave repair re-runs "a"
      start("a"), done("a", 50, 5),
      { type: "agent_complete", agent_id: "wave-step", waves: 1, tasks: 2 },
    ]);
    const step = state.agents[0];
    const a = step.waveWorkers!.find((w) => w.taskId === "a")!;
    expect(a.totalTokens).toBe(165);
    expect(a.inputTokens).toBe(150);
    expect(step.totalTokens).toBe(385);
    expect(step.inputTokens).toBe(350);
    expect(step.outputTokens).toBe(35);
    // the cache split follows the same members, re-runs included
    expect(a.cacheReadTokens).toBe(99 + 49);
    expect(step.cacheReadTokens).toBe(99 + 199 + 49);
    expect(step.cacheWriteTokens).toBe(3);
    expect(state.totalInputTokens).toBe(350);
  });
});
