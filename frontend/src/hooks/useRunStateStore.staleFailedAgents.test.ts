import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useRunStateStore } from "@/hooks/useRunStateStore";

// A run that failed at one step, was resumed and then completed must not keep
// naming that step as the failure in the header ("Run failed · Story Writers").
describe("a resumed run that completes drops its earlier failed-agent list", () => {
  it("pipeline_failed then pipeline_complete leaves no failedAgents", () => {
    const { result } = renderHook(() => useRunStateStore());
    act(() => result.current.switchViewTo("run-1"));
    act(() =>
      result.current.handleFrame("run-1", {
        type: "pipeline_failed",
        pipeline_run_id: "run-1",
        agents_failed: ["custom-agent:us-write"],
        error: "Story Writers failed",
      }),
    );
    expect(result.current.viewed.pipelineState.failedAgents).toEqual(["custom-agent:us-write"]);

    // The resume replays a fresh pipeline_start before the run completes.
    act(() =>
      result.current.handleFrame("run-1", { type: "pipeline_start", pipeline_run_id: "run-1", agents: [] }),
    );

    act(() =>
      result.current.handleFrame("run-1", {
        type: "pipeline_complete",
        pipeline_run_id: "run-1",
        status: "completed",
      }),
    );
    const s = result.current.viewed.pipelineState;
    expect(s.failed).toBeFalsy();
    expect(s.failedAgents).toBeUndefined();
  });
});
