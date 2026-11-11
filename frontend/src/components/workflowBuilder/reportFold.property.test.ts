import fc from "fast-check";
import { describe, expect, it } from "vitest";

import { REPORT_MARKER, foldReport } from "./reportFold";

// Fixed seed keeps failures reproducible; 200 runs per property stays fast.
const PROPERTY_OPTIONS = { seed: 20240611, numRuns: 200 } as const;

// Lines mix the tokens the fold cares about (marker, `## `, `### `, indented
// and inline `## `) with arbitrary text so generated replies hit every branch.
const replyLine = fc.oneof(
  fc.constantFrom(
    REPORT_MARKER,
    `${REPORT_MARKER}: 3 files`,
    "## Details",
    "## ",
    "### Sub heading",
    "  ## indented",
    "use ## inline",
    "| a | b |",
    "```",
    "```md",
    "~~~",
    "````",
    "",
  ),
  fc.string({ maxLength: 30 }),
);

const lineBreak = fc.constantFrom("\n", "\r\n");

/** Any reply: random lines joined by LF or CRLF. */
const anyReply = fc
  .tuple(fc.array(replyLine, { maxLength: 15 }), lineBreak)
  .map(([lines, eol]) => lines.join(eol));

/** A reply whose first line starts with the report marker. */
const markedReply = fc
  .tuple(
    fc.string({ maxLength: 20 }).filter((s) => !s.includes("\n")),
    fc.array(replyLine, { maxLength: 15 }),
    lineBreak,
  )
  .map(([tail, lines, eol]) => [`${REPORT_MARKER}${tail}`, ...lines].join(eol));

/** A reply whose first line does not start with the report marker. */
const unmarkedReply = anyReply.filter((text) => {
  const firstLine = text.split("\n", 1)[0] ?? "";
  return !firstLine.startsWith(REPORT_MARKER);
});

describe("foldReport properties", () => {
  // Feature: ai-workflow-builder, Property 40: Report folding loses nothing
  // **Validates: Requirements 15.1**
  it("joins back to the original text for any reply", () => {
    fc.assert(
      fc.property(fc.oneof(anyReply, markedReply, fc.string()), (text) => {
        const result = foldReport(text);
        const joined = result.folded ? result.summary + result.report : result.text;
        expect(joined).toBe(text);
      }),
      PROPERTY_OPTIONS,
    );
  });

  // Feature: ai-workflow-builder, Property 40: Report folding loses nothing
  // **Validates: Requirements 15.1**
  it("does not fold text whose first line lacks the report marker", () => {
    fc.assert(
      fc.property(unmarkedReply, (text) => {
        expect(foldReport(text)).toEqual({ folded: false, text });
      }),
      PROPERTY_OPTIONS,
    );
  });

  // Feature: ai-workflow-builder, Property 40: Report folding loses nothing
  // **Validates: Requirements 15.1**
  it("folds a marked reply exactly at its first level-2 heading outside a code fence", () => {
    fc.assert(
      fc.property(markedReply, (text) => {
        const result = foldReport(text);
        const expected = headingOutsideFences(text);
        if (!result.folded) {
          // Not folded only when no `## ` line sits outside a fenced code block.
          expect(expected).toBe(-1);
          expect(result.text).toBe(text);
          return;
        }
        expect(result.summary.length).toBe(expected);
        expect(result.summary.startsWith(REPORT_MARKER)).toBe(true);
        expect(result.report.startsWith("## ")).toBe(true);
      }),
      PROPERTY_OPTIONS,
    );
  });
});

/**
 * Oracle: index of the first line that starts with `## ` and is not inside a
 * fenced code block. Lines are located by their start offsets; a fence opens on
 * 3+ backticks or tildes (up to 3 leading spaces) and closes on a run of the same
 * character at least as long.
 */
function headingOutsideFences(text: string): number {
  const starts = [0];
  for (let i = 0; i < text.length; i += 1) {
    if (text[i] === "\n") starts.push(i + 1);
  }
  let open: { char: string; length: number } | null = null;
  for (const start of starts) {
    const end = text.indexOf("\n", start);
    const line = text.slice(start, end === -1 ? text.length : end);
    const run = / {0,3}(`{3,}|~{3,})/y.exec(line);
    if (open !== null) {
      if (run && run[1][0] === open.char && run[1].length >= open.length) open = null;
      continue;
    }
    if (run) {
      open = { char: run[1][0], length: run[1].length };
      continue;
    }
    if (line.startsWith("## ")) return start;
  }
  return -1;
}
