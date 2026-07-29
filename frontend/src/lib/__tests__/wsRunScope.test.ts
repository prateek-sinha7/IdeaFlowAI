/**
 * Foreign-run frame scoping — the guard that stops a CONCURRENT run's per-agent
 * frames from mutating the VIEWED run's live state.
 *
 * Why this exists: the SSE provider attaches one stream per live run and fans
 * EVERY frame out to the single dashboard subscriber. The agent-scoped payloads
 * (`agent_start`/`agent_chunk`/`agent_complete`/`tool_*`/`task_*`) carry no
 * `pipeline_run_id`, and agent ids are NOT unique across runs — two prototype
 * runs both stream `prototype-build` and `prototype-validate`. So a second run's
 * frames were applied to the finished run on screen: after `pipeline_complete`
 * swept every agent to "done" and the completion notification fired, the other
 * run's build/validate frames flipped those same agents back to "running" and
 * kept them cycling through its task loop — "the workflow says it's done but the
 * validation and build agents are still running in a loop", with no second
 * notification possible (the notification id had already been consumed).
 *
 * Pinned here:
 *   1. the predicate is conservative — an untagged frame or an unclaimed tab is
 *      never foreign (launch → first-frame window must keep working);
 *   2. the agent-scoped set covers every frame type that writes per-agent state,
 *      and EXCLUDES the run-lifecycle frames (they carry their own run id and
 *      drive revision / chaining / reopen across runs);
 *   3. end-to-end through the real reducer: a foreign `agent_start` dropped by
 *      the guard leaves a completed run's agents "done", while the SAME frame
 *      from the tracked run is applied.
 */
import { describe, expect, it } from "vitest";
import {
  isForeignRunFrame,
  isAgentScopedFrame,
  AGENT_SCOPED_FRAME_TYPES,
} from "@/lib/wsReplayState";
import { handlePipelineMessage } from "@/hooks/useWorkflow";
import type { AgentRunState, PipelineRunState } from "@/types/index";

const VIEWED_RUN = "run-viewed";
const OTHER_RUN = "run-other";

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

/**
 * Fake setPipelineState that applies functional updaters to a seed, mirroring how
 * the hook drives handlePipelineMessage (msg + setPipelineState + ref stub).
 */
function makeHarness(seed: PipelineRunState) {
  const state = { current: seed };
  return {
    get state() {
      return state.current;
    },
    setPipelineState: (
      updater: PipelineRunState | ((prev: PipelineRunState) => PipelineRunState),
    ) => {
      state.current =
        typeof updater === "function"
          ? (updater as (prev: PipelineRunState) => PipelineRunState)(state.current)
          : updater;
    },
    agentStartTimesRef: { current: {} as Record<string, number> },
  };
}

/**
 * The dashboard router's guard, in isolation: drop an agent-scoped frame that
 * arrived on a run this tab does not track; otherwise apply it via the reducer.
 * Mirrors `handleWebSocketMessage`'s top-of-handler check.
 */
function route(
  h: ReturnType<typeof makeHarness>,
  msg: { type: string; [k: string]: unknown },
  frameRunId: string | undefined,
  trackedRunId: string | null,
): "dropped" | "applied" {
  if (isAgentScopedFrame(msg.type) && isForeignRunFrame(frameRunId, trackedRunId)) {
    return "dropped";
  }
  handlePipelineMessage(msg, h.setPipelineState, h.agentStartTimesRef);
  return "applied";
}

describe("isForeignRunFrame — conservative run attribution", () => {
  it("is foreign only when BOTH ids are known and differ", () => {
    expect(isForeignRunFrame(OTHER_RUN, VIEWED_RUN)).toBe(true);
  });

  it("treats a frame from the tracked run as ours", () => {
    expect(isForeignRunFrame(VIEWED_RUN, VIEWED_RUN)).toBe(false);
  });

  it("never drops an untagged frame (no source run on the envelope)", () => {
    expect(isForeignRunFrame(undefined, VIEWED_RUN)).toBe(false);
    expect(isForeignRunFrame(null, VIEWED_RUN)).toBe(false);
  });

  it("never drops while the tab has claimed no run yet (launch window)", () => {
    expect(isForeignRunFrame(OTHER_RUN, null)).toBe(false);
    expect(isForeignRunFrame(OTHER_RUN, undefined)).toBe(false);
  });
});

