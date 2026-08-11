/**
 * ISS-063 — the "Spec Revision Cycle N" banner must count real revision cycles,
 * live AND after a reload.
 *
 * FIX-164's arm/consume detector required EVERY agent in the roster to be "done"
 * while the run was still running. For od_prototype the update_specs gate sits on
 * `prototype-analyze`, agent 2 of 5, so `prototype-build` / `prototype-validate` are
 * still "idle" — the arm was structurally unsatisfiable and the banner was dead on
 * every path, not merely on reload. There was zero test coverage, which is exactly
 * why FIX-164 could silently kill the feature it was fixing.
 *
 * The replacement derives the count from the accumulated per-agent restart counts.
 * These tests drive `handlePipelineMessage` directly (mirroring
 * `useWorkflow.regenerateReset.test.ts`) with the REAL frame sequence recorded for
 * run d5dbc9f2-dbe8-480f-8b13-788794a6788e, proving:
 *   1. the real log yields 2 (the user clicked "Update the Specs" twice);
 *   2. live-paced and replayed-in-one-synchronous-burst agree exactly;
 *   3. the trailing same-run resume `pipeline_start` no longer zeroes the history;
 *   4. a genuinely different run DOES reset;
 *   5. the event-derived count agrees with `max(spec.version) - 1` from artifact_refs.
 */
import { describe, expect, it } from "vitest";
import { deriveSpecRevisionCount, handlePipelineMessage } from "./useWorkflow";
import type { PipelineRunState } from "@/types/index";

const RUN_ID = "d5dbc9f2-dbe8-480f-8b13-788794a6788e";

/** The roster from the run's real `pipeline_start` payload (agent_count 5). */
const ROSTER = [
  { id: "prototype-specify", name: "Spec Writer Agent", role: "Specification & Architecture", icon: "🤖", order: 1 },
  { id: "prototype-plan", name: "Task Planner Agent", role: "Build Planning & Task Decomposition", icon: "🤖", order: 2 },
  { id: "prototype-analyze", name: "Spec Kit Analyzer", role: "Cross-Artifact Quality Analysis", icon: "🤖", order: 3 },
  { id: "prototype-build", name: "Builder Agent", role: "Implementation", icon: "🤖", order: 4 },
  { id: "prototype-validate", name: "Validator Agent", role: "Validation", icon: "🤖", order: 5 },
];

function pipelineStart(runId = RUN_ID) {
  return {
    type: "pipeline_start",
    pipeline_type: "od_prototype",
    pipeline_run_id: runId,
    agent_count: 5,
    resume_offset: 0,
    agents: ROSTER,
  };
}

const start = (agentId: string) => ({ type: "agent_start", agent_id: agentId });
const complete = (agentId: string) => ({ type: "agent_complete", agent_id: agentId, duration: 1, output: "x" });

/**
 * The real non-chunk sequence for run d5dbc9f2, read from `run_events`:
 *   seq     9  pipeline_start   (resume_offset 0)
 *   seq    11  agent_start      prototype-specify     ← original pass
 *   ...            specify → plan → analyze
 *   seq  9285  agent_start      prototype-specify     ← REVISION CYCLE 1
 *   ...            specify → plan → analyze
 *   seq 20362  agent_start      prototype-specify     ← REVISION CYCLE 2
 *   seq 24791  pipeline_start   RESUME, SAME run id, resume_offset 0
 */
const REAL_FRAMES: Array<{ type: string; [k: string]: unknown }> = [
  pipelineStart(),
  start("prototype-specify"), complete("prototype-specify"),
  start("prototype-plan"), complete("prototype-plan"),
  start("prototype-analyze"), complete("prototype-analyze"),
  // ── revision cycle 1 ──
  start("prototype-specify"), complete("prototype-specify"),
  start("prototype-plan"), complete("prototype-plan"),
  start("prototype-analyze"), complete("prototype-analyze"),
  // ── revision cycle 2 ──
  start("prototype-specify"), complete("prototype-specify"),
  // ── the trailing resume frame that used to zero the counter (mechanism C) ──
  pipelineStart(),
];

const EMPTY_STATE: PipelineRunState = {
  isRunning: false,
  pipeline_type: "",
  agents: [],
  currentAgentIndex: -1,
  totalDuration: null,
  completedCount: 0,
};

/**
 * Feed frames through the reducer the way `useRunStateStore.handleFrame` does:
 * a synchronous dispatch that writes straight back into the same object. This is
 * the replay model — one tight loop with no React commit between frames.
 */
function runFrames(frames: Array<{ type: string; [k: string]: unknown }>): PipelineRunState {
  let state: PipelineRunState = { ...EMPTY_STATE };
  const times = { current: {} as Record<string, number> };
  for (const f of frames) {
    handlePipelineMessage(
      f,
      ((updater) => {
        state = typeof updater === "function" ? (updater as (p: PipelineRunState) => PipelineRunState)(state) : updater;
      }) as React.Dispatch<React.SetStateAction<PipelineRunState>>,
      times,
    );
  }
  return state;
}

