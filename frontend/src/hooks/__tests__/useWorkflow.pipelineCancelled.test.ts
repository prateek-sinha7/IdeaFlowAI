/**
 * ISS-035 (SC-4) — pipeline_cancelled must stamp a derivable terminal
 * cancelled marker, and doing so must NOT regress FIX-039.
 *
 * The reskin (plan 06) and Steps (plan 08) derive the LIVE-STATE-CONTRACT §1
 * cancelled state ("Cancelled by you" ack + relaunch) from a marker on
 * `pipelineState` — today the pipeline_cancelled case only flips `isRunning`
 * false and falls through to idle, so a cancelled run is indistinguishable from
 * an idle one. This suite pins:
 *
 *   1. pipeline_cancelled sets the `cancelled` terminal marker (mirrors the
 *      pipeline_failed `failed` marker) alongside isRunning=false / totalDuration
 *      / completedCount, so a downstream selector derives cancelled (not idle).
 *   2. FIX-039 REGRESSION GUARD: the unconditional per-run agent_start
 *      accumulator reset still REPLACES (not appends) an agent's output under a
 *      double agent_start (regenerate) — proving the ISS-035 edit did not
 *      reorder/duplicate the reset block.
 *
 * Drives `handlePipelineMessage` directly (mirrors useWorkflow.regenerateReset)
 * and gates agent_start through `shouldApplyEvent` to model the real dashboard
 * dedup (dashboard/page.tsx).
 */
import { beforeEach, describe, expect, it } from "vitest";
import { handlePipelineMessage } from "../useWorkflow";
import { shouldApplyEvent } from "@/lib/wsReplayState";
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

/** Seed: a mid-run pipeline with one running agent + one done agent. */
function seedState(): PipelineRunState {
  return {
    isRunning: true,
    pipeline_type: "prototype",
    pipelineRunId: "run-abc",
    agents: [makeAgent("a1", "running"), makeAgent("a2", "done")],
    currentAgentIndex: 0,
    totalDuration: null,
    completedCount: 1,
  };
}

function makeHarness() {
  let state = seedState();
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

function apply(
  h: ReturnType<typeof makeHarness>,
  seen: Set<string>,
  eventId: string | undefined,
  msg: { type: string; [key: string]: unknown },
): boolean {
  if (!shouldApplyEvent(seen, eventId)) return false;
  return handlePipelineMessage(msg, h.setPipelineState, h.agentStartTimesRef);
}

function agentOf(h: ReturnType<typeof makeHarness>, id: string): AgentRunState {
  const a = h.state.agents.find((x) => x.id === id);
  if (!a) throw new Error(`agent ${id} not found`);
  return a;
}

describe("handlePipelineMessage — pipeline_cancelled cancel-ack marker (ISS-035, SC-4)", () => {
  it("stamps a derivable `cancelled` terminal marker alongside isRunning=false", () => {
    const h = makeHarness();

    const routed = handlePipelineMessage(
      { type: "pipeline_cancelled", duration: 4200 },
      h.setPipelineState,
      h.agentStartTimesRef,
    );
    expect(routed).toBe(true);

    // The terminal cancelled marker RunLaneState derives "Cancelled by you" from.
    expect(h.state.cancelled).toBe(true);
    // Existing teardown still holds.
    expect(h.state.isRunning).toBe(false);
    expect(h.state.totalDuration).toBe(4200);
    // The in-flight agent resolves to idle; the done agent stays done (count 1).
    expect(agentOf(h, "a1").status).toBe("idle");
    expect(agentOf(h, "a2").status).toBe("done");
    expect(h.state.completedCount).toBe(1);
  });

  it("reads the od_prototype nested data.duration shape too", () => {
    const h = makeHarness();
    handlePipelineMessage(
      { type: "pipeline_cancelled", data: { duration: 999 } },
      h.setPipelineState,
      h.agentStartTimesRef,
    );
    expect(h.state.cancelled).toBe(true);
    expect(h.state.totalDuration).toBe(999);
  });

  it("does not stamp `cancelled` on a non-cancel event (marker stays absent)", () => {
    const h = makeHarness();
    handlePipelineMessage(
      { type: "agent_start", agent_id: "a1", event_id: "e1" },
      h.setPipelineState,
      h.agentStartTimesRef,
    );
    expect(h.state.cancelled).toBeUndefined();
  });
});

describe("FIX-039 regression guard — reset survives the ISS-035 edit", () => {
  it("double agent_start REPLACES (not appends) output; reset order intact", () => {
    const h = makeHarness();
    const seen = new Set<string>();

    // Run 1 (event e1) — a stale 1-task plan on a1.
    expect(apply(h, seen, "e1", { type: "agent_start", agent_id: "a1", event_id: "e1" })).toBe(true);
    apply(h, seen, undefined, { type: "agent_chunk", agent_id: "a1", chunk: "<tasks>\n## Task 1: X\n</tasks>" });
    expect(agentOf(h, "a1").output).toBe("<tasks>\n## Task 1: X\n</tasks>");

    // Run 2 (NEW event e2) — regenerate. The unconditional reset fires immediately.
    expect(apply(h, seen, "e2", { type: "agent_start", agent_id: "a1", event_id: "e2" })).toBe(true);
    expect(agentOf(h, "a1").output).toBe("");

    // The 2nd run's stream — a 2-task plan; only it survives (no append onto v1).
    apply(h, seen, undefined, { type: "agent_chunk", agent_id: "a1", chunk: "<tasks>\n## Task 1: P\n## Task 2: Q\n</tasks>" });
    const out = agentOf(h, "a1").output;
    expect(out).toBe("<tasks>\n## Task 1: P\n## Task 2: Q\n</tasks>");
    expect(out).not.toContain("Task 1: X");
    expect((out.match(/## Task \d+/g) || []).length).toBe(2);
  });
});
