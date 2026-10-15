import { describe, expect, it } from "vitest";
import { runFrames, type ReducerFrame } from "/Users/bilala/Developer/Projects/VELOCITY-AI-worktrees/feat-user-stories-v2/frontend/src/hooks/__fixtures__/reducerHarness";

const ROSTER = [{ id: "wave-step", name: "Screen Builders", role: "Builder", icon: "x", order: 1 }];
const HEAD: ReducerFrame[] = [
  { type: "pipeline_start", pipeline_type: "prototype", pipeline_run_id: "run-1", resume_offset: 0, agents: ROSTER },
  { type: "agent_start", agent_id: "wave-step" },
];
const stateRunning = () => runFrames([...HEAD,
  { type: "agent_start", agent_id: "wave-step", task_id: "task-1", wave_index: 0, worker_index: 0, wave_total: 50 }]);

describe("which matcher survives the 30-key WaveWorkerEntry", () => {
  it("A. the entry has 30 keys, only 6 defined: the 5 asserted + startedAt (24 are undefined)", () => {
    const w = stateRunning().agents[0].waveWorkers![0] as Record<string, unknown>;
    const defined = Object.keys(w).filter((k) => w[k] !== undefined).sort();
    console.log("TOTAL KEYS", Object.keys(w).length, "DEFINED KEYS", JSON.stringify(defined));
    expect(defined).toEqual(["startedAt","status","taskId","waveIndex","waveTotal","workerIndex"]);
  });
  it("B. toEqual as written FAILS (current test)", () => {
    expect(() => expect(stateRunning().agents[0].waveWorkers).toEqual([
      { taskId: "task-1", status: "running", workerIndex: 0, waveIndex: 0, waveTotal: 50 },
    ])).toThrow();
  });
  it("C. toEqual PASSES once startedAt is stripped -> the 24 undefined keys are ignored by toEqual", () => {
    const w = { ...(stateRunning().agents[0].waveWorkers![0] as Record<string, unknown>) };
    delete w.startedAt;
    expect([w]).toEqual([{ taskId: "task-1", status: "running", workerIndex: 0, waveIndex: 0, waveTotal: 50 }]);
  });
  it("D. toEqual with startedAt: expect.any(Number) PASSES", () => {
    expect(stateRunning().agents[0].waveWorkers).toEqual([
      { taskId: "task-1", status: "running", workerIndex: 0, waveIndex: 0, waveTotal: 50, startedAt: expect.any(Number) },
    ]);
  });
  it("E. toMatchObject PASSES with the 5 asserted fields", () => {
    expect(stateRunning().agents[0].waveWorkers).toMatchObject([
      { taskId: "task-1", status: "running", workerIndex: 0, waveIndex: 0, waveTotal: 50 },
    ]);
  });
  it("F. toMatchObject still FAILS on a duplicate row (array length is enforced)", () => {
    const dup = runFrames([...HEAD,
      { type: "agent_start", agent_id: "wave-step", task_id: "task-1", wave_index: 0, worker_index: 0, wave_total: 50 },
      { type: "agent_start", agent_id: "wave-step", task_id: "task-2", wave_index: 0, worker_index: 1, wave_total: 50 }]);
    expect(() => expect(dup.agents[0].waveWorkers).toMatchObject([
      { taskId: "task-1", status: "running", workerIndex: 0, waveIndex: 0, waveTotal: 50 },
    ])).toThrow();
  });
  it("G. toMatchObject still FAILS on a wrong status / wrong field value", () => {
    expect(() => expect(stateRunning().agents[0].waveWorkers).toMatchObject([
      { taskId: "task-1", status: "done", workerIndex: 0, waveIndex: 0, waveTotal: 50 },
    ])).toThrow();
  });
});
