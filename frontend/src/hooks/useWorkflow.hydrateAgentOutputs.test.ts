/**
 * useWorkflow.hydrateAgentOutputs — a finished run replayed WITHOUT its
 * agent_chunk/agent_thinking deltas gets its Steps text from the persisted
 * `agent_outputs` rows (plan D3). Real hook + reducer run; only the REST
 * transport boundaries (`@/lib/api`, `@/providers/RunConnectionProvider`) are
 * mocked, mirroring useWorkflow.hook.test.ts.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useWorkflow } from "./useWorkflow";

vi.mock("@/lib/api", () => ({
  getToken: vi.fn(() => "tok"),
  postAnswers: vi.fn(),
}));

vi.mock("@/providers/RunConnectionProvider", () => ({
  useRunConnection: () => ({ sendCommand: vi.fn() }),
}));

type Msg = { type: string; [key: string]: unknown };

const ROSTER = [
  { id: "plan", name: "Plan", role: "r", icon: "", order: 0 },
  { id: "wave", name: "Wave", role: "r", icon: "", order: 1 },
];

function setup() {
  const hook = renderHook(() => useWorkflow());
  const emit = (msg: Msg) => {
    act(() => {
      hook.result.current.handleMessage(msg);
    });
  };
  const agent = (id: string) => hook.result.current.pipelineState.agents.find((a) => a.id === id)!;
  return { hook, emit, agent };
}

beforeEach(() => {
  sessionStorage.clear();
});

describe("useWorkflow hydrateAgentOutputs", () => {
  it("fills step and worker output when replayed lifecycle frames carry no deltas", () => {
    const { hook, emit, agent } = setup();
    emit({ type: "pipeline_start", pipeline_run_id: "r1", pipeline_type: "custom", agents: ROSTER });
    emit({ type: "agent_start", agent_id: "plan", event_id: "e1", seq: 1 });
    emit({ type: "agent_complete", agent_id: "plan", event_id: "e2", seq: 2 });
    emit({ type: "agent_start", agent_id: "wave", event_id: "e3", seq: 3 });
    emit({ type: "agent_start", agent_id: "wave", task_id: "t1", event_id: "e4", seq: 4 });
    emit({ type: "agent_complete", agent_id: "wave", task_id: "t1", event_id: "e5", seq: 5 });
    emit({ type: "agent_complete", agent_id: "wave", event_id: "e6", seq: 6 });
    expect(agent("plan").output).toBe("");

    act(() => {
      hook.result.current.hydrateAgentOutputs([
        { agent_id: "plan", output: "the plan", thinking_text: "hmm" },
        { agent_id: "wave", task_id: "t1", output: "worker text", thinking_text: "w-think" },
        { agent_id: "wave", output: "", thinking_text: "" },
      ]);
    });

    expect(agent("plan")).toMatchObject({ output: "the plan", thinkingText: "hmm", status: "done" });
    expect(agent("wave").waveWorkers?.[0]).toMatchObject({
      taskId: "t1",
      output: "worker text",
      thinking: "w-think",
      status: "done",
    });
  });

  it("keeps the same state object when the rows change nothing", () => {
    const { hook, emit } = setup();
    emit({ type: "pipeline_start", pipeline_run_id: "r1", pipeline_type: "custom", agents: ROSTER });
    const before = hook.result.current.pipelineState;

    act(() => {
      hook.result.current.hydrateAgentOutputs([{ agent_id: "unknown", output: "x" }]);
    });

    expect(hook.result.current.pipelineState).toBe(before);
  });

  it("returns a stable hydrateAgentOutputs across renders", () => {
    const { hook, emit } = setup();
    const first = hook.result.current.hydrateAgentOutputs;
    emit({ type: "pipeline_start", pipeline_run_id: "r1", pipeline_type: "custom", agents: ROSTER });
    expect(hook.result.current.hydrateAgentOutputs).toBe(first);
  });
});
