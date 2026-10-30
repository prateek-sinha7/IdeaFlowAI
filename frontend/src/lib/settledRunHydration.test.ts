import { describe, expect, it } from "vitest";
import type { DurableFrame } from "@/lib/api";
import type { AgentRunState, PipelineRunState, WaveWorkerEntry } from "@/types/index";
import {
  applyAgentOutputs,
  canHydrateFromAgentOutputs,
  parsePersistedAgentOutputs,
  type PersistedAgentOutputRow,
} from "./settledRunHydration";

// ─────────────────────────────────────────────────────────────────
// Finished-run perf (plan D3) — the predicate that decides whether a
// delta-free replay + persisted agent_outputs reproduces the full-log Steps
// text, and the pure writer that fills it. Pure functions: no mocks.
// ─────────────────────────────────────────────────────────────────

const frame = (type: string, data: Record<string, unknown> = {}): DurableFrame => ({ type, data });
const start = (agentId: string, taskId?: string) =>
  frame("agent_start", { agent_id: agentId, ...(taskId ? { task_id: taskId } : {}) });
const complete = (agentId: string, taskId?: string) =>
  frame("agent_complete", { agent_id: agentId, ...(taskId ? { task_id: taskId } : {}) });
const error = (agentId: string, taskId?: string) =>
  frame("agent_error", { agent_id: agentId, ...(taskId ? { task_id: taskId } : {}) });
const row = (agentId: string, extra: Partial<PersistedAgentOutputRow> = {}): PersistedAgentOutputRow => ({
  agent_id: agentId,
  ...extra,
});

function agent(id: string, extra: Partial<AgentRunState> = {}): AgentRunState {
  return {
    id,
    name: id,
    role: "r",
    icon: "",
    status: "done",
    output: "",
    thinking: "",
    duration: null,
    error: null,
    index: 0,
    ...extra,
  };
}

const worker = (taskId: string, extra: Partial<WaveWorkerEntry> = {}): WaveWorkerEntry => ({
  taskId,
  status: "done",
  ...extra,
});

function state(agents: AgentRunState[]): PipelineRunState {
  return {
    isRunning: false,
    pipeline_type: "custom",
    agents,
    currentAgentIndex: -1,
    totalDuration: null,
    completedCount: 0,
    clarifications: [],
  };
}

describe("parsePersistedAgentOutputs", () => {
  it("parses the column's JSON string into rows when the value is a JSON array", () => {
    const raw = JSON.stringify([
      { agent_id: "a", output: "o", thinking_text: "t", name: "ignored" },
      { agent_id: "b", task_id: "t1" },
    ]);

    expect(parsePersistedAgentOutputs(raw)).toEqual([
      { agent_id: "a", task_id: null, output: "o", thinking_text: "t" },
      { agent_id: "b", task_id: "t1" },
    ]);
  });

  it("returns null when the string is not valid JSON", () => {
    expect(parsePersistedAgentOutputs("{not json")).toBeNull();
  });

  it.each([[undefined], [null], [{ agent_id: "a" }], [42], [JSON.stringify({ a: 1 })]])(
    "returns null when the value is not an array (%j)",
    (raw) => {
      expect(parsePersistedAgentOutputs(raw)).toBeNull();
    },
  );

  it("drops elements without a non-empty string agent_id and non-string fields", () => {
    const rows = parsePersistedAgentOutputs([
      null,
      7,
      { output: "no id" },
      { agent_id: "" },
      { agent_id: 3 },
      { agent_id: "a", task_id: 5, output: 1, thinking_text: ["x"] },
    ]);

    expect(rows).toEqual([{ agent_id: "a", task_id: null }]);
  });
});

