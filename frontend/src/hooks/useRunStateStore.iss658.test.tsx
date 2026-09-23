/**
 * ISS-658 — QA-PS-002: retiring the wrong regression test.
 *
 * The original `NotificationPanel.iss658.test.tsx` asserted that the panel
 * merges a fabricated `notifications` entry's `agentsCompleted` into a live
 * row — but the panel deliberately drops running/gate items from
 * `notifications` (`NotificationPanel.tsx:212-214`) and production never
 * hands DashboardLayout a running notification to begin with
 * (`DashboardLayout.tsx:2695`). Turning that test green would require code
 * that is unreachable in production and reads a field
 * (`useNotifications`'s `agentsCompleted`) that ISS-644's own theory already
 * showed is the wrong one. This card asked the test-writer to re-point
 * coverage at the real mechanism instead of retiring it outright.
 *
 * The real mechanism (confirmed by ISS-679, which corrects ISS-673): the
 * "0 of N" the panel/header actually draw comes from `runAgentsCompletedMap`,
 * built from `useRunStateStore`'s per-run ref (`page.tsx:3894-3900`). That
 * store lives inside `page.tsx`'s own component body
 * (`useRunStateStore.ts:274`, a plain `useRef`), so a client-side navigation
 * or reload that remounts `page.tsx` throws the whole map away. The roster a
 * run needs before `agent_complete` can advance its count is seeded ONLY by
 * `pipeline_start` (`useWorkflow.ts:404-410`); nothing re-seeds it for a
 * run that is not the one named in the URL. So a backgrounded run's
 * `agent_complete` frames arrive at a fresh, empty store after a remount and
 * are silently dropped (`useWorkflow.ts:705-706`'s "agent not in roster"
 * guard) — the completed count for that run is stuck at 0 forever, not just
 * stale.
 *
 * This test reproduces exactly that: one store instance receives
 * `pipeline_start` for a backgrounded run, is torn down (simulating the
 * remount), and a fresh store instance then receives that run's
 * `agent_complete` frames. Correct behaviour is that the run's real progress
 * still reaches the new instance; today it does not.
 */
import { describe, expect, it } from "vitest";
import { act, render, screen, cleanup } from "@testing-library/react";
import { useEffect } from "react";
import { useRunStateStore } from "./useRunStateStore";

let store: ReturnType<typeof useRunStateStore>;

function Harness() {
  const runStore = useRunStateStore();
  useEffect(() => {
    store = runStore;
  });
  return <span data-testid="bg-count">{runStore.get("run-bg")?.pipelineState.completedCount ?? 0}</span>;
}

const ROSTER = [
  { id: "a1", name: "Agent 1", role: "r", icon: "i", order: 1 },
  { id: "a2", name: "Agent 2", role: "r", icon: "i", order: 2 },
  { id: "a3", name: "Agent 3", role: "r", icon: "i", order: 3 },
];

describe("useRunStateStore — ISS-658 re-pointed at ISS-679's remount mechanism (QA-PS-002)", () => {
  it("a backgrounded run's completed-agent count survives a page remount", () => {
    const { unmount } = render(<Harness />);

    act(() => {
      store.switchViewTo("run-viewed");
      store.handleFrame("run-bg", { type: "pipeline_start", data: { pipeline_run_id: "run-bg", agents: ROSTER } });
    });
    expect(screen.getByTestId("bg-count")).toHaveTextContent("0");

    // Simulate a client-side navigation (router.push) or reload remounting
    // page.tsx — the store's backing useRef is scoped to this component
    // instance, so it is discarded here exactly as it would be in the app.
    unmount();
    cleanup();
    render(<Harness />);

    act(() => {
      store.switchViewTo("run-viewed");
      store.handleFrame("run-bg", { type: "agent_complete", data: { agent_id: "a1" } });
      store.handleFrame("run-bg", { type: "agent_complete", data: { agent_id: "a2" } });
    });

    // Expected/correct behaviour: the run's real progress (2 of 3 agents)
    // reaches the new store instance regardless of the remount in between.
    expect(store.get("run-bg")?.pipelineState.completedCount).toBe(2);
    expect(screen.getByTestId("bg-count")).toHaveTextContent("2");
  });
});
