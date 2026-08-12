/**
 * ISS-063 / ISS-080 / ISS-081 — the "Spec Revision Cycle N" banner must count real
 * revision cycles, live AND after a reload AND after a history reopen.
 *
 * FIX-164's arm/consume detector required EVERY agent in the roster to be "done"
 * while the run was still running. For od_prototype the update_specs gate sits on
 * `prototype-analyze`, agent 2 of 5, so `prototype-build` / `prototype-validate` are
 * still "idle" — the arm was structurally unsatisfiable and the banner was dead on
 * every path, not merely on reload. There was zero test coverage, which is exactly
 * why FIX-164 could silently kill the feature it was fixing.
 *
 * The replacement derives the count from the accumulated per-agent restart history.
 * These tests drive `handlePipelineMessage` directly (mirroring
 * `useWorkflow.regenerateReset.test.ts`) with the REAL frame sequences recorded for
 * runs d5dbc9f2-dbe8-480f-8b13-788794a6788e and 6e38b9a7-f2c1-4557-8a2d-9336e958d182,
 * proving:
 *   1. the real log yields 2 (the user clicked "Update the Specs" twice);
 *   2. live-paced and replayed-in-one-synchronous-burst agree exactly;
 *   3. the trailing same-run resume `pipeline_start` no longer zeroes the history;
 *   4. a genuinely different run DOES reset;
 *   5. the event-derived count agrees with `max(spec.version) - 1` from artifact_refs;
 *   6. (ISS-080) DOUBLE DELIVERY of the whole log still yields 2;
 *   7. (ISS-081) a per-task build loop's restarts are not revisions;
 *   8. (ISS-075) the trailing same-run `pipeline_start` no longer resets the roster.
 *
 * Properties 6-8 are the ones the original 15 cases could not see: every one of them
 * called `runFrames(REAL_FRAMES)` EXACTLY ONCE, so they varied frame ORDER but never
 * frame MULTIPLICITY — and multiplicity is what a history reopen produces (the REST
 * durable replay and the SSE durable replay each deliver the same durable event).
 */
import { describe, expect, it } from "vitest";
import { deriveSpecRevisionCount, handlePipelineMessage } from "./useWorkflow";
import { EMPTY_STATE, runFrames } from "./__fixtures__/reducerHarness";
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

/**
 * Stamp a frame with the durable identity EVERY real frame carries: `run_events`
 * persists `event_id` + `seq` on every row and `getRunEvents` merges both onto the
 * replayed payload (lib/api.ts), while the SSE transport delivers the same pair. The
 * previous fixtures omitted them, which is part of why ISS-080 was invisible here: an
 * un-stamped frame cannot be recognised as a re-delivery of one it has already seen.
 */
let stampCounter = 0;
function stamped<T extends Record<string, unknown>>(frame: T): T & { event_id: string; seq: number } {
  stampCounter += 1;
  return { ...frame, event_id: `evt-${stampCounter}`, seq: stampCounter };
}

function pipelineStart(runId = RUN_ID, resumeOffset = 0) {
  return stamped({
    type: "pipeline_start",
    pipeline_type: "od_prototype",
    pipeline_run_id: runId,
    agent_count: 5,
    resume_offset: resumeOffset,
    agents: ROSTER,
  });
}

const start = (agentId: string) => stamped({ type: "agent_start", agent_id: agentId });
const complete = (agentId: string) => stamped({ type: "agent_complete", agent_id: agentId, duration: 1, output: "x" });

/**
 * The real non-chunk sequence for run d5dbc9f2, read from `run_events`:
 *   seq     9  pipeline_start   (resume_offset 0)
 *   seq    11  agent_start      prototype-specify     ← original pass
 *   ...            specify → plan → analyze
 *   seq  9285  agent_start      prototype-specify     ← REVISION CYCLE 1
 *   ...            specify → plan → analyze
 *   seq 20362  agent_start      prototype-specify     ← REVISION CYCLE 2
 *   seq 24787  agent_complete   prototype-specify
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

/**
 * ISS-081 — the real sequence for run 6e38b9a7 (ONE update_specs cycle), whose build
 * step re-invokes the SAME agent once per task: 11 `agent_start` rows for
 * `prototype-build` against 2 for the pipeline head. Read from `run_events`
 * (seqs 32432…43123). `max` over all agents reads this as ten revision cycles.
 */
