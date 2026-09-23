/**
 * ISS-679 / QA-PS-002: the guards on the run store's module-scope lifetime.
 *
 * The per-run maps outlive a page.tsx remount so a background run keeps its
 * roster (useRunStateStore.iss658.test.tsx covers that). Three guards come with it:
 *   - only in-flight runs cross a remount: a finished run replayed into the entry
 *     that already holds it loses its revision count (ISS-063);
 *   - an unmounted page's late writes go nowhere, for the same reason;
 *   - the maps belong to one signed-in user (JWT `sub`, ISS-188/ISS-201): a token
 *     refresh keeps them, a different user starts empty.
 */
import { afterEach, describe, expect, it } from "vitest";
import { act, cleanup, render } from "@testing-library/react";
import { useEffect } from "react";
import { useRunStateStore } from "./useRunStateStore";

let store: ReturnType<typeof useRunStateStore>;

function Harness() {
  const runStore = useRunStateStore();
  useEffect(() => {
    store = runStore;
  });
  return null;
}

function remount() {
  cleanup();
  render(<Harness />);
}

const b64url = (o: object) => btoa(JSON.stringify(o)).replace(/=+$/, "").replace(/\+/g, "-").replace(/\//g, "_");
const tokenFor = (sub: string, n: number) => `${b64url({ alg: "none" })}.${b64url({ sub, n })}.sig`;

const ROSTER = [
  { id: "a1", name: "Agent 1", role: "r", icon: "i", order: 1 },
  { id: "a2", name: "Agent 2", role: "r", icon: "i", order: 2 },
];

// A finished run with one spec revision: the head agent a1 starts twice.
const FINISHED_WITH_REVISION = [
  { type: "pipeline_start", data: { pipeline_run_id: "run-done", agents: ROSTER, seq: 1, event_id: "e1" } },
  { type: "agent_start", data: { agent_id: "a1", seq: 2, event_id: "e2" } },
  { type: "agent_complete", data: { agent_id: "a1", seq: 3, event_id: "e3" } },
  { type: "agent_start", data: { agent_id: "a2", seq: 4, event_id: "e4" } },
  { type: "agent_complete", data: { agent_id: "a2", seq: 5, event_id: "e5" } },
  { type: "agent_start", data: { agent_id: "a1", seq: 6, event_id: "e6" } },
  { type: "agent_complete", data: { agent_id: "a1", seq: 7, event_id: "e7" } },
  { type: "pipeline_complete", data: { seq: 8, event_id: "e8" } },
];

afterEach(() => {
  cleanup();
  localStorage.removeItem("auth_token");
});

describe("useRunStateStore — what survives a page remount (ISS-679)", () => {
  it("a finished run reopened after a remount keeps its revision count", () => {
    render(<Harness />);
    act(() => {
      store.switchViewTo("run-done");
      for (const f of FINISHED_WITH_REVISION) store.handleFrame("run-done", f);
    });
    expect(store.get("run-done")?.specRevisionCount).toBe(1);

    remount();
    act(() => {
      store.switchViewTo("run-done");
      for (const f of FINISHED_WITH_REVISION) store.handleFrame("run-done", f);
    });
    expect(store.get("run-done")?.specRevisionCount).toBe(1);
  });

  it("a replay the unmounted page finishes late cannot zero the new page's revision count", () => {
    // A reopen click starts handleSelectWorkflowRun in the old page, then router.push
    // remounts it; the old page's replay resolves after the unmount.
    render(<Harness />);
    const unmountedPage = store;
    act(() => unmountedPage.switchViewTo("run-late"));
    remount();

    const frames = FINISHED_WITH_REVISION.map((f) =>
      f.type === "pipeline_start" ? { ...f, data: { ...f.data, pipeline_run_id: "run-late" } } : f,
    );
    act(() => {
      for (const f of frames) unmountedPage.handleFrame("run-late", f);
    });
    act(() => {
      store.switchViewTo("run-late");
      for (const f of frames) store.handleFrame("run-late", f);
    });
    expect(store.get("run-late")?.specRevisionCount).toBe(1);
  });

  it("a token refresh for the same user keeps a running background run", () => {
    localStorage.setItem("auth_token", tokenFor("user-1", 1));
    render(<Harness />);
    act(() => {
      store.switchViewTo("run-viewed");
      store.handleFrame("run-refresh", { type: "pipeline_start", data: { pipeline_run_id: "run-refresh", agents: ROSTER } });
    });

    localStorage.setItem("auth_token", tokenFor("user-1", 2));
    remount();
    act(() => {
      store.switchViewTo("run-viewed");
      store.handleFrame("run-refresh", { type: "agent_complete", data: { agent_id: "a1" } });
    });
    expect(store.get("run-refresh")?.pipelineState.completedCount).toBe(1);
  });

  it("a different signed-in user never sees the previous user's running run", () => {
    localStorage.setItem("auth_token", tokenFor("user-1", 1));
    render(<Harness />);
    act(() => {
      store.switchViewTo("run-viewed");
      store.handleFrame("run-other", { type: "pipeline_start", data: { pipeline_run_id: "run-other", agents: ROSTER } });
    });

    localStorage.setItem("auth_token", tokenFor("user-2", 1));
    remount();
    expect(store.get("run-other")).toBeUndefined();
  });
});
