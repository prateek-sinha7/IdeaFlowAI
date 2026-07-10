/**
 * useNotifications — the pipeline-notification feed DATA layer (Phase 38, SC-2).
 *
 * These tests drive the hook's transition contract through `renderHook` + `act`:
 * a run enters via `addRunningNotification` and then transitions to one of the
 * four honest kinds — gate / running / done(completed) / failed — plus the
 * cancelled terminal. Today only `markCompleted` fires from DashboardLayout;
 * `markFailed`/`markCancelled` exist but are never called, and there is NO
 * `gate` kind at all (RED here on `markGatePaused` / `status:"gate"`).
 *
 * Proves:
 *   1. addRunning -> markGatePaused(id): item status becomes "gate" (paused, not
 *      terminal — no completedAt); RED now, markGatePaused does not yet exist.
 *   2. addRunning -> markFailed(id): status "failed", completedAt set.
 *   3. addRunning -> markCancelled(id): status "cancelled", completedAt set.
 *   4. the status union accepts "gate" at the type level (compiles once added).
 */
import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useNotifications, type PipelineNotification } from "./useNotifications";

const RUN_ID = "run-1";

function addRunning(result: { current: ReturnType<typeof useNotifications> }) {
  act(() => {
    result.current.addRunningNotification(RUN_ID, "prototype", "Build a login flow", 4);
  });
}

describe("useNotifications transitions", () => {
  it("markGatePaused(id) moves the run to the gate kind (paused, no completedAt)", () => {
    const { result } = renderHook(() => useNotifications());
    addRunning(result);
    act(() => {
      result.current.markGatePaused(RUN_ID);
    });
    const n = result.current.notifications.find((x) => x.id === RUN_ID)!;
    expect(n.status).toBe("gate");
    // gate is a PAUSED, not terminal, state — mirrors markFailed otherwise but
    // does NOT stamp completedAt.
    expect(n.completedAt).toBeUndefined();
  });

  it("markFailed(id) moves the run to failed and stamps completedAt", () => {
    const { result } = renderHook(() => useNotifications());
    addRunning(result);
    act(() => {
      result.current.markFailed(RUN_ID);
    });
    const n = result.current.notifications.find((x) => x.id === RUN_ID)!;
    expect(n.status).toBe("failed");
    expect(n.completedAt).toBeInstanceOf(Date);
  });

  it("markCancelled(id) moves the run to cancelled and stamps completedAt", () => {
    const { result } = renderHook(() => useNotifications());
    addRunning(result);
    act(() => {
      result.current.markCancelled(RUN_ID);
    });
    const n = result.current.notifications.find((x) => x.id === RUN_ID)!;
    expect(n.status).toBe("cancelled");
    expect(n.completedAt).toBeInstanceOf(Date);
  });

  it("the status union accepts the gate kind at the type level", () => {
    // Compile-time assertion: "gate" is a legal PipelineNotification["status"].
    const gateStatus: PipelineNotification["status"] = "gate";
    expect(gateStatus).toBe("gate");
  });
});