const BUILD_LOOP_FRAMES: Array<{ type: string; [k: string]: unknown }> = [
  pipelineStart(),
  start("prototype-specify"), complete("prototype-specify"),
  start("prototype-plan"), complete("prototype-plan"),
  // seq 13111 — a mid-run resume re-announcement carrying resume_offset 1
  pipelineStart(RUN_ID, 1),
  start("prototype-analyze"), complete("prototype-analyze"),
  // ── the ONE revision cycle ──
  start("prototype-specify"), complete("prototype-specify"),
  start("prototype-plan"), complete("prototype-plan"),
  start("prototype-analyze"), complete("prototype-analyze"),
  // ── the per-task build loop: 11 restarts of ONE agent, zero revisions ──
  ...Array.from({ length: 11 }).flatMap(() => [
    start("prototype-build"), complete("prototype-build"),
  ]),
  start("prototype-validate"), complete("prototype-validate"),
];

/** The number the banner renders, computed exactly as `useRunStateStore` computes it. */
const bannerCount = (state: PipelineRunState): number => deriveSpecRevisionCount(state);

/** Restart tallies per agent, from the identity-keyed history the reducer accumulates. */
const startTally = (state: PipelineRunState): Record<string, number> =>
  Object.fromEntries(
    Object.entries(state.agentStartEventIds ?? {}).map(([agentId, ids]) => [agentId, ids.length]),
  );