describe("ISS-063 — spec revision cycle count derived from the event stream", () => {
  it("yields 2 for the real d5dbc9f2 frame sequence (two update_specs clicks)", () => {
    // FAIL-BEFORE: `agentStartCounts` does not exist and nothing counts restarts — RED.
    const state = runFrames(REAL_FRAMES);
    expect(deriveSpecRevisionCount(state.agentStartCounts)).toBe(2);
  });

  it("counts every restart of the head agent, not one per re-run agent", () => {
    // FIX-163's rule fired once PER AGENT, so one click read as +3 (that was FIX-164's
    // bug report). The revision re-runs specify → plan → analyze; only the head agent's
    // restart count names the cycle.
    const state = runFrames(REAL_FRAMES);
    expect(state.agentStartCounts).toEqual({
      "prototype-specify": 3,
      "prototype-plan": 2,
      "prototype-analyze": 2,
    });
  });

  it("is identical whether frames arrive one at a time or in one synchronous burst", () => {
    // Mechanism B: the old detector read a ref refreshed only by a post-commit effect,
    // so it was frozen for the whole REST replay loop (page.tsx:2257-2269). A pure
    // function of accumulated state cannot have that failure mode.
    const burst = runFrames(REAL_FRAMES);

    let paced: PipelineRunState = { ...EMPTY_STATE };
    const times = { current: {} as Record<string, number> };
    for (const f of REAL_FRAMES) {
      // Re-seat the state object between frames to model a React commit boundary.
      paced = { ...paced };
      handlePipelineMessage(
        f,
        ((updater) => {
          paced = typeof updater === "function" ? (updater as (p: PipelineRunState) => PipelineRunState)(paced) : updater;
        }) as React.Dispatch<React.SetStateAction<PipelineRunState>>,
        times,
      );
    }

    expect(deriveSpecRevisionCount(paced.agentStartCounts)).toBe(
      deriveSpecRevisionCount(burst.agentStartCounts),
    );
    expect(deriveSpecRevisionCount(paced.agentStartCounts)).toBe(2);
  });

  it("survives the trailing same-run resume pipeline_start (mechanism C)", () => {
    // Run d5dbc9f2's log ends with a resume `pipeline_start` (seq 24791) carrying the
    // SAME pipeline_run_id. page.tsx:807 used to reset the counter there, so the value
    // was zeroed at the END of every replay regardless of what came before.
    const withResume = runFrames(REAL_FRAMES);
    const withoutResume = runFrames(REAL_FRAMES.slice(0, -1));
    expect(deriveSpecRevisionCount(withResume.agentStartCounts)).toBe(
      deriveSpecRevisionCount(withoutResume.agentStartCounts),
    );
    expect(deriveSpecRevisionCount(withResume.agentStartCounts)).toBe(2);
  });

  it("resets for a genuinely different run", () => {
    const state = runFrames([...REAL_FRAMES, pipelineStart("11111111-2222-3333-4444-555555555555")]);
    expect(state.agentStartCounts).toEqual({});
    expect(deriveSpecRevisionCount(state.agentStartCounts)).toBe(0);
  });

  it("stays 0 for a run with no revision", () => {
    const state = runFrames([
      pipelineStart(),
      start("prototype-specify"), complete("prototype-specify"),
      start("prototype-plan"), complete("prototype-plan"),
    ]);
    expect(deriveSpecRevisionCount(state.agentStartCounts)).toBe(0);
  });

  it("agrees with max(spec.version) - 1 from the run's artifact_refs (ISS-065 cross-source)", () => {
    // artifact_refs for d5dbc9f2: spec v1, v2, v3 — read from backend/dev.db. Two
    // independent durable sources must not drift apart; this is the assertion that
    // keeps ISS-063's banner and ISS-065's version picker telling the same story.
    const specVersionsFromArtifactRefs = [1, 2, 3];
    const fromArtifacts = Math.max(...specVersionsFromArtifactRefs) - 1;
    const fromEvents = deriveSpecRevisionCount(runFrames(REAL_FRAMES).agentStartCounts);
    expect(fromEvents).toBe(fromArtifacts);
  });
});

describe("deriveSpecRevisionCount", () => {
  it("returns 0 for undefined, empty, and single-start rosters", () => {
    expect(deriveSpecRevisionCount(undefined)).toBe(0);
    expect(deriveSpecRevisionCount({})).toBe(0);
    expect(deriveSpecRevisionCount({ a: 1, b: 1, c: 1 })).toBe(0);
  });

  it("returns the max restart count minus one", () => {
    expect(deriveSpecRevisionCount({ a: 3, b: 2, c: 2 })).toBe(2);
    expect(deriveSpecRevisionCount({ a: 1, b: 2 })).toBe(1);
  });
});
