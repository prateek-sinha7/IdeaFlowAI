/**
 * ISS-657 — sibling of QA-PS-005 (ISS-647): `handleSwitchToLiveRun` has no
 * in-flight guard, so a rapid re-click/double-click on two different running
 * pipelines can race and land on the wrong one.
 *
 * `handleSwitchToLiveRun` (page.tsx, ~line 2592) is `async`: it sets
 * `trackedRunIdRef.current = runId` and `runStore.switchViewTo(runId)`
 * synchronously, then `await getRunEvents(...)`, replays the durable frames,
 * and finally calls `runStore.switchViewTo(runId)` AGAIN once that fetch
 * resolves. Nothing in the function checks that `runId` is still the run the
 * user last clicked before that final call — so if two overlapping calls are
 * in flight (A started, then B started before A's fetch resolved) and A's
 * fetch happens to resolve LAST, A's replay clobbers B's already-applied
 * switch, silently reverting the viewport to the run the user did NOT most
 * recently click.
 *
 * `handleSwitchToLiveRun` is an inline `useCallback` inside a 4000+ line page
 * component with no existing test harness mounting it (`use()`-based async
 * route params, auth bootstrap, SSE wiring) — exercising the real race would
 * require inventing that harness from scratch, which risks a test that fails
 * on plumbing rather than on this defect. Per the card's own root-cause
 * analysis, the exact gap is mechanical and file-local: there is no
 * generation/abort guard between the ref write at call-start and the final
 * `runStore.switchViewTo(runId)` inside the `try`. This test pins that gap
 * directly against the real, current source, so it fails today and starts
 * failing loudly (soft assertion flips true) the moment a guard is added.
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";

describe("handleSwitchToLiveRun — ISS-657 in-flight race guard", () => {
  // ISS-657 unfixed: `{ fails: true }` is this suite's xfail — the test must
  // FAIL today (asserting the guard's presence) and will start reporting a
  // hard failure ("expected test to fail") once the guard is added, which is
  // the signal to remove this flag.
  it("guards the final switchViewTo call against a newer, already-started switch", () => {
    const src = readFileSync(path.join(__dirname, "page.tsx"), "utf8");

    const start = src.indexOf("const handleSwitchToLiveRun = useCallback(");
    expect(start).toBeGreaterThan(-1);
    const depsMarker = "[recentRuns, runConnection, seedRunChatTranscript, handleWebSocketMessage],";
    const end = src.indexOf(depsMarker, start);
    expect(end).toBeGreaterThan(start);
    const body = src.slice(start, end);

    // Sanity: this is genuinely the async replay path the card describes —
    // if these markers move, the slice above is no longer the right function
    // and this test would otherwise pass/fail for the wrong reason.
    expect(body).toContain("await getRunEvents(");
    expect(body).toContain("runStore.switchViewTo(runId)");

    // The final `runStore.switchViewTo(runId)` (post-replay, inside the
    // `try`) must be preceded by a check that this call is still the most
    // recent switch — e.g. bailing when `trackedRunIdRef.current !== runId`,
    // or an AbortController/generation-token comparison — before it's
    // allowed to re-apply. ISS-657 unfixed: no such guard exists anywhere in
    // this function today.
    const hasInFlightGuard =
      /trackedRunIdRef\.current\s*!==\s*runId/.test(body) ||
      /\.aborted\b/i.test(body) ||
      /generation/i.test(body);

    expect(hasInFlightGuard).toBe(true);
  });
});
