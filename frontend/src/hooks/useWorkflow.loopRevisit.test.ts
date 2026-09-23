/**
 * A conditional-route loop-back (and a resume) must not leave the Steps panel in
 * a state the pipeline can never actually be in.
 *
 * Live evidence, run fafea1bc: Coverage Check (index 8) judged the synthesis
 * "incomplete" and routed back to the Synthesizer (index 7). The reducer set the
 * Synthesizer to "running" and touched nothing else, so Coverage Check kept the
 * ✓ it earned on pass 1 and the progress counter never came down — an earlier
 * step in flight underneath a later step marked done. The engine restart made it
 * starker still: Document Ingest re-dispatched at index 0 while the Synthesizer
 * row was STILL showing "Writing…" from the killed pass — two steps rendering as
 * in-flight at once.
 *
 * The engine had the answer all along: `visit_count` rides on both `agent_start`
 * and `agent_complete` (engine.py :4768 / :5754). Nothing in `frontend/src` read
 * it until now.
 */
import { describe, expect, it } from "vitest";
import { handlePipelineMessage } from "./useWorkflow";
import type { AgentRunState, PipelineRunState } from "@/types/index";

function makeAgent(id: string, index: number, status: AgentRunState["status"]): AgentRunState {
  return {
    id, name: id, role: "test", icon: "🤖", status,
    output: "", thinking: "", duration: null, error: null, index,
  };
}

/** The real shape: ingest, five parallel readers, supervisor, synth, checker, journey. */
function seedState(): PipelineRunState {
  return {
    isRunning: true,
    pipeline_type: "custom",
    agents: [
      makeAgent("ingest", 0, "done"),
      makeAgent("r1", 1, "done"),
      makeAgent("r2", 2, "done"),
      makeAgent("r3", 3, "done"),
      makeAgent("r4", 4, "done"),
      makeAgent("r5", 5, "done"),
      makeAgent("supervisor", 6, "done"),
      makeAgent("synth", 7, "done"),
      makeAgent("checker", 8, "done"),
      makeAgent("journey", 9, "skipped"),
      makeAgent("build", 10, "idle"),
    ],
    currentAgentIndex: 8,
    totalDuration: null,
    completedCount: 9,
  };
}

function makeHarness(seed: PipelineRunState = seedState()) {
  let state = seed;
  const setPipelineState = ((updater: unknown) => {
    state = typeof updater === "function"
      ? (updater as (p: PipelineRunState) => PipelineRunState)(state)
      : (updater as PipelineRunState);
  }) as React.Dispatch<React.SetStateAction<PipelineRunState>>;
  const agentStartTimesRef = { current: {} as Record<string, number> };
  return { setPipelineState, agentStartTimesRef, get state() { return state; } };
}

const send = (h: ReturnType<typeof makeHarness>, msg: Record<string, unknown>) =>
  handlePipelineMessage(msg as never, h.setPipelineState, h.agentStartTimesRef);

const at = (h: ReturnType<typeof makeHarness>, id: string): AgentRunState => {
  const a = h.state.agents.find((x) => x.id === id);
  if (!a) throw new Error(`agent ${id} not found`);
  return a;
};

describe("agent_start — a conditional route sends the pipeline backwards", () => {
  it("clears the ✓ from every step after the one re-entered", () => {
    const h = makeHarness();
    send(h, { type: "agent_start", agent_id: "synth", visit_count: 1 });

    expect(at(h, "synth").status).toBe("running");
    expect(at(h, "checker").status).toBe("idle");   // was "done" — it will re-run
    expect(at(h, "journey").status).toBe("idle");   // was "skipped" by this same route
  });

  it("leaves the steps BEFORE the re-entered one alone", () => {
    const h = makeHarness();
    send(h, { type: "agent_start", agent_id: "synth", visit_count: 1 });

    for (const id of ["ingest", "r1", "r2", "r3", "r4", "r5", "supervisor"]) {
      expect(at(h, id).status).toBe("done");
    }
  });

  it("brings the progress count back down", () => {
    const h = makeHarness();
    expect(h.state.completedCount).toBe(9);

    send(h, { type: "agent_start", agent_id: "synth", visit_count: 1 });
    send(h, { type: "agent_complete", agent_id: "synth", visit_count: 1 });

    // 7 steps before synth stayed done, synth completed again ⇒ 8, not 10.
    expect(h.state.completedCount).toBe(8);
  });

  it("records which pass this is, on both ends", () => {
    const h = makeHarness();
    send(h, { type: "agent_start", agent_id: "synth", visit_count: 2 });
    expect(at(h, "synth").visitCount).toBe(2);

    send(h, { type: "agent_complete", agent_id: "synth", visit_count: 2 });
    expect(at(h, "synth").visitCount).toBe(2);
  });
});