describe("AGENT_SCOPED_FRAME_TYPES — membership contract", () => {
  it("covers every frame type that writes per-agent live state", () => {
    for (const t of [
      "agent_start",
      "agent_thinking",
      "agent_chunk",
      "agent_complete",
      "agent_error",
      "agent_input",
      "tool_call",
      "tool_result",
      "task_progress",
      "task_loop_progress",
      "validator_result",
      "gate_passed",
      "gate_blocked",
    ]) {
      expect(isAgentScopedFrame(t)).toBe(true);
    }
  });

  it("EXCLUDES the run-lifecycle frames — they must stay cross-run", () => {
    // These carry their own pipeline_run_id and drive revision-completion
    // re-anchoring, chaining and history reopen; scoping them out would break
    // those flows (a revision run legitimately completes under a NEW run id).
    for (const t of [
      "pipeline_start",
      "pipeline_complete",
      "pipeline_failed",
      "pipeline_cancelled",
      "pipeline_reconnected",
      "planner_start",
      "planner_complete",
      "clarification_limit_reached",
      "workflow_validated",
    ]) {
      expect(isAgentScopedFrame(t)).toBe(false);
    }
    expect(AGENT_SCOPED_FRAME_TYPES.has("pipeline_complete")).toBe(false);
  });
});

describe("foreign-run bleed — a completed run stays completed", () => {
  /** A finished run: both agents swept to "done", run resolved. */
  function completedSeed(): PipelineRunState {
    return {
      isRunning: false,
      pipeline_type: "prototype",
      pipelineRunId: VIEWED_RUN,
      agents: [
        makeAgent("prototype-build", "done"),
        makeAgent("prototype-validate", "done"),
      ],
      currentAgentIndex: 1,
      totalDuration: 12,
      completedCount: 2,
      clarifications: [],
    };
  }

  it("drops a CONCURRENT run's agent_start — agents stay done, run stays resolved", () => {
    const h = makeHarness(completedSeed());

    // The other run is mid task-loop and re-runs the same agent ids.
    const outcome = route(
      h,
      { type: "agent_start", agent_id: "prototype-build" },
      OTHER_RUN,
      VIEWED_RUN,
    );

    expect(outcome).toBe("dropped");
    expect(h.state.agents.map((a) => a.status)).toEqual(["done", "done"]);
    expect(h.state.isRunning).toBe(false);
    expect(h.state.completedCount).toBe(2);
  });

  it("drops the whole foreign build/validate cycle, not just the first frame", () => {
    const h = makeHarness(completedSeed());

    for (const msg of [
      { type: "agent_start", agent_id: "prototype-build" },
      { type: "agent_chunk", agent_id: "prototype-build", chunk: "<div>other run</div>" },
      { type: "task_loop_progress", agent_id: "prototype-build", task_number: 3 },
      { type: "agent_start", agent_id: "prototype-validate" },
      { type: "agent_chunk", agent_id: "prototype-validate", chunk: "validating…" },
    ]) {
      expect(route(h, msg, OTHER_RUN, VIEWED_RUN)).toBe("dropped");
    }

    expect(h.state.agents.map((a) => a.status)).toEqual(["done", "done"]);
    // No foreign output bled into the viewed run's agents.
    expect(h.state.agents.every((a) => a.output === "")).toBe(true);
  });

  it("STILL applies the same frame when it belongs to the tracked run", () => {
    const h = makeHarness(completedSeed());

    const outcome = route(
      h,
      { type: "agent_start", agent_id: "prototype-build" },
      VIEWED_RUN,
      VIEWED_RUN,
    );

    expect(outcome).toBe("applied");
    expect(h.state.agents[0].status).toBe("running");
  });

  it("STILL applies an untagged frame (legacy/durable replay parity)", () => {
    const h = makeHarness(completedSeed());

    const outcome = route(
      h,
      { type: "agent_start", agent_id: "prototype-build" },
      undefined,
      VIEWED_RUN,
    );

    expect(outcome).toBe("applied");
    expect(h.state.agents[0].status).toBe("running");
  });

  it("lets a FOREIGN pipeline_complete through (revision re-anchoring unbroken)", () => {
    const h = makeHarness(completedSeed());

    const outcome = route(
      h,
      { type: "pipeline_complete", total_duration: 3 },
      OTHER_RUN,
      VIEWED_RUN,
    );

    // Not agent-scoped → never dropped by this guard; the page's own
    // isForeignCompletion / isRevisionCompletion logic decides its side effects.
    expect(outcome).toBe("applied");
  });
});
