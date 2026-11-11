import fc from "fast-check";
import { describe, expect, it } from "vitest";

import type { FinalTurnStatus, Outcome, StopReason } from "@/types/workflowBuilder";

import type { RunningTurnView, TurnView } from "./builderReducer";
import { canSend } from "./builderSelectors";

// Feature: ai-workflow-builder, Property 38: Send is allowed exactly when the server would accept
// **Validates: Requirements 4.5, 4.6**

// Fixed seed keeps failures reproducible.
const PROPERTY_OPTIONS = { seed: 20260512, numRuns: 100 } as const;

/** The server default for `BUILDER_MAX_MESSAGE_CHARS` (backend/app/core/config.py). */
const SERVER_MAX_CODE_POINTS = 12_000;

function range(from: number, to: number): number[] {
  return Array.from({ length: to - from + 1 }, (_, i) => from + i);
}

/**
 * Code points for which Python's `str.isspace()` is true, which `value.strip()`
 * in schemas.py removes. Written out here, not imported from the production
 * module, so the oracle stays independent. Checked against Python 3.13.
 */
const PYTHON_WHITESPACE: ReadonlySet<number> = new Set([
  ...range(0x09, 0x0d),
  ...range(0x1c, 0x20),
  0x85,
  0xa0,
  0x1680,
  ...range(0x2000, 0x200a),
  0x2028,
  0x2029,
  0x202f,
  0x205f,
  0x3000,
]);

/** Characters that look blank but are content to Python: U+FEFF, U+200B, U+180E. */
const NEAR_MISS_CHARS = ["\uFEFF", "\u200B", "\u180E"] as const;
const WHITESPACE_CHARS = [...PYTHON_WHITESPACE].map((cp) => String.fromCodePoint(cp));

/** The server's rule: not blank under Python's strip, and at most the limit in code points. */
function serverWouldAccept(text: string): boolean {
  let codePoints = 0;
  let blank = true;
  for (const character of text) {
    codePoints += 1;
    if (!PYTHON_WHITESPACE.has(character.codePointAt(0) ?? -1)) {
      blank = false;
    }
  }
  return !blank && codePoints <= SERVER_MAX_CODE_POINTS;
}

function isBusy(turn: TurnView): boolean {
  return turn.kind === "sending" || turn.kind === "running";
}

function codePointCount(text: string): number {
  let count = 0;
  for (const _character of text) {
    count += 1;
  }
  return count;
}

const toText = (codePoints: readonly number[]): string =>
  codePoints.map((cp) => String.fromCodePoint(cp)).join("");

/** One code point from the whole Unicode range, surrogates excluded; half are ASCII so ordinary text is common. */
const anyCodePoint: fc.Arbitrary<number> = fc.oneof(
  fc.integer({ min: 0x00, max: 0x7f }),
  fc.integer({ min: 0x00, max: 0x10ffff }).filter((cp) => cp < 0xd800 || cp > 0xdfff),
);

/** Any Unicode text, with astral characters. */
const fullText = fc.array(anyCodePoint, { maxLength: 40 }).map(toText);

/** Only characters the server strips, possibly empty. */
const blankText = fc.array(fc.constantFrom(...WHITESPACE_CHARS), { maxLength: 40 }).map((c) =>
  c.join(""),
);

/** Blank padding around some content, so a whitespace-only check cannot pass by accident. */
const paddedText = fc
  .tuple(blankText, fullText, blankText)
  .map(([head, body, tail]) => `${head}${body}${tail}`);

/** Non-blank text made only of characters that look like whitespace. */
const nearMissText = fc
  .array(fc.constantFrom(...NEAR_MISS_CHARS), { minLength: 1, maxLength: 10 })
  .map((c) => c.join(""));

/**
 * Text close to the limit, with astral characters (two UTF-16 units each), so
 * a count in UTF-16 units would give a different answer from the server.
 */
const boundaryText = fc
  .integer({ min: SERVER_MAX_CODE_POINTS - 5, max: SERVER_MAX_CODE_POINTS + 5 })
  .chain((length) =>
    fc
      .integer({ min: 0, max: length })
      .map((astral) => "\u{1F600}".repeat(astral) + "a".repeat(length - astral)),
  );

const textArb: fc.Arbitrary<string> = fc.oneof(
  fullText,
  blankText,
  paddedText,
  nearMissText,
  boundaryText,
);

const FINAL_STATUSES: readonly FinalTurnStatus[] = [
  "completed",
  "failed",
  "cancelled",
  "timed_out",
  "interrupted",
];
const ORIGINS: readonly RunningTurnView["origin"][] = ["this_tab", "other_tab", "rejoined"];

const RUNNING_BASE: RunningTurnView = {
  kind: "running",
  turnId: "t1",
  origin: "other_tab",
  stage: "starting",
  label: "Starting",
  startedAt: 0,
  lastSeq: 1,
  activity: [],
  checks: [],
  warnings: [],
  text: "",
  thinking: "",
  pendingDraft: null,
};

const turnArb: fc.Arbitrary<TurnView> = fc.oneof(
  fc.constant<TurnView>({ kind: "idle" }),
  textArb.map<TurnView>((text) => ({ kind: "sending", clientMessageId: "c1", text })),
  fc.constantFrom(...ORIGINS).map<TurnView>((origin) => ({ ...RUNNING_BASE, origin })),
  fc
    .record({
      status: fc.constantFrom(...FINAL_STATUSES),
      outcome: fc.constantFrom<Outcome>("draft", "reply", "unfinished"),
      stopReason: fc.constantFrom<StopReason | null>(null, "time", "tool_calls", "error"),
    })
    .map<TurnView>(({ status, outcome, stopReason }) => ({
      kind: "ended",
      turnId: "t1",
      status,
      outcome,
      stopReason,
    })),
);

describe("Property 38: Send is allowed exactly when the server would accept", () => {
  it("enables Send exactly when no turn is busy and the server would accept the text", () => {
    fc.assert(
      fc.property(
        turnArb,
        textArb,
        (turn, text) => canSend(text, turn) === (!isBusy(turn) && serverWouldAccept(text)),
      ),
      PROPERTY_OPTIONS,
    );
  });

  it("generates busy and idle turns, blank, near-miss and over-limit text", () => {
    // Guards the generators: each branch of the property above must be reachable.
    const turns = fc.sample(turnArb, { seed: PROPERTY_OPTIONS.seed, numRuns: 500 });
    expect(turns.some((turn) => turn.kind === "sending")).toBe(true);
    expect(turns.some((turn) => turn.kind === "running")).toBe(true);
    expect(turns.some((turn) => turn.kind === "idle")).toBe(true);
    expect(turns.some((turn) => turn.kind === "ended")).toBe(true);

    const texts = fc.sample(textArb, { seed: PROPERTY_OPTIONS.seed, numRuns: 500 });
    expect(texts.some((text) => text.length > 0 && !serverWouldAccept(text))).toBe(true);
    expect(texts.some((text) => codePointCount(text) > SERVER_MAX_CODE_POINTS)).toBe(true);
    expect(
      texts.some(
        (text) => codePointCount(text) === SERVER_MAX_CODE_POINTS && text.length > SERVER_MAX_CODE_POINTS,
      ),
    ).toBe(true);
  });
});