describe("canHydrateFromAgentOutputs", () => {
  it("returns true when the log has no agent_start and no rows", () => {
    expect(canHydrateFromAgentOutputs([frame("pipeline_start"), frame("chat_message")], null)).toBe(true);
    expect(canHydrateFromAgentOutputs([], [])).toBe(true);
  });

  it("returns true when every key's starts match its rows and the last pass is closed", () => {
    const frames = [frame("pipeline_start"), start("a"), complete("a"), start("b"), error("b")];

    expect(canHydrateFromAgentOutputs(frames, [row("a"), row("b")])).toBe(true);
  });

  it("returns true when a re-run step has one row per closed pass", () => {
    const frames = [start("a"), complete("a"), start("a"), complete("a")];

    expect(canHydrateFromAgentOutputs(frames, [row("a"), row("a")])).toBe(true);
  });

  it("returns false when the key's last pass is still open", () => {
    const frames = [start("a"), complete("a"), start("a")];

    expect(canHydrateFromAgentOutputs(frames, [row("a"), row("a")])).toBe(false);
  });

  it("returns false when a start->start re-run dropped a pass from the rows", () => {
    const frames = [start("a"), start("a"), complete("a")];

    expect(canHydrateFromAgentOutputs(frames, [row("a")])).toBe(false);
  });

  it("returns false when rows are null and the log has starts", () => {
    expect(canHydrateFromAgentOutputs([start("a"), complete("a")], null)).toBe(false);
  });

  it("counts worker keys separately from the step key", () => {
    const frames = [start("w"), start("w", "t1"), complete("w", "t1"), complete("w")];

    expect(canHydrateFromAgentOutputs(frames, [row("w", { task_id: "t1" }), row("w")])).toBe(true);
    expect(canHydrateFromAgentOutputs(frames, [row("w"), row("w")])).toBe(false);
  });

  it("returns false when a row exists for a key that never started", () => {
    const frames = [start("a"), complete("a"), complete("c")];

    expect(canHydrateFromAgentOutputs(frames, [row("a"), row("b")])).toBe(false);
    expect(canHydrateFromAgentOutputs(frames, [row("a"), row("c")])).toBe(false);
  });

  it("ignores lifecycle frames without a usable agent_id", () => {
    const frames = [frame("agent_start", {}), frame("agent_start", { agent_id: "" }), start("a"), complete("a")];

    expect(canHydrateFromAgentOutputs(frames, [row("a")])).toBe(true);
  });
});

describe("applyAgentOutputs", () => {
  it("writes the LAST row of a plain step into output and thinkingText", () => {
    const prev = state([agent("a")]);

    const next = applyAgentOutputs(prev, [
      row("a", { output: "first", thinking_text: "t1" }),
      row("a", { output: "second", thinking_text: "t2" }),
    ]);

    expect(next.agents[0]).toMatchObject({ output: "second", thinkingText: "t2" });
    expect(next).not.toBe(prev);
  });

  it("changes only output when the row has no thinking and the step has none", () => {
    const prev = state([agent("a", { output: "stale" })]);

    const next = applyAgentOutputs(prev, [row("a")]);

    expect(next.agents[0].output).toBe("");
    expect(next.agents[0]).not.toHaveProperty("thinkingText");
  });

  it("changes only thinkingText when the output already matches", () => {
    const prev = state([agent("a", { output: "same", thinkingText: "old" })]);

    const next = applyAgentOutputs(prev, [row("a", { output: "same", thinking_text: "new" })]);

    expect(next.agents[0]).toMatchObject({ output: "same", thinkingText: "new" });
  });

  it("concatenates every row of a worker in order across a wave-repair re-run", () => {
    const untouched = worker("t3", { output: "keep" });
    const prev = state([agent("w", { waveWorkers: [worker("t1"), worker("t2"), untouched] })]);

    const next = applyAgentOutputs(prev, [
      row("w", { task_id: "t1", output: "a", thinking_text: "x" }),
      row("w", { task_id: "t2", output: "c" }),
      row("w", { task_id: "t1", output: "b", thinking_text: "y" }),
    ]);

    const workers = next.agents[0].waveWorkers!;
    expect(workers[0]).toMatchObject({ taskId: "t1", output: "ab", thinking: "xy" });
    expect(workers[1]).toMatchObject({ taskId: "t2", output: "c" });
    expect(workers[1]).not.toHaveProperty("thinking");
    expect(workers[2]).toBe(untouched);
  });

  it("changes only a worker's thinking when its output already matches", () => {
    const prev = state([agent("w", { waveWorkers: [worker("t1", { thinking: "old" })] })]);

    const next = applyAgentOutputs(prev, [row("w", { task_id: "t1" })]);

    expect(next.agents[0].waveWorkers![0]).toEqual({ taskId: "t1", status: "done", thinking: "" });
  });

  it("returns the same state when the rows already match", () => {
    const prev = state([
      agent("a", { output: "o", thinkingText: "t" }),
      agent("w", { waveWorkers: [worker("t1", { output: "wo", thinking: "wt" })] }),
    ]);

    const next = applyAgentOutputs(prev, [
      row("a", { output: "o", thinking_text: "t" }),
      row("w", { task_id: "t1", output: "wo", thinking_text: "wt" }),
    ]);

    expect(next).toBe(prev);
  });

  it("ignores rows for unknown agents and workers on a step without workers", () => {
    const prev = state([agent("a"), agent("w")]);

    const next = applyAgentOutputs(prev, [
      row("ghost", { output: "x" }),
      row("w", { task_id: "t9", output: "y" }),
    ]);

    expect(next).toBe(prev);
  });

  it("returns the same state when there are no rows", () => {
    const prev = state([agent("a", { output: "kept" })]);

    expect(applyAgentOutputs(prev, [])).toBe(prev);
  });
});
