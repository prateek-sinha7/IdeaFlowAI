import fc from "fast-check";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createLiveAnnouncer,
  DRAFT_APPLIED_MESSAGE,
  STAGE_INTERVAL_MS,
  TURN_END_MESSAGES,
  type TurnEndKind,
} from "./liveAnnouncer";

// Feature: ai-workflow-builder, Property 39: The live region announces only what it should
// **Validates: Requirements 14.2, 14.5**

// Fixed seed keeps failures reproducible.
const PROPERTY_OPTIONS = { seed: 20260511, numRuns: 200 } as const;

const TURN_END_KINDS: readonly TurnEndKind[] = ["finished", "stopped", "failed"];
const TURN_END_LINES: ReadonlySet<string> = new Set(Object.values(TURN_END_MESSAGES));
const DELTA_PREFIX = "delta:";

/**
 * One step of a turn as the panel sees it. `delta` is streamed text: the
 * panel receives it but has no way to pass it to the announcer (Req 14.5), so
 * the driver below only advances the clock for it.
 */
type Step =
  | { kind: "stage"; label: string; delayMs: number }
  | { kind: "draft"; delayMs: number }
  | { kind: "delta"; text: string; delayMs: number }
  | { kind: "end"; end: TurnEndKind; delayMs: number };

// Few labels so repeats and A-B-A patterns occur; delays straddle the 3 s window.
const delayMs = fc.oneof(
  { weight: 3, arbitrary: fc.integer({ min: 0, max: 600 }) },
  { weight: 2, arbitrary: fc.integer({ min: 2900, max: 3100 }) },
  { weight: 1, arbitrary: fc.integer({ min: 0, max: 10_000 }) },
);
const label = fc.integer({ min: 0, max: 4 }).map((n) => `Stage ${n}`);

const step: fc.Arbitrary<Step> = fc.oneof(
  { weight: 6, arbitrary: fc.record({ kind: fc.constant("stage" as const), label, delayMs }) },
  { weight: 2, arbitrary: fc.record({ kind: fc.constant("draft" as const), delayMs }) },
  {
    weight: 4,
    arbitrary: fc.record({
      kind: fc.constant("delta" as const),
      text: fc.string({ maxLength: 40 }).map((s) => `${DELTA_PREFIX}${s}`),
      delayMs,
    }),
  },
  {
    weight: 1,
    arbitrary: fc.record({
      kind: fc.constant("end" as const),
      end: fc.constantFrom(...TURN_END_KINDS),
      delayMs,
    }),
  },
);

const steps = fc.array(step, { maxLength: 40 });

interface Emission {
  message: string;
  at: number;
  /** Index of the step being applied, or `steps.length` for the final settle. */
  stepIndex: number;
}

interface Run {
  emissions: Emission[];
  /** Latest stage label fed before each stage emission, by emission index. */
  latestFedAtEmission: (string | null)[];
}

/** Run a sequence against a fresh announcer under fake timers. */
function drive(sequence: readonly Step[]): Run {
  vi.useFakeTimers();
  vi.setSystemTime(1_000_000);
  const emissions: Emission[] = [];
  const latestFedAtEmission: (string | null)[] = [];
  let stepIndex = 0;
  let latestFed: string | null = null;
  const announcer = createLiveAnnouncer((message) => {
    emissions.push({ message, at: Date.now(), stepIndex });
    latestFedAtEmission.push(latestFed);
  });
  try {
    sequence.forEach((s, index) => {
      stepIndex = index;
      vi.advanceTimersByTime(s.delayMs);
      switch (s.kind) {
        case "stage":
          latestFed = s.label;
          announcer.stage(s.label);
          break;
        case "draft":
          announcer.draftApplied();
          break;
        case "delta":
          break;
        case "end":
          announcer.turnEnded(s.end);
          break;
      }
    });
    stepIndex = sequence.length;
    vi.advanceTimersByTime(STAGE_INTERVAL_MS);
  } finally {
    announcer.dispose();
    vi.useRealTimers();
  }
  return { emissions, latestFedAtEmission };
}

function isStageMessage(message: string): boolean {
  return message !== DRAFT_APPLIED_MESSAGE && !TURN_END_LINES.has(message);
}

describe("Property 39: the live region announces only what it should", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("announces only fed stage labels, the applied-draft line and the turn-end lines", () => {
    fc.assert(
      fc.property(steps, (sequence) => {
        const { emissions } = drive(sequence);
        for (const { message, stepIndex } of emissions) {
          expect(message.startsWith(DELTA_PREFIX)).toBe(false);
          if (isStageMessage(message)) {
            const fedBefore = sequence
              .slice(0, stepIndex + 1)
              .some((s) => s.kind === "stage" && s.label === message);
            expect(fedBefore).toBe(true);
          }
        }
      }),
      PROPERTY_OPTIONS,
    );
  });

  it("announces at most one stage label per 3 s", () => {
    fc.assert(
      fc.property(steps, (sequence) => {
        const { emissions } = drive(sequence);
        const stageTimes = emissions.filter((e) => isStageMessage(e.message)).map((e) => e.at);
        for (let i = 1; i < stageTimes.length; i += 1) {
          expect(stageTimes[i] - stageTimes[i - 1]).toBeGreaterThanOrEqual(STAGE_INTERVAL_MS);
        }
      }),
      PROPERTY_OPTIONS,
    );
  });

  it("announces the latest stage whenever it announces one, and settles on it", () => {
    fc.assert(
      fc.property(steps, (sequence) => {
        const { emissions, latestFedAtEmission } = drive(sequence);
        emissions.forEach((e, index) => {
          if (isStageMessage(e.message)) {
            expect(e.message).toBe(latestFedAtEmission[index]);
          }
        });

        // With no turn end after the last stage call, the window closes and
        // the latest label has been announced by then.
        const lastStageIndex = sequence.map((s) => s.kind).lastIndexOf("stage");
        if (lastStageIndex === -1) return;
        const endedAfter = sequence.slice(lastStageIndex + 1).some((s) => s.kind === "end");
        if (endedAfter) return;
        const lastFed = (sequence[lastStageIndex] as Extract<Step, { kind: "stage" }>).label;
        const lastAnnounced = [...emissions].reverse().find((e) => isStageMessage(e.message));
        expect(lastAnnounced?.message).toBe(lastFed);
      }),
      PROPERTY_OPTIONS,
    );
  });

  it("announces each draft and turn-end event once, at the time it happens", () => {
    fc.assert(
      fc.property(steps, (sequence) => {
        const { emissions } = drive(sequence);
        const fixed = emissions.filter((e) => !isStageMessage(e.message));
        const expected = sequence.flatMap((s, index) => {
          if (s.kind === "draft") return [{ message: DRAFT_APPLIED_MESSAGE, stepIndex: index }];
          if (s.kind === "end") return [{ message: TURN_END_MESSAGES[s.end], stepIndex: index }];
          return [];
        });
        expect(fixed.map(({ message, stepIndex }) => ({ message, stepIndex }))).toEqual(expected);
      }),
      PROPERTY_OPTIONS,
    );
  });
});
