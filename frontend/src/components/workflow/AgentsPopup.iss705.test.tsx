/**
 * ISS-705 (QA-PS-025) — the Simple-view composer's only planner->worker
 * connector lever is `StepSelection.strategy`, typed
 * `"fanout_batch" | "wave_scheduler"` (AgentsPopup.tsx ~line 1397).
 * `task_loop` is not a member of that union, so no selection the composer UI
 * can ever construct carries it — even though the backend overlay
 * (engine.py `_apply_selections`) is fully generic and would carry it
 * through if the frontend ever sent it. This pins the exact gap against the
 * real, current source, so it fails today and starts failing loudly (the
 * soft assertion flips) once `task_loop` is added to the union.
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";

describe("StepSelection.strategy — ISS-705 task_loop unreachable from Simple composer", () => {
  it("includes task_loop as a selectable strategy value", () => {
    const src = readFileSync(path.join(__dirname, "AgentsPopup.tsx"), "utf8");

    // ISS-705 resolved (landed via 9efb704d): the lock now pins the FIXED union.
    // The old sanity marker — the restrictive `"fanout_batch" | "wave_scheduler";`
    // line — pinned the pre-fix source, so it could only pass while the bug stood.
    // A bare `toContain('"task_loop"')` is not enough on its own: the string also
    // appears in comments. Pin the type member AND the selectable <option>.
    expect(src).toContain('strategy?: "fanout_batch" | "wave_scheduler" | "task_loop";');
    expect(src).toContain('<option value="task_loop">');
    // The restrictive two-member union must be gone.
    expect(src).not.toContain('strategy?: "fanout_batch" | "wave_scheduler";');
  });
});
