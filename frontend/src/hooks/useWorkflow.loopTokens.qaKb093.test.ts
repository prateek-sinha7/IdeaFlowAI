/**
 * QA-KB-093: the live run header undercounted tokens when a step ran more than once.
 *
 * Run d091ed54 (ex_A1_loop): emoji, greet, check, greet, check, done. The backend's
 * token_usage was 19815, the sum of all six agent_complete events. The live header
 * showed 13303, the LAST pass of each agent only, because agent_start resets a step's
 * token fields and agent_complete overwrites them, so a re-run's earlier pass vanished
 * from the run total. A reload read the backend total, so the two disagreed.
 */
import { describe, expect, it } from "vitest";
import { handlePipelineMessage } from "./useWorkflow";
import type { AgentRunState, PipelineRunState } from "@/types/index";

function makeAgent(id: string, index: number): AgentRunState {
  return { id, name: id, role: "test", icon: "🤖", status: "idle", output: "", thinking: "", duration: null, error: null, index };
}

function makeHarness() {
  let state: PipelineRunState = {
    isRunning: true,
    pipeline_type: "custom",
    agents: [makeAgent("emoji", 0), makeAgent("greet", 1), makeAgent("check", 2), makeAgent("done", 3)],
    currentAgentIndex: 0,
    totalDuration: null,
    completedCount: 0,
  };
  const setPipelineState = ((updater: unknown) => {
    state = typeof updater === "function"
      ? (updater as (p: PipelineRunState) => PipelineRunState)(state)
      : (updater as PipelineRunState);
  }) as React.Dispatch<React.SetStateAction<PipelineRunState>>;
  const agentStartTimesRef = { current: {} as Record<string, number> };
  return { setPipelineState, agentStartTimesRef, get state() { return state; } };
}

type H = ReturnType<typeof makeHarness>;
let seq = 0;
const send = (h: H, msg: Record<string, unknown>) =>
  handlePipelineMessage({ ...msg, seq: ++seq } as never, h.setPipelineState, h.agentStartTimesRef);

/** One pass of one step: start, then complete with these totals (input + output = total). */
function pass(h: H, agentId: string, total: number, visit?: number) {
  const input = total - 100;
  send(h, { type: "agent_start", agent_id: agentId, ...(visit ? { visit_count: visit } : {}) });
  send(h, {
    type: "agent_complete", agent_id: agentId, ...(visit ? { visit_count: visit } : {}),
    input_tokens: input, output_tokens: 100, total_tokens: total,
  });
}

describe("QA-KB-093: live token total counts every pass of a re-run step", () => {
  it("matches the backend total (sum of all agent_complete events) on a loop run", () => {
    const h = makeHarness();
    pass(h, "emoji", 3181);
    pass(h, "greet", 3188);
    pass(h, "check", 3324);
    pass(h, "greet", 3449, 1);
    pass(h, "check", 3366, 1);
    pass(h, "done", 3307);

    expect(h.state.totalTokens).toBe(19815);
    expect(h.state.totalTokens).not.toBe(13303); // the old last-pass-only figure
  });

  it("keeps each step's own token fields last-pass-only, like duration", () => {
    const h = makeHarness();
    pass(h, "greet", 3188);
    pass(h, "greet", 3449, 1);

    const greet = h.state.agents.find((a) => a.id === "greet")!;
    expect(greet.totalTokens).toBe(3449);
    expect(greet.priorPassTotalTokens).toBe(3188);
  });

  it("leaves a run with no re-runs unchanged", () => {
    const h = makeHarness();
    pass(h, "emoji", 1000);
    pass(h, "greet", 2000);

    expect(h.state.totalTokens).toBe(3000);
    expect(h.state.agents.every((a) => a.priorPassTotalTokens === undefined)).toBe(true);
  });
});