describe("a re-entered step clears a STALE running row too", () => {
  it("never leaves two steps in flight at once", () => {
    // A step killed mid-write keeps "running" forever unless the reset covers
    // every non-idle status, not just "done".
    const h = makeHarness({ ...seedState(), currentAgentIndex: 8 });
    h.state.agents[9].status = "running"; // journey, stuck mid-write

    send(h, { type: "agent_start", agent_id: "synth", visit_count: 1 });

    const inFlight = h.state.agents.filter(
      (a) => a.status === "running" || a.status === "thinking",
    );
    expect(inFlight.map((a) => a.id)).toEqual(["synth"]);
  });
});

describe("forward progress is untouched (INV-3)", () => {
  it("a fan-out worker starting does NOT reset its running siblings", () => {
    // All five readers are dispatched together, in ascending index order, before
    // any of them completes. Each is a FORWARD move, so none may reset another.
    const h = makeHarness({
      ...seedState(),
      agents: [
        makeAgent("ingest", 0, "done"),
        makeAgent("r1", 1, "idle"),
        makeAgent("r2", 2, "idle"),
        makeAgent("r3", 3, "idle"),
        makeAgent("r4", 4, "idle"),
        makeAgent("r5", 5, "idle"),
        makeAgent("supervisor", 6, "idle"),
      ],
      currentAgentIndex: 0,
      completedCount: 1,
    });

    for (const id of ["r1", "r2", "r3", "r4", "r5"]) send(h, { type: "agent_start", agent_id: id });
    // r5 is quick and finishes while the rest are still reading.
    send(h, { type: "agent_complete", agent_id: "r5" });
    expect(at(h, "r5").status).toBe("done");

    // A late frame for r2 must not wipe r5's completion.
    send(h, { type: "agent_chunk", agent_id: "r2", chunk: "..." });
    expect(at(h, "r5").status).toBe("done");
    expect(at(h, "ingest").status).toBe("done");
  });

  it("fan-out siblings on a LATER pass do not reset each other", () => {
    // The subtle one: gating on visit_count alone is enough on pass 1 (siblings
    // carry none), but on pass 2 every sibling carries visit_count > 0, so the
    // last to start would wipe the higher-indexed ones. Forward movement is what
    // excludes them.
    const h = makeHarness({
      ...seedState(),
      agents: [
        makeAgent("ingest", 0, "done"),
        makeAgent("r1", 1, "idle"),
        makeAgent("r2", 2, "idle"),
        makeAgent("r3", 3, "idle"),
      ],
      currentAgentIndex: 0,
      completedCount: 1,
    });

    // All three re-dispatched in the same (second) pass. The engine emits the
    // starts in ascending index order (observed live: seq 215/218/221/224/227),
    // so each is a forward move and resets nothing.
    send(h, { type: "agent_start", agent_id: "r1", visit_count: 1 });
    send(h, { type: "agent_start", agent_id: "r2", visit_count: 1 });
    send(h, { type: "agent_start", agent_id: "r3", visit_count: 1 });
    // r3 is quick and finishes while r1/r2 are still working.
    send(h, { type: "agent_complete", agent_id: "r3", visit_count: 1 });

    expect(at(h, "r3").status).toBe("done");
    expect(at(h, "r1").status).toBe("running");
    expect(at(h, "r2").status).toBe("running");
    // Gating on visit_count ALONE would have had r3's start wipe nothing (it is
    // last) but r1's and r2's wipe their higher-indexed siblings on the way in.
    expect(at(h, "ingest").status).toBe("done");
  });

  it("an ordinary first dispatch carries no pass badge and resets nothing", () => {
    const h = makeHarness({
      ...seedState(),
      agents: [makeAgent("ingest", 0, "done"), makeAgent("r1", 1, "idle")],
      currentAgentIndex: 0,
      completedCount: 1,
    });
    send(h, { type: "agent_start", agent_id: "r1" });

    expect(at(h, "r1").visitCount).toBe(0);
    expect(at(h, "ingest").status).toBe("done");
  });

  it("a SPEC REVISION restarting step 0 leaves the later steps done (ISS-075)", () => {
    // prototype-specify re-runs at index 0 on every revision cycle. Revisions are
    // counted in `revision_attempt`, never in visit_count, so this path must be
    // untouched — pinned here because an index-based rule would have broken it.
    const h = makeHarness({
      ...seedState(),
      agents: [
        makeAgent("prototype-specify", 0, "done"),
        makeAgent("prototype-plan", 1, "done"),
        makeAgent("prototype-analyze", 2, "done"),
      ],
      currentAgentIndex: 2,
      completedCount: 3,
    });
    send(h, { type: "agent_start", agent_id: "prototype-specify" });

    expect(at(h, "prototype-plan").status).toBe("done");
    expect(at(h, "prototype-analyze").status).toBe("done");
  });
});
