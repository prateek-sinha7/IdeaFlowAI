/**
 * ISS-648 — sibling of QA-PS-002 (ISS-644): a background/non-viewed run's
 * failure or cancellation is never reflected in its notification.
 *
 * `DashboardLayout`'s failure/cancellation effect (~line 905-917) is the ONLY
 * place `markFailed`/`markCancelled` are called, and it is gated solely on
 * `currentPipelineNotifId.current` — the ref documented at line 658-659 as
 * tracking "the CURRENTLY VIEWED run's notif". A run that fails or is
 * cancelled while it is not the viewed run never reaches this effect.
 *
 * The completion case (FIX-203) already solved the identical problem with a
 * dedicated background bridge: `backgroundCompletedRunId` (a prop set by
 * page.tsx on every pipeline_complete for a non-viewed run) plus a SEPARATE
 * effect (line ~697-729) that looks the notification up by `workflowRunId`
 * and calls `markCompleted` for it, independent of `currentPipelineNotifId`.
 * No equivalent exists for failure/cancellation.
 *
 * `DashboardLayout` has no harness that mounts two concurrent runs and
 * backgrounds one to a real SSE failure/cancel frame (the same class of gap
 * ISS-657's test documents for `page.tsx`). Per the card's own root-cause
 * analysis the gap is mechanical and file-local — no background bridge call
 * site exists at all — so this test pins that directly against the real,
 * current source. It fails today and starts failing loudly ("expected test
 * to fail") the moment a background bridge is added, which is the signal to
 * remove the `fails: true` marker.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";

describe("DashboardLayout — ISS-648 background failure/cancellation bridge", () => {
  it("marks a background (non-viewed) run's notification failed/cancelled, not only the viewed run's", () => {
    const src = readFileSync(path.join(__dirname, "DashboardLayout.tsx"), "utf8");

    // markFailed/markCancelled must each be called somewhere OTHER than the
    // single viewed-run effect gated on `currentPipelineNotifId.current` —
    // e.g. a background-bridge effect analogous to FIX-203's
    // `backgroundCompletedRunId` one, keyed off a prop such as
    // `backgroundFailedRunId` / `backgroundCancelledRunId`.
    const markFailedCallSites = (src.match(/markFailed\(/g) ?? []).length;
    const markCancelledCallSites = (src.match(/markCancelled\(/g) ?? []).length;
    const hasBackgroundBridgeIdentifier = /backgroundFailedRunId|backgroundCancelledRunId/.test(src);

    // ISS-648 unfixed: exactly one call site each, both inside the
    // viewed-only effect, and no background-bridge identifier anywhere.
    expect(
      hasBackgroundBridgeIdentifier || markFailedCallSites > 1 || markCancelledCallSites > 1,
    ).toBe(true);
  });
});
