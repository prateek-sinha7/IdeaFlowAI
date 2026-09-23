/**
 * The Steps panel reconciles against its own header — pinned to a real run.
 *
 * Run faba87c9 finished in 93m 10s and its seventeen rows added up to 38m 05s. Two
 * separate holes, both visible only at this scale:
 *
 *  1. `duration` was assigned per step id on every `agent_complete`, so a step that ran
 *     twice overwrote its own first number. Thirty executions rendered as seventeen rows.
 *     The Task Planner ran SEVEN times across the spec-revision cycles — 17m 22s — and
 *     reported 2m 23s, the last pass alone.
 *  2. 28m 29s was spent parked at human review gates. That belongs to no step, so no
 *     amount of fixing the per-step numbers could ever have closed the gap.
 *
 * The fixture is the run's own durable log, distilled to the frames that move the
 * timeline (`__fixtures__/run-faba87c9-timeline.json`, 90 of 5.8MB). Replaying it is the
 * only check that actually proves the arithmetic closes; a synthetic two-agent run cannot
 * exercise a seven-pass step, a five-way fan-out and fifteen gate waits at once.
 */
import { describe, expect, it } from "vitest";
import { runFrames, type ReducerFrame } from "./__fixtures__/reducerHarness";
import FIXTURE from "./__fixtures__/run-faba87c9-timeline.json";

const PLANNER = "prototype-plan";
const SYNTH = "custom-agent:oa2v5f-wmvl34";
const READERS = ["oa2v5f-34cpzv", "oa2v5f-2keaco", "oa2v5f-grxt34", "oa2v5f-6bdv7y", "oa2v5f-wscqg4"]
  .map((i) => `custom-agent:${i}`);

const state = runFrames(FIXTURE as ReducerFrame[]);
const byId = (id: string) => {
  const a = state.agents.find((x) => x.id === id);
  if (!a) throw new Error(`${id} not in the replayed roster`);
  return a;
};

describe("the run's own log, replayed", () => {
  it("rebuilds the seventeen rows and the 93m 10s header", () => {
    expect(state.agents).toHaveLength(17);
    expect(state.totalDuration).toBeCloseTo(5589.4, 0);
  });

  it("splits the wall clock into working and awaiting-review", () => {
    expect(state.busySeconds).toBeCloseTo(3878.4, 0);   // 64m 38s
    expect(state.waitingSeconds).toBeCloseTo(1709.4, 0); // 28m 29s
  });

  it("closes: working + awaiting + dispatch residual == the header", () => {
    const residual = (state.totalDuration ?? 0) - (state.busySeconds ?? 0) - (state.waitingSeconds ?? 0);
    // 17 dispatch hand-offs at ~0.1s each. Unattributed on purpose — absorbing it into
    // either bucket would make the split a fudge rather than a measurement.
    expect(residual).toBeGreaterThanOrEqual(0);
    expect(residual).toBeLessThan(5);
  });

  it("counts concurrent readers ONCE — busy is a union, not a sum", () => {
    // The five readers are dispatched together and overlap by ~202s. A sum of the rows
    // reports 68m 00s of agent time against a 64m 38s union, and can never reconcile.
    // The sum is of the ENGINE's own reported `duration` per pass, which runs ~2.6s
    // above the ts-to-ts spans across all 30 executions (it excludes dispatch overhead);
    // the busy union is measured from the timestamps, so the two are not the same
    // quantity and only the union is the one that closes against the header.
    const naiveSum = state.agents.reduce((s, a) => s + (a.cumulativeDuration ?? 0), 0);
    expect(naiveSum).toBeCloseTo(4080.0, 0);
    expect(naiveSum - (state.busySeconds ?? 0)).toBeCloseTo(201.5, 0);
    for (const r of READERS) expect(byId(r).passCount).toBe(1);
  });
});

describe("a step that ran more than once reports all of it", () => {
  it("the Task Planner: 7 passes, 17m 22s, not the 2m 23s of its last one", () => {
    const plan = byId(PLANNER);
    expect(plan.passCount).toBe(7);
    expect(plan.duration).toBeCloseTo(143.45, 1);          // still the pass on screen
    expect(plan.cumulativeDuration).toBeCloseTo(1042.3, 0); // what the seven cost
  });

  it("the Synthesizer's conditional loop-back is counted the same way", () => {
    const synth = byId(SYNTH);
    expect(synth.passCount).toBe(2);
    expect(synth.visitCount).toBe(1); // the engine's own signal, unchanged
    expect(synth.cumulativeDuration).toBeCloseTo(713.6, 0);
  });

  it("passCount sees the revision restarts visit_count never did", () => {
    // The reason the badge could not keep reading visit_count: the engine stamps it on
    // conditional routes only, so six of the Task Planner's seven dispatches were
    // invisible to it while the Synthesizer's single loop-back was not.
    expect(byId(PLANNER).visitCount ?? 0).toBe(0);
    expect(byId(PLANNER).passCount).toBe(7);
  });

  it("every execution in the log is accounted for", () => {
    const dispatches = (FIXTURE as ReducerFrame[]).filter((f) => f.type === "agent_start").length;
    const counted = state.agents.reduce((s, a) => s + (a.passCount ?? 0), 0);
    expect(counted).toBe(dispatches);
    expect(counted).toBe(30); // 30 executions behind 17 rows
  });
});
