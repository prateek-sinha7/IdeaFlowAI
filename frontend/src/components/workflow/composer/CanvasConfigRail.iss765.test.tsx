/**
 * ISS-765 (QA-PS-025, sibling of ISS-705) — the Canvas node-graph composer
 * view has its OWN, independently hand-written "Fan out over a list" lever
 * in CanvasConfigRail.tsx (~lines 1258-1327): the toggle's `onToggle` only
 * ever writes `strategy: "fanout_batch"`, and the Batch/Waves `<select>`
 * only offers `fanout_batch`/`wave_scheduler` options. Fixing the Simple
 * view (AgentsPopup.tsx, ISS-705) alone leaves this second UI surface
 * unable to construct a `task_loop` selection too. This pins the gap
 * against the real, current source, so it fails today and starts failing
 * loudly once a task_loop path is added here.
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";

describe("CanvasConfigRail fan-out lever — ISS-765 task_loop unreachable from Canvas composer", () => {
  it("offers task_loop as a fan-out mode option, not just fanout_batch/wave_scheduler", () => {
    const src = readFileSync(path.join(__dirname, "CanvasConfigRail.tsx"), "utf8");

    // Sanity: the exact two-option select the card names must still be here,
    // otherwise this test is no longer pinning the right block.
    expect(src).toContain('<option value="fanout_batch">Batch — one pass</option>');
    expect(src).toContain('<option value="wave_scheduler">Waves — dependency-ordered</option>');

    // ISS-765 unfixed: no code path in this file can ever write
    // `strategy: "task_loop"` — the toggle's onToggle and the mode <select>
    // both hardcode the two fan-out values only.
    expect(src).toContain('"task_loop"');
  });
});
