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

    const marker = 'strategy?: "fanout_batch" | "wave_scheduler";';
    const idx = src.indexOf(marker);
    // Sanity: the exact restrictive union the card names must still be here,
    // otherwise this test is no longer pinning the right line.
    expect(idx).toBeGreaterThan(-1);

    // ISS-705 unfixed: the strategy union has no task_loop member anywhere
    // in the file, so a step downstream of a task-emitting planner can never
    // be wired to consume it via task_loop through this UI.
    expect(src).toContain('"task_loop"');
  });
});
