/**
 * ISS-649 — sibling of QA-PS-002 (ISS-644): a background/non-viewed run's
 * review-gate opening (pause) or resolving (resume) is never reflected in
 * its notification's paused/resumed mark.
 *
 * `DashboardLayout`'s gate pause/resume effect (~line 926-934) is the ONLY
 * place `markGatePaused`/`markGateResumed` are called:
 *
 *   useEffect(() => {
 *     if (!currentPipelineNotifId.current || !pipelineState?.isRunning) return;
 *     if (reviewGateData) markGatePaused(currentPipelineNotifId.current);
 *     else markGateResumed(currentPipelineNotifId.current);
 *   }, [reviewGateData, pipelineState?.isRunning]);
 *
 * Both `pipelineState` and `reviewGateData` are `runStore.viewed`-scoped
 * (page.tsx:3887/4149) — exactly one run at a time. The per-run
 * `reviewGateData` IS captured correctly for every run regardless of which is
 * viewed (`runStore.update(gateRunId, { reviewGateData })`), but nothing
 * reads that per-run value to mark a BACKGROUND run's notification paused —
 * unlike completion (FIX-203) or progress (ISS-673's target), no
 * `backgroundGate*` bridge exists anywhere in this file (confirmed absent by
 * grep, cited in the card).
 *
 * Same class of gap as ISS-648/ISS-657: no harness mounts two concurrent runs
 * with one backgrounded to a real gate-open frame, and the gap is mechanical
 * and file-local, so this test pins it directly against the real source. It
 * fails today and starts failing loudly the moment a background gate bridge
 * is added, which is the signal to remove the `fails: true` marker.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";

describe("DashboardLayout — ISS-649 background gate pause/resume bridge", () => {
  it("marks a background (non-viewed) run's notification gate-paused/resumed, not only the viewed run's", () => {
    const src = readFileSync(path.join(__dirname, "DashboardLayout.tsx"), "utf8");

    const markGatePausedCallSites = (src.match(/markGatePaused\(/g) ?? []).length;
    const markGateResumedCallSites = (src.match(/markGateResumed\(/g) ?? []).length;
    const hasBackgroundGateBridgeIdentifier = /backgroundGate/i.test(src);

    // ISS-649 unfixed: exactly one call site each, both inside the single
    // viewed-only effect, and no background-gate bridge identifier anywhere.
    expect(
      hasBackgroundGateBridgeIdentifier || markGatePausedCallSites > 1 || markGateResumedCallSites > 1,
    ).toBe(true);
  });
});
