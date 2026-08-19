/**
 * ISS-082 — every accumulating field in `handlePipelineMessage` survives re-delivery.
 *
 * THE RULE, made executable:
 *   A reducer field that accumulates is not done until a test has fed it the same input
 *   twice and it did not change.
 *
 * Why a whole suite for it. `handlePipelineMessage` grows seven fields out of their own
 * previous value (`[...prev.x, y]` or string `+`) instead of overwriting them, so a second
 * delivery of one frame appends a second copy. Until ISS-082 that was survivable only
 * because the CALLERS deduped — and ISS-080 is the proof of what happens when one stops:
 * it shipped behind 15 green tests and still put a wrong number on screen, because every
 * one of those tests varied frame ORDER and never frame MULTIPLICITY.
 *
 * Three deliveries are exercised per field, because they fail for different reasons:
 *   1. PARTIAL redelivery — the same frames again with NO intervening `agent_start`. This
 *      is what an SSE resume from `Last-Event-ID` produces mid-agent, and it is the one
 *      that was red for five of the six frame-driven fields.
 *   2. FULL replay — the whole log twice, `pipeline_start` included. This one used to
 *      self-heal for the per-agent fields, because `agent_start`'s FIX-039 reset is a fixed
 *      point — but NOT for `hookRuns`, which nothing resets. That asymmetry is load-bearing
 *      and is pinned here so nobody leans on it again.
 *   3. TRIPLE delivery — catches a fix that happens to be correct only at n=2.
 *
 * The registry below is the enforcement point: GUARD-1 (bottom of this file) reads
 * `useWorkflow.ts` and fails if the source grows an accumulator that has no row here.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { runFrames, type ReducerFrame } from "./__fixtures__/reducerHarness";
import type { PipelineRunState } from "@/types/index";

const RUN_ID = "0be8ac52-1c3f-4a8e-9d70-5f1a2b3c4d5e";

const ROSTER = [
  { id: "a1", name: "Agent One", role: "First", icon: "🤖", order: 1 },
  { id: "a2", name: "Agent Two", role: "Second", icon: "🤖", order: 2 },
];

/**
 * Stamp a frame with the durable identity every real frame carries. `run_events` persists
 * `event_id` + `seq` on every row; `getRunEvents` merges both COLUMNS onto the replayed
 * payload (`lib/api.ts`) and the SSE transport delivers the same pair — so one durable
 * event has ONE identity on both transports. A re-delivery re-uses the stamped object, so
 * the two copies are indistinguishable from the two the wire actually produces.
 */
let stampCounter = 0;
function stamped<T extends Record<string, unknown>>(frame: T): T & { event_id: string; seq: number } {
  stampCounter += 1;
  return { ...frame, event_id: `evt-${stampCounter}`, seq: stampCounter };
}

/**
 * `hook_run` is the ONE frame with no `seq`: `KernelServices.emit_hook_event` pushes it
 * straight onto the live queue, so it never reaches the engine's `seq`/`event_id` stamping
 * chokepoint and has no `run_events` row. ISS-082/A1 gives it a uuid `event_id` and nothing
 * else — deliberately, because routing it through `execute()` would persist a row and add a
 * frame to the engine's yield stream, changing the golden event multiset (INV-3).
 */
function stampedWithoutSeq<T extends Record<string, unknown>>(frame: T): T & { event_id: string } {
  stampCounter += 1;
  return { ...frame, event_id: `evt-${stampCounter}` };
}

/**
 * The head every case shares: the run announces its roster, then agent `a1` starts. Stamped
 * BEFORE the registry below (module evaluation order), so every case's body carries a HIGHER
 * `seq` than its own head — the shape the wire guarantees and the cursor relies on.
 */
const HEAD: ReducerFrame[] = [
  stamped({
    type: "pipeline_start",
    pipeline_type: "od_prototype",
    pipeline_run_id: RUN_ID,
    agent_count: ROSTER.length,
    resume_offset: 0,
    agents: ROSTER,
  }),
  stamped({ type: "agent_start", agent_id: "a1" }),
];

// ── Part 1: the registry — one row per accumulating field ────────────────────────────────

interface AccumulatorCase {
  /** The literal key in the reducer's return. GUARD-1 matches source sites on this. */
  stateKey: string;
  /** Where a reader finds it on screen. */
  label: string;
  /**
   * `frame` — grown by an incoming pipeline frame, so frame identity can gate it.
   * `ui` — grown by a direct call from the UI, which carries no frame and therefore no
   * identity to gate on. Registered (GUARD-1 must still see it) but not driven below.
   */
  driver: "frame" | "ui";
  /** The minimal frames that grow it, delivered AFTER `HEAD`. */
  body: ReducerFrame[];
  /** What the user ends up seeing. */
  read: (s: PipelineRunState) => unknown;
  /** Its value after ONE logical delivery, however many times the wire delivers it. */
  expected: unknown;
}

