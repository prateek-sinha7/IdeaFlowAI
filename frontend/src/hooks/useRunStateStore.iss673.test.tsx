/**
 * ISS-673 / ISS-674 — QA-PS-002: the notification panel, the header's running
 * badge and its "N Running" dropdown show "0 of N agents" for every run that is
 * not the one being viewed.
 *
 * page.tsx builds `runAgentsCompletedMap` inline on every render from
 * `runStore.get(run.id).pipelineState.completedCount`, and all three surfaces read
 * it (via AppHeader's `runningPipelines`). `useRunStateStore` writes a non-viewed
 * run's frames into a ref and re-renders only for the viewed run, so the store's
 * count was right while the screen stayed frozen at the last unrelated render.
 *
 * The harness reads the store exactly the way page.tsx does — during render —
 * views a different run, then delivers the background run's agent_complete frames
 * in their own act() so only a store-triggered re-render can refresh the text.
 */
import { describe, expect, it } from "vitest";
import { act, render, screen } from "@testing-library/react";
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

describe("useRunStateStore — ISS-673 background run progress reaches the screen", () => {
  // FIX-521 (the fix ISS-673 placed in the shared producer): handleFrame bumps a
  // state tick when a NON-viewed run's completedCount changes, so the consumer
  // re-renders; no other background frame does (FIX-224 flicker rule holds).
  // Scope: this covers a background run whose pipeline_start reached THIS store
  // instance. The page-remount case — QA-PS-002's own repro, where a new store never
  // sees pipeline_start — is ISS-679, pinned by useRunStateStore.remountLifetime.test.tsx.
  // The `{ fails: true }` xfail marker was removed once FIX-521 made this pass.
  it("re-renders its consumer when a non-viewed run completes an agent", () => {
    render(<Harness />);

    act(() => {
      store.switchViewTo("run-viewed");
      store.handleFrame("run-bg", { type: "pipeline_start", data: { pipeline_run_id: "run-bg", agents: ROSTER } });
    });
    expect(screen.getByTestId("bg-count")).toHaveTextContent("0");

    act(() => {
      store.handleFrame("run-bg", { type: "agent_complete", data: { agent_id: "a1" } });
      store.handleFrame("run-bg", { type: "agent_complete", data: { agent_id: "a2" } });
    });

    // The store itself is already right (the ref write works today)...
    expect(store.get("run-bg")?.pipelineState.completedCount).toBe(2);
    // ...but only a re-render puts it on screen.
    expect(screen.getByTestId("bg-count")).toHaveTextContent("2");
  });
});
