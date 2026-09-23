/**
 * BUG A11-1 — the gate card missing after a reload of a `waiting_for_user` run.
 *
 * A replayed/re-armed `review_gate_ready` can reach the store BEFORE (or
 * without) `pipeline_start` ever landing for the run — the backend's D-14g SSE
 * re-arm re-emits a dangling `review_gate_ready` ALONE on reconnect (no
 * `pipeline_start`), and even on a fresh reload the SSE attach and the REST
 * durable replay (`getRunEvents`) are two independent network calls that can
 * resolve in either order. `page.tsx`'s `review_gate_ready` switch-case is the
 * ONE place `reviewGateData` gets written; this test pins that it ALSO forces
 * `pipelineState.isRunning` (and `gateOpen`) true there, mirroring the exact
 * two `runStore` calls the switch-case makes, WITHOUT ever replaying a
 * `pipeline_start` frame first — the scenario that left `isRunning` stuck
 * `false` and hid the Approve/Reject card (StepsOverviewSpine's
 * `gateActive`/`showGateFallback` are both `&& isRunning`) even though the
 * header/transcript (gated on `reviewGateData` alone) already read "gate".
 */

import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useRunStateStore } from "@/hooks/useRunStateStore";
import type { ReviewGateData } from "@/hooks/useRunStateStore";

const GATE_DATA: ReviewGateData = {
  gateKey: "run-1:shell-builder:0",
  agentId: "shell-builder",
  agentName: "Shell Builder",
  output: "{\"tasks\":[]}",
  pipelineRunId: "run-1",
  redoable: false,
  updateSpecsEligible: false,
  artifactKind: "task_list",
  revisionCycle: 0,
  revisionInFlight: false,
};

/** Mirrors the EXACT two `runStore` calls page.tsx's `review_gate_ready`
 *  switch-case makes (the fix under test), so this stays a source-faithful
 *  reproduction rather than testing invented store behavior. */
function applyReviewGateReady(
  store: ReturnType<typeof useRunStateStore>,
  runId: string,
  gateData: ReviewGateData,
) {
  store.update(runId, { reviewGateData: gateData });
  store.updatePipelineState(runId, (prev) =>
    prev.isRunning ? prev : { ...prev, isRunning: true, gateOpen: true },
  );
}

describe("BUG A11-1 — review_gate_ready replay without a prior pipeline_start", () => {
  it("populates reviewGateData AND flips isRunning true, with no pipeline_start ever replayed", () => {
    const { result } = renderHook(() => useRunStateStore());

    act(() => {
      // Mirrors handleSelectWorkflowRun's synchronous viewport switch, BEFORE
      // any durable replay/SSE frame arrives.
      result.current.switchViewTo("run-1");
    });
    act(() => {
      applyReviewGateReady(result.current, "run-1", GATE_DATA);
    });

    expect(result.current.viewed.reviewGateData).toEqual(GATE_DATA);
    // The precondition StepsOverviewSpine's gateActive/showGateFallback both
    // require (isRunning) — this is what was stuck false before the fix.
    expect(result.current.viewed.pipelineState.isRunning).toBe(true);
    expect(result.current.viewed.pipelineState.gateOpen).toBe(true);
  });

  it("does not clobber an isRunning already set true by an earlier pipeline_start", () => {
    const { result } = renderHook(() => useRunStateStore());

    act(() => {
      result.current.switchViewTo("run-1");
      result.current.handleFrame("run-1", {
        type: "pipeline_start",
        pipeline_run_id: "run-1",
        agents: [{ id: "shell-builder", name: "Shell Builder", role: "build" }],
      });
    });
    act(() => {
      applyReviewGateReady(result.current, "run-1", GATE_DATA);
    });

    expect(result.current.viewed.pipelineState.isRunning).toBe(true);
    expect(result.current.viewed.pipelineState.agents.length).toBe(1);
    expect(result.current.viewed.reviewGateData).toEqual(GATE_DATA);
  });

  it("review_gate_approved clears gateOpen without forcing isRunning false (the run resumes, it does not end)", () => {
    const { result } = renderHook(() => useRunStateStore());

    act(() => {
      result.current.switchViewTo("run-1");
    });
    act(() => {
      applyReviewGateReady(result.current, "run-1", GATE_DATA);
    });
    act(() => {
      // Mirrors the review_gate_approved switch-case's two runStore calls.
      result.current.update("run-1", { reviewGateData: null });
      result.current.updatePipelineState("run-1", (prev) =>
        prev.gateOpen ? { ...prev, gateOpen: false } : prev,
      );
    });

    expect(result.current.viewed.reviewGateData).toBeNull();
    expect(result.current.viewed.pipelineState.gateOpen).toBe(false);
    expect(result.current.viewed.pipelineState.isRunning).toBe(true);
  });

  it("a later pipeline_complete still wins — the fix is one-way, never overrides a real terminal", () => {
    const { result } = renderHook(() => useRunStateStore());

    act(() => {
      result.current.switchViewTo("run-1");
    });
    act(() => {
      applyReviewGateReady(result.current, "run-1", GATE_DATA);
    });
    act(() => {
      result.current.handleFrame("run-1", {
        type: "pipeline_complete",
        pipeline_run_id: "run-1",
      });
    });

    expect(result.current.viewed.pipelineState.isRunning).toBe(false);
  });
});