const ACCUMULATORS: AccumulatorCase[] = [
  {
    stateKey: "output",
    label: "agents[].output — the streamed deliverable text (PreviewPanel, Thinking tab)",
    driver: "frame",
    body: [
      stamped({ type: "agent_chunk", agent_id: "a1", chunk: "Hello " }),
      stamped({ type: "agent_chunk", agent_id: "a1", chunk: "world" }),
    ],
    read: (s) => s.agents[0]?.output,
    expected: "Hello world",
  },
  {
    stateKey: "thinkingText",
    label: "agents[].thinkingText — the Thinking tab transcript",
    driver: "frame",
    body: [stamped({ type: "agent_thinking", agent_id: "a1", thinking: "step one" })],
    read: (s) => s.agents[0]?.thinkingText,
    // No trailing separator: the reducer concatenates thinking deltas verbatim
    // (see useWorkflow.ts — "plain concatenation, no separator"), because thinking
    // now streams at agent_chunk granularity and each delta carries its own
    // spacing. This expectation still said "step one\n" from when the reducer
    // joined whole thoughts with a newline.
    expected: "step one",
  },
  {
    stateKey: "toolCalls",
    label: "agents[].toolCalls — the tool-call rows in the Thinking tab",
    driver: "frame",
    body: [stamped({ type: "tool_call", agent_id: "a1", tool: "read_file", args: { path: "spec.md" } })],
    read: (s) => s.agents[0]?.toolCalls?.length,
    expected: 1,
  },
  {
    stateKey: "validationIssues",
    label: "agents[].validationIssues — AgentDetailPanel's checks badge",
    driver: "frame",
    // `validator_result` reads `msg.data ?? msg`, so the flat shape the transports deliver
    // is the shape under test.
    body: [
      stamped({
        type: "validator_result",
        agent_id: "a1",
        issues: [{ severity: "P0", message: "missing route handler" }],
      }),
    ],
    read: (s) => s.agents[0]?.validationIssues?.length,
    expected: 1,
  },
  {
    stateKey: "hookRuns",
    label: "hookRuns — the run's executable-hook audit rows",
    driver: "frame",
    // Flat, and WITHOUT `seq`: this is exactly what reaches the reducer, because
    // `dashboard/page.tsx` spreads `msg.data` onto the frame before dispatching and
    // `emit_hook_event` never gets a `seq`.
    body: [
      stampedWithoutSeq({
        type: "hook_run",
        hook: "secret_scan",
        event: "before_write",
        outcome: "block",
      }),
    ],
    read: (s) => s.hookRuns?.length,
    expected: 1,
  },
  {
    stateKey: "agentStartEventIds",
    label: "agentStartEventIds — the restart history deriveSpecRevisionCount reads",
    driver: "frame",
    // The CONTROL row: FIX-225 already gave this field an identity, so it is green before
    // AND after. It also pins that ISS-082 did not take the array away — the spec-revision
    // banner (and ISS-083 after it) derives from exactly this data.
    body: [stamped({ type: "agent_start", agent_id: "a2" })],
    read: (s) => s.agentStartEventIds?.a2?.length,
    expected: 1,
  },
  {
    stateKey: "clarifications",
    label: "clarifications — retained clarify Q&A rounds (useWorkflow.retainClarifyRound)",
    // Grown by a direct UI call when the questionnaire panel unmounts, not by a frame.
    // There is no event identity to gate on, so ISS-082's mechanism does not reach it;
    // filed separately rather than folded in.
    driver: "ui",
    body: [],
    read: (s) => s.clarifications?.length,
    expected: 0,
  },
];

const FRAME_DRIVEN = ACCUMULATORS.filter((c) => c.driver === "frame");

// ── Part 2: three multiplicities per row ─────────────────────────────────────────────────

describe.each(FRAME_DRIVEN.map((c) => [c.stateKey, c] as const))(
  "ISS-082 — %s survives re-delivery",
  (_key, c) => {
    it(`single delivery establishes the expected value (${c.label})`, () => {
      expect(c.read(runFrames([...HEAD, ...c.body]))).toEqual(c.expected);
    });

    it("partial redelivery — same frames again, no intervening agent_start", () => {
      // FAIL-BEFORE (ISS-082): output "Hello worldHello world", thinkingText
      // "step one\nstep one\n", toolCalls 2, validationIssues 2, hookRuns 2.
      expect(c.read(runFrames([...HEAD, ...c.body, ...c.body]))).toEqual(c.expected);
    });

    it("full replay — the whole log delivered twice", () => {
      // FAIL-BEFORE (ISS-082): hookRuns 2. The per-agent fields converge here only because
      // agent_start resets them; nothing resets hookRuns.
      const log = [...HEAD, ...c.body];
      expect(c.read(runFrames([...log, ...log]))).toEqual(c.expected);
    });

    it("triple delivery — a fix that is only correct at n=2 fails here", () => {
      expect(c.read(runFrames([...HEAD, ...c.body, ...c.body, ...c.body]))).toEqual(c.expected);
    });
  },
);

