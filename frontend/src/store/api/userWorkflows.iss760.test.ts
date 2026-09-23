/**
 * ISS-760 (QA-PS-025, sibling of ISS-705) — the save/load ("My Workflows")
 * layer has a THIRD, independently-declared restriction: `StepSelectionWire`
 * (userWorkflows.ts ~line 21) only types `strategy?: "fanout_batch" |
 * "wave_scheduler"`, and `manifestStepsToGateSelections`'s leaf-fan-out
 * branch (~line 793) only recognizes those two literal strings. Even if a
 * future fix lets the compose-time UI construct `strategy: "task_loop"`,
 * reopening a saved workflow with that step silently drops it — the file's
 * own comment documents this exact bug class already happening once before
 * for `wave_scheduler`. This pins the gap against the real, current source,
 * so it fails today and starts failing loudly once the reverse-mapping
 * recognizes task_loop.
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";

describe("userWorkflows StepSelectionWire / manifestStepsToGateSelections — ISS-760 task_loop dropped on reload", () => {
  it("recognizes task_loop in the wire type and the leaf fan-out reverse-mapping", () => {
    const src = readFileSync(path.join(__dirname, "userWorkflows.ts"), "utf8");

    // Sanity: the exact restrictive condition the card names must still be
    // here, otherwise this test is no longer pinning the right block.
    expect(src).toContain(
      '(step.strategy === "fanout_batch" || step.strategy === "wave_scheduler")',
    );

    // ISS-760 unfixed: neither the wire type nor the reverse-mapping
    // condition has any task_loop member/branch — a saved task_loop step
    // reopens with no strategy and no task_source.
    expect(src).toContain('"task_loop"');
  });
});
