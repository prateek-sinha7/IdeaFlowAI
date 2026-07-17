import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// ─────────────────────────────────────────────────────────────────
// BUG-021: source-lock assertions for the FRESH-LAUNCH transcript reset —
// on a fresh top-level (non-revision) launch performed in-session after viewing
// another run, the left chat lane's transcript BODY carried over the PREVIOUS
// run's messages because `onStartPipeline`'s `if (!isRevision)` fresh-run reset
// block cleared the preview content + content-source ids but NOT
// `useRunChat.messages`. The fix adds `seedRunChatTranscript([]);` inside that
// block, reusing the existing `seedTranscript` reset primitive so the last-
// viewed run's turns are cleared and the new run's streamed frames fold into the
// now-empty transcript.
//
// The inline `onStartPipeline` arrow resists an isolated unit render (a giant
// inline arrow in a JSX prop inside the 1500+-line page.tsx), so — as with
// contentSourceRunType.source.test.ts / contentSourceRunScope.source.test.ts,
// which already lock THIS reset block — the sanctioned "grep-style source
// assertion" pins the wiring:
//
//  1. PRESENT: page.tsx contains the exact `seedRunChatTranscript([]);` reset.
//  2. INSIDE the `!isRevision` block: the reset sits between `if (!isRevision) {`
//     and the `// For revisions, keep existing content` comment — never on the
//     revision path.
//  3. EXACTLY ONCE: the reset appears once (history-open's
//     `seedRunChatTranscript(durableFrames)` uses `durableFrames`, not `[]`, so
//     it does not match) — proving the reset was not duplicated onto the
//     revision path.
// ─────────────────────────────────────────────────────────────────

const pageSource = readFileSync(
  resolve(__dirname, "../../app/dashboard/page.tsx"),
  "utf8",
);

// Collapse whitespace runs to a single space so the block-boundary slice is
// robust to indentation/line-wrap without loosening what it pins.
const pageCollapsed = pageSource.replace(/\s+/g, " ");

describe("BUG-021 fresh-launch transcript reset (source-lock)", () => {
  it("page.tsx resets the transcript on a fresh launch with seedRunChatTranscript([])", () => {
    expect(pageSource).toContain("seedRunChatTranscript([]);");
  });

  it("the reset sits INSIDE the `if (!isRevision)` fresh-run block (not the revision path)", () => {
    const start = pageCollapsed.indexOf("if (!isRevision) {");
    const end = pageCollapsed.indexOf("// For revisions, keep existing content");
    expect(start).toBeGreaterThan(-1);
    expect(end).toBeGreaterThan(start);
    const freshRunBlock = pageCollapsed.slice(start, end);
    expect(freshRunBlock).toContain("seedRunChatTranscript([]);");
  });

  it("the fresh-launch reset appears EXACTLY once (not duplicated onto the revision path)", () => {
    const matches = pageSource.match(/seedRunChatTranscript\(\[\]/g) ?? [];
    expect(matches).toHaveLength(1);
  });
});
