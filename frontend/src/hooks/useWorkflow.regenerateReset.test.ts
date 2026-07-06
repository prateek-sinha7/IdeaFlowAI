/**
 * FIX-039 — regenerate must REPLACE (not append) an agent's streamed output.
 *
 * When a prototype agent is re-run (user hits "regenerate" at the plan gate),
 * the frontend used to append the new run's stream onto the previous run's, so
 * `PrototypePipelineView.parseTasks(planAgent.output)` read the FIRST `<tasks>`
 * block — a regenerated 9-task plan still showed "1 Build Task".
 *
 * The fix resets the (re)starting agent's run-scoped accumulators in the
 * `agent_start` case BEFORE the next run's chunks accumulate. These tests drive
 * `handlePipelineMessage` directly (mirroring `useWorkflow.reconnect.test.ts`)
 * and gate `agent_start` through `shouldApplyEvent` to model the real dashboard
 * dedup (dashboard/page.tsx:276) — proving:
 *   1. replace-not-append (2-task parse, no v1 residue);
 *   2. thinkingText resets on re-start;
 *   3. replay-safety (a replayed agent_start is dropped upstream → no reset);
 *   4. first-run reset is a no-op;
 *   5. cross-agent + pipeline-level isolation.
 */
import { beforeEach, describe, expect, it } from "vitest";
import { handlePipelineMessage } from "./useWorkflow";
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

/** Seed state: a mid-run pipeline with 2 idle agents. */
function seedState(): PipelineRunState {
  return {
    isRunning: true,
    pipeline_type: "prototype",
    agents: [makeAgent("a1", "idle"), makeAgent("a2", "idle")],
    currentAgentIndex: -1,
    totalDuration: null,
    completedCount: 0,
  };
}

/**
 * Fake setPipelineState: captures functional updaters and applies them to the
 * seed so the test can inspect the resulting state. Mirrors how the hook
 * exercises handlePipelineMessage (msg + setPipelineState + ref stub).
 */
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

/** Model the real dashboard: only route the event when the dedup gate allows. */
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

describe("handlePipelineMessage — agent_start run-scoped reset (FIX-039)", () => {
  it("Test 1: a genuine re-start REPLACES output (2-task parse, no v1 residue)", () => {
    const h = makeHarness();
    const seen = new Set<string>();

    // Run 1 (event e1) — a stale 1-task plan.
    expect(apply(h, seen, "e1", { type: "agent_start", agent_id: "a1", event_id: "e1" })).toBe(true);
    apply(h, seen, undefined, { type: "agent_chunk", agent_id: "a1", chunk: "<tasks>\n## Task 1: X\n</tasks>" });
    expect(agentOf(h, "a1").output).toBe("<tasks>\n## Task 1: X\n</tasks>");

    // Run 2 (NEW event e2) — regenerate. Reset fires immediately.
    expect(apply(h, seen, "e2", { type: "agent_start", agent_id: "a1", event_id: "e2" })).toBe(true);
    expect(agentOf(h, "a1").output).toBe("");

    // The 2nd run's stream — a 2-task plan.
    apply(h, seen, undefined, { type: "agent_chunk", agent_id: "a1", chunk: "<tasks>\n## Task 1: P\n## Task 2: Q\n</tasks>" });

    const out = agentOf(h, "a1").output;
    // Exact equality: only the 2nd chunk survives (no append onto v1).
    expect(out).toBe("<tasks>\n## Task 1: P\n## Task 2: Q\n</tasks>");
    expect(out).not.toContain("Task 1: X");
    // Mirrors parseTasks' count without importing the non-exported parser.
    expect((out.match(/## Task \d+/g) || []).length).toBe(2);
  });

  it("Test 2: thinkingText also resets on re-start", () => {
    const h = makeHarness();
    const seen = new Set<string>();

    apply(h, seen, "e1", { type: "agent_start", agent_id: "a1", event_id: "e1" });
    apply(h, seen, undefined, { type: "agent_thinking", agent_id: "a1", thinking: "first thoughts" });
    expect(agentOf(h, "a1").thinkingText).not.toBe("");

    apply(h, seen, "e2", { type: "agent_start", agent_id: "a1", event_id: "e2" });
    expect(agentOf(h, "a1").thinkingText).toBe("");
  });

  it("Test 3: a REPLAYED agent_start (same event_id) is dropped upstream → live output preserved", () => {
    const h = makeHarness();
    const seen = new Set<string>();

    apply(h, seen, "e1", { type: "agent_start", agent_id: "a1", event_id: "e1" });
    apply(h, seen, undefined, { type: "agent_chunk", agent_id: "a1", chunk: "<tasks>\n## Task 1: X\n</tasks>" });
    const live = agentOf(h, "a1").output;

    // Replayed agent_start with the SAME event_id — shouldApplyEvent returns
    // false, so handlePipelineMessage is NEVER called (no reset).
    const routed = apply(h, seen, "e1", { type: "agent_start", agent_id: "a1", event_id: "e1" });
    expect(routed).toBe(false);
    expect(agentOf(h, "a1").output).toBe(live);
  });

  it("Test 4: first-run reset is a no-op (empty output stays empty; identity preserved)", () => {
    const h = makeHarness();
    const seen = new Set<string>();

    const before = { ...agentOf(h, "a1") };
    apply(h, seen, "e1", { type: "agent_start", agent_id: "a1", event_id: "e1" });
    const after = agentOf(h, "a1");

    expect(after.output).toBe("");
    expect(after.id).toBe(before.id);
    expect(after.name).toBe(before.name);
    expect(after.role).toBe(before.role);
    expect(after.icon).toBe(before.icon);
    expect(after.index).toBe(before.index);
    expect(after.status).toBe("running");
  });

  it("Test 5: restarting A leaves B and pipeline-level state untouched", () => {
    const h = makeHarness();
    const seen = new Set<string>();

    // Give B prior output via its own run.
    apply(h, seen, "b1", { type: "agent_start", agent_id: "a2", event_id: "b1" });
    apply(h, seen, undefined, { type: "agent_chunk", agent_id: "a2", chunk: "B-output" });
    const bBefore = agentOf(h, "a2").output;
    const completedBefore = h.state.completedCount;

    apply(h, seen, "a-e2", { type: "agent_start", agent_id: "a1", event_id: "a-e2" });

    expect(agentOf(h, "a2").output).toBe(bBefore);
    expect(h.state.completedCount).toBe(completedBefore);
  });
});