describe("ISS-082 — a genuinely NEW frame after a re-delivery still applies", () => {
  it("the cursor blocks only what it has already folded in", () => {
    // The failure mode a seq cursor invites: skipping everything after the first replay.
    // A frame the run has not yet seen must still land, whatever preceded it.
    const chunks = ACCUMULATORS[0].body;
    const fresh = stamped({ type: "agent_chunk", agent_id: "a1", chunk: "!" });
    expect(runFrames([...HEAD, ...chunks, ...chunks, fresh]).agents[0]?.output).toBe("Hello world!");
  });

  it("a different run resets the cursor, so run 2's frames are not swallowed", () => {
    // Without a per-run boundary the cursor would carry run 1's high-water mark into run 2
    // and silently drop its whole trace (INV-2 — no cross-run state on shared state).
    // Run 2's seqs start over at 1 — `engine.execute` allocates them per run — so every
    // one of them is BELOW run 1's high-water mark. Hand-stamped rather than taken from
    // the shared counter, because that is the whole point of the case.
    const runTwo: ReducerFrame[] = [
      {
        type: "pipeline_start",
        pipeline_type: "od_prototype",
        pipeline_run_id: "11111111-2222-3333-4444-555555555555",
        agent_count: ROSTER.length,
        resume_offset: 0,
        agents: ROSTER,
        event_id: "r2-evt-1",
        seq: 1,
      },
      { type: "agent_start", agent_id: "a1", event_id: "r2-evt-2", seq: 2 },
      { type: "agent_chunk", agent_id: "a1", chunk: "second run", event_id: "r2-evt-3", seq: 3 },
    ];
    const state = runFrames([...HEAD, ...ACCUMULATORS[0].body, ...runTwo]);
    expect(state.agents[0]?.output).toBe("second run");
  });
});

describe("ISS-082 — clarifications is registered but not frame-gated", () => {
  it("grows through retainClarifyRound, which carries no frame identity", () => {
    // Recorded, not asserted away: the accumulation is real, the mechanism ISS-082 adds
    // cannot reach it, and it is filed rather than folded in.
    const row = ACCUMULATORS.find((c) => c.stateKey === "clarifications");
    expect(row?.driver).toBe("ui");
  });
});

// ── Part 3: GUARD-1 — no new accumulator without a registry row ───────────────────────────

const REDUCER_SOURCE = readFileSync(resolve(__dirname, "./useWorkflow.ts"), "utf8");

/**
 * Wrapped expressions folded back onto one line, so a property the formatter split across
 * lines is still one match. Only continuation tokens are folded (`?`/`:`/`||`/`&&`/`+`/`.x`),
 * never a closing brace, so block structure is untouched.
 */
const FOLDED_SOURCE = REDUCER_SOURCE.replace(/\n[ \t]*(?=[?:]|\|\||&&|\+[ \t]|\.\w)/g, " ");

/** Any `key: value` property assignment. */
const PROPERTY = /^[ \t]*(\w+):[ \t]*(.+)$/gm;

/**
 * A value that GROWS: a spread-append, a `.concat(`/`.push(`, or a string concat. A value
 * that merely carries (`?? prev.k`) or overwrites is idempotent and must NOT match — the
 * token totals at `agent_complete` are the model those six should imitate.
 *
 * The ISS-082 register row's own command is the cautionary example this replaces:
 * `grep -nE '\+= 1|\.push\(|\.concat\('` over this file matches a comment and a local
 * variable and ZERO real accumulators, because every one of them uses an idiom it cannot see.
 */
const GROWS = /\[[ \t]*\.\.\.|\.concat\(|\.push\(|\)[ \t]*\+|\w[ \t]*\+[ \t]*\w/;

function findAccumulatorsInSource(): Set<string> {
  const found = new Set<string>();
  for (const [, key, value] of FOLDED_SOURCE.matchAll(PROPERTY)) {
    // Accumulation = the value both READS its own previous value and GROWS it.
    if (!GROWS.test(value)) continue;
    if (!new RegExp(`\\.${key}\\b`).test(value)) continue;
    found.add(key);
  }
  return found;
}

describe("GUARD-1 — an accumulator cannot be added without a registry row", () => {
  const found = findAccumulatorsInSource();
  const registered = new Set(ACCUMULATORS.map((c) => c.stateKey));

  it("the detector is not vacuous: it finds every registered accumulator", () => {
    // Written against the seven known sites FIRST. Without this half the guard could
    // silently match nothing and pass forever — which is precisely how the register row's
    // grep "confirmed" two fields it never actually found.
    expect([...registered].filter((k) => !found.has(k)).sort()).toEqual([]);
  });

  it("finds exactly the registered accumulators and no others", () => {
    // RED when someone grows a new field in the reducer without registering it here — the
    // multiplicity matrix above then covers it automatically.
    expect([...found].filter((k) => !registered.has(k)).sort()).toEqual([]);
  });

  it("the registry covers all seven, six of them frame-driven", () => {
    expect(ACCUMULATORS).toHaveLength(7);
    expect(FRAME_DRIVEN).toHaveLength(6);
  });
});
