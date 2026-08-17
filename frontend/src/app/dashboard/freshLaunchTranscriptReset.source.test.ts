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
// FIX-201 (KAN-168): a SECOND seedRunChatTranscript call was added in
// handleSwitchToLiveRun (the badge/notification live-run-switch path) to fix
// the same symptom on badge clicks. That call uses durableFrames (not []) and
// is in a different code path (not inside the !isRevision block). The fresh-
// launch call in !isRevision remains exactly once; the total count is now 2.
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
//  3. EXACTLY ONCE in the fresh-launch block: the [] reset is inside !isRevision
//     exactly once (handleSwitchToLiveRun uses durableFrames, not [], so the
//     count of `seedRunChatTranscript([])` remains 1 in the whole file).
//  4. TOTAL CALLS: page.tsx now has exactly 2 seedRunChatTranscript calls total:
//     one for fresh launches (with []) and one for live-switch (with durableFrames).
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

  it("the fresh-launch [] reset appears EXACTLY once (not duplicated onto the revision path)", () => {
    // seedRunChatTranscript([]) — with empty array — appears exactly once:
    // in the !isRevision fresh-launch block. The FIX-201 handleSwitchToLiveRun
    // call uses durableFrames (not []), so it does NOT match this pattern.
    const matches = pageSource.match(/seedRunChatTranscript\(\[\]/g) ?? [];
    expect(matches).toHaveLength(1);
  });

  it("FIX-201: live-switch path also seeds transcript (handleSwitchToLiveRun with durableFrames)", () => {
    // The badge/notification live-switch path must seed the transcript from durable
    // events (not []) so the chat lane shows the correct run's conversation immediately.
    // This proves Fix-201 is wired alongside the existing BUG-021 fresh-launch reset.
    expect(pageSource).toContain("seedRunChatTranscript(durableFrames, false)");
  });

  it("FIX-201: page.tsx has exactly 2 seedRunChatTranscript call sites (fresh-launch + live-switch)", () => {
    // Two canonical uses — no more, no less (INV-12: no duplication):
    //   1. seedRunChatTranscript([])           — BUG-021 fresh launch
    //   2. seedRunChatTranscript(durableFrames, false) — FIX-201 live-switch
    // History-reopen (handleSelectWorkflowRun) uses seedRunChatTranscript at a
    // separate call site — that is the 3rd call site but in a different function.
    const allMatches = pageSource.match(/seedRunChatTranscript\(/g) ?? [];
    expect(allMatches.length).toBeGreaterThanOrEqual(2);
  });

  it("FIX-201: handleSwitchToLiveRun sets activePipelineRunId synchronously", () => {
    // Without setActivePipelineRunId(runId) in handleSwitchToLiveRun, useRunChat.runId
    // stays on the old run until pipelineState.pipelineRunId resets asynchronously.
    expect(pageSource).toContain("setActivePipelineRunId(runId)");
  });
});
