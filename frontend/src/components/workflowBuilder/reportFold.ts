/**
 * Report folding for assistant replies in the Builder panel (Req 15.1).
 *
 * A reply is the skill's report when its first line starts with
 * "Context loaded this turn" (SKILL.md step 11 requires that line). The text
 * before the first `## ` heading is the summary; the heading and everything
 * after it is the full report. Folding never filters or rewrites text:
 * `summary + report` is always exactly the input (design: report fold, G-30).
 */

/** The marker the skill's report must start with. */
export const REPORT_MARKER = "Context loaded this turn";

export type FoldedReply =
  | { readonly folded: false; readonly text: string }
  | { readonly folded: true; readonly summary: string; readonly report: string };

/** A Markdown code-fence line: up to 3 spaces, then 3 or more backticks or tildes. */
const FENCE_LINE = /^ {0,3}(`{3,}|~{3,})/;

/**
 * Offset of the first level-2 heading line (`## `, not `### `) outside a fenced
 * code block, or -1. A `## ` line inside a fence is code, not a heading. A
 * fence closes on a line of the same character that is at least as long; an
 * unclosed fence runs to the end of the text, as in CommonMark.
 */
function firstHeadingOffset(text: string): number {
  let offset = 0;
  let fence: string | null = null;
  for (const line of text.split("\n")) {
    const marker = FENCE_LINE.exec(line)?.[1] ?? null;
    if (fence !== null) {
      if (marker !== null && marker[0] === fence[0] && marker.length >= fence.length) {
        fence = null;
      }
    } else if (marker !== null) {
      fence = marker;
    } else if (line.startsWith("## ")) {
      return offset;
    }
    offset += line.length + 1;
  }
  return -1;
}

/**
 * Split a reply into a summary and a collapsible full report.
 *
 * Returns `folded: false` when the reply is not a report or has no `## `
 * heading outside a code block to fold at, so the caller shows the whole text
 * unchanged.
 */
export function foldReport(text: string): FoldedReply {
  const firstLineEnd = text.indexOf("\n");
  const firstLine = firstLineEnd === -1 ? text : text.slice(0, firstLineEnd);
  if (!firstLine.startsWith(REPORT_MARKER)) {
    return { folded: false, text };
  }
  const heading = firstHeadingOffset(text);
  if (heading === -1) {
    return { folded: false, text };
  }
  return {
    folded: true,
    summary: text.slice(0, heading),
    report: text.slice(heading),
  };
}