describe("ISS-063 — spec revision cycle count derived from the event stream", () => {
  it("yields 2 for the real d5dbc9f2 frame sequence (two update_specs clicks)", () => {
    // FAIL-BEFORE: no restart history existed and nothing counted restarts — RED.
    const state = runFrames(REAL_FRAMES);
    expect(bannerCount(state)).toBe(2);
  });

  it("counts every restart of the head agent, not one per re-run agent", () => {
    // FIX-163's rule fired once PER AGENT, so one click read as +3 (that was FIX-164's
    // bug report). The revision re-runs specify → plan → analyze; only the head agent's
    // restart count names the cycle.
    const state = runFrames(REAL_FRAMES);
    expect(startTally(state)).toEqual({
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

    expect(bannerCount(paced)).toBe(bannerCount(burst));
    expect(bannerCount(paced)).toBe(2);
  });

  it("survives the trailing same-run resume pipeline_start (mechanism C)", () => {
    // Run d5dbc9f2's log ends with a resume `pipeline_start` (seq 24791) carrying the
    // SAME pipeline_run_id. page.tsx:807 used to reset the counter there, so the value
    // was zeroed at the END of every replay regardless of what came before.
    const withResume = runFrames(REAL_FRAMES);
    const withoutResume = runFrames(REAL_FRAMES.slice(0, -1));
    expect(bannerCount(withResume)).toBe(bannerCount(withoutResume));
    expect(bannerCount(withResume)).toBe(2);
  });

  it("resets for a genuinely different run", () => {
    const state = runFrames([...REAL_FRAMES, pipelineStart("11111111-2222-3333-4444-555555555555")]);
    expect(startTally(state)).toEqual({});
    expect(bannerCount(state)).toBe(0);
  });

  it("stays 0 for a run with no revision", () => {
    const state = runFrames([
      pipelineStart(),
      start("prototype-specify"), complete("prototype-specify"),
      start("prototype-plan"), complete("prototype-plan"),
    ]);
    expect(bannerCount(state)).toBe(0);
  });

  it("agrees with max(spec.version) - 1 from the run's artifact_refs (ISS-065 cross-source)", () => {
    // artifact_refs for d5dbc9f2: spec v1, v2, v3 — read from backend/dev.db. Two
    // independent durable sources must not drift apart; this is the assertion that
    // keeps ISS-063's banner and ISS-065's version picker telling the same story.
    const specVersionsFromArtifactRefs = [1, 2, 3];
    const fromArtifacts = Math.max(...specVersionsFromArtifactRefs) - 1;
    const fromEvents = bannerCount(runFrames(REAL_FRAMES));
    expect(fromEvents).toBe(fromArtifacts);
  });
});

describe("ISS-080 — the count is a function of the SET of events, not of deliveries", () => {
  it("is idempotent under double delivery (a reopen replays REST *and* SSE)", () => {
    // FAIL-BEFORE: 5. Reopening a run fires BOTH durable replays, and the trailing
    // same-run `pipeline_start` wipes the event-id seen-set mid-replay (page.tsx:774,
    // 24783 ids measured), so the second pass re-counts every restart. `+= 1` has no
    // identity key, so it cannot tell a re-delivery from a new start.
    expect(bannerCount(runFrames([...REAL_FRAMES, ...REAL_FRAMES]))).toBe(2);
  });

  it("is idempotent under triple delivery too (any future multiplicity)", () => {
    // Not a hypothetical: a reconnect storm, a third transport, or a StrictMode
    // double-subscribe all produce N deliveries of one durable event.
    expect(bannerCount(runFrames([...REAL_FRAMES, ...REAL_FRAMES, ...REAL_FRAMES]))).toBe(2);
  });

  it("keeps the per-agent tally at the DISTINCT-event count under double delivery", () => {
    // FAIL-BEFORE: {specify: 6, plan: 4, analyze: 4} — exactly the map measured in the
    // live browser (scratchpad/REOPEN-REPLAY-ANALYSIS.md §0).
    expect(startTally(runFrames([...REAL_FRAMES, ...REAL_FRAMES]))).toEqual({
      "prototype-specify": 3,
      "prototype-plan": 2,
      "prototype-analyze": 2,
    });
  });
});

describe("ISS-081 — a per-task agent loop is not a revision cycle", () => {
  it("ignores the build loop's 11 restarts on run 6e38b9a7 (ONE revision)", () => {
    // FAIL-BEFORE: 10. `max` over ALL agents picks `prototype-build`, which the engine
    // re-invokes once per task (_run_build_task_loop) — 11 `agent_start` rows for a run
    // whose artifact_refs hold TWO spec versions.
    expect(bannerCount(runFrames(BUILD_LOOP_FRAMES))).toBe(1);
  });

  it("still ignores the build loop under double delivery", () => {
    // FAIL-BEFORE: 21. The two defects compound: multiplicity multiplies the wrong
    // agent's count. Both properties must hold together or the banner is still wrong.
    expect(bannerCount(runFrames([...BUILD_LOOP_FRAMES, ...BUILD_LOOP_FRAMES]))).toBe(1);
  });

  it("reads 0 revisions on a run whose ONLY repeated agent is the task loop", () => {
    // The predicted LIVE symptom: on a fresh od_prototype build with zero revisions the
    // banner appeared the moment the build loop got going. FAIL-BEFORE: 10.
    const noRevision = [
      pipelineStart(),
      start("prototype-specify"), complete("prototype-specify"),
      start("prototype-plan"), complete("prototype-plan"),
      start("prototype-analyze"), complete("prototype-analyze"),
      ...Array.from({ length: 11 }).flatMap(() => [
        start("prototype-build"), complete("prototype-build"),
      ]),
    ];
    expect(bannerCount(runFrames(noRevision))).toBe(0);
  });
});

describe("ISS-075 — a same-run pipeline_start re-announces, it does not restart", () => {
  it("does not repaint a populated roster as idle (trailing resume_offset 0)", () => {
    // FAIL-BEFORE: all five agents "idle". The last agents-touching frame in the durable
    // log of any run that was resumed while parked is a `pipeline_start` with
    // resume_offset 0, and the reducer REBUILT every agent from it — so a reopened run
    // whose specify/plan/analyze had all completed read as "nothing has run", and every
    // Steps row became a disabled button (StepsOverviewSpine gates on status !== idle).
    const state = runFrames(REAL_FRAMES);
    expect(state.agents.filter((a) => a.status === "done").map((a) => a.id)).toEqual([
      "prototype-specify",
      "prototype-plan",
      "prototype-analyze",
    ]);
  });

  it("does not zero completedCount on a same-run re-announcement", () => {
    // FAIL-BEFORE: 0 — the header read "0 / 5 agents" on a run with three agents done.
    expect(runFrames(REAL_FRAMES).completedCount).toBe(3);
  });

  it("keeps the roster intact when the re-announcement carries a NON-zero offset", () => {
    // Run 6e38b9a7's mid-run resume carries resume_offset 1 while TWO agents are done;
    // rebuilding from the offset alone would demote the second one.
    const upToResume = BUILD_LOOP_FRAMES.slice(0, BUILD_LOOP_FRAMES.findIndex(
      (f, i) => i > 0 && f.type === "pipeline_start",
    ) + 1);
    const state = runFrames(upToResume);
    expect(state.agents.filter((a) => a.status === "done").map((a) => a.id)).toEqual([
      "prototype-specify",
      "prototype-plan",
    ]);
    expect(state.completedCount).toBe(2);
  });

  it("still builds a fresh idle roster for a genuinely different run", () => {
    // The merge must be scoped to the SAME run — a new run starts from zero, unchanged.
    const state = runFrames([...REAL_FRAMES, pipelineStart("11111111-2222-3333-4444-555555555555")]);
    expect(state.agents.every((a) => a.status === "idle")).toBe(true);
    expect(state.completedCount).toBe(0);
  });
});

describe("deriveSpecRevisionCount", () => {
  const withHistory = (
    roster: string[],
    history: Record<string, number>,
  ): PipelineRunState => ({
    ...EMPTY_STATE,
    agents: roster.map((id, index) => ({
      id, name: id, role: "", icon: "🤖", status: "idle" as const,
      output: "", thinking: "", duration: null, error: null, index,
    })),
    agentStartEventIds: Object.fromEntries(
      Object.entries(history).map(([id, n]) => [id, Array.from({ length: n }, (_, i) => `${id}-${i}`)]),
    ),
  });

  it("returns 0 for undefined, empty, and single-start rosters", () => {
    expect(deriveSpecRevisionCount(undefined)).toBe(0);
    expect(deriveSpecRevisionCount(withHistory([], {}))).toBe(0);
    expect(deriveSpecRevisionCount(withHistory(["a", "b", "c"], { a: 1, b: 1, c: 1 }))).toBe(0);
  });

  it("returns the head agent's restart count minus one", () => {
    expect(deriveSpecRevisionCount(withHistory(["a", "b", "c"], { a: 3, b: 2, c: 2 }))).toBe(2);
  });

  it("ignores restarts of any agent that is NOT the pipeline head (ISS-081)", () => {
    // Superseded rule: `max` over all agents returned 1 here and 10 for the real build
    // loop. A later step restarting is a task loop or a partial resume, not a revision.
    expect(deriveSpecRevisionCount(withHistory(["a", "b"], { a: 1, b: 2 }))).toBe(0);
    expect(deriveSpecRevisionCount(withHistory(["a", "b"], { a: 1, b: 11 }))).toBe(0);
  });

  it("returns 0 when the roster is not known yet", () => {
    // No `pipeline_start` has arrived, so there is no head to attribute restarts to.
    expect(deriveSpecRevisionCount({ ...EMPTY_STATE, agentStartEventIds: { a: ["1", "2"] } })).toBe(0);
  });
});
