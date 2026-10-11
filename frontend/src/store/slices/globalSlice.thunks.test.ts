import { beforeEach, describe, expect, it, vi } from "vitest";
import { configureStore } from "@reduxjs/toolkit";
import type { WorkflowSummary } from "@/store/api/workflows";
import type { WorkflowRun } from "@/types/index";

const { list, getToken, getWorkflows } = vi.hoisted(() => ({
  list: vi.fn(),
  getToken: vi.fn(),
  getWorkflows: vi.fn(),
}));

// System boundaries: workflow catalog HTTP adapter, token storage, runs REST helper.
vi.mock("@/store/api/workflows", () => ({ workflowsApi: { list } }));
vi.mock("@/lib/api", () => ({ getToken, getWorkflows }));

import globalReducer, {
  fetchRecentRuns,
  fetchWorkflows,
  globalCleared,
  type GlobalState,
} from "./globalSlice";

const WORKFLOW = {
  id: "prototype",
  name: "Prototype",
  description: "",
  step_count: 0,
  steps: [],
  user_launchable: true,
} as WorkflowSummary;

const RUN = { id: "run-1", title: "First run" } as WorkflowRun;

const INITIAL: GlobalState = {
  workflows: [],
  workflowsStatus: "idle",
  workflowsError: null,
  recentRuns: [],
  recentRunsStatus: "idle",
  recentRunsError: null,
};

function makeStore() {
  return configureStore({ reducer: { global: globalReducer } });
}

describe("globalSlice", () => {
  beforeEach(() => {
    list.mockReset();
    getToken.mockReset();
    getWorkflows.mockReset();
  });

  it("returns the idle empty state when initialised", () => {
    expect(globalReducer(undefined, { type: "@@INIT" })).toEqual(INITIAL);
  });

  describe("fetchWorkflows", () => {
    it("sets workflowsStatus to loading and clears a previous error when pending", async () => {
      const store = makeStore();
      list.mockRejectedValueOnce(new Error("boom"));
      await store.dispatch(fetchWorkflows());
      expect(store.getState().global.workflowsError).toBe("boom");

      let resolve!: (value: WorkflowSummary[]) => void;
      list.mockReturnValueOnce(new Promise<WorkflowSummary[]>((r) => (resolve = r)));
      const pending = store.dispatch(fetchWorkflows());

      expect(store.getState().global.workflowsStatus).toBe("loading");
      expect(store.getState().global.workflowsError).toBeNull();

      resolve([]);
      await pending;
    });

    it("stores the catalog when fulfilled", async () => {
      list.mockResolvedValueOnce([WORKFLOW]);
      const store = makeStore();

      await store.dispatch(fetchWorkflows());

      expect(store.getState().global).toEqual({
        ...INITIAL,
        workflows: [WORKFLOW],
        workflowsStatus: "succeeded",
      });
    });

    it("records the error message when rejected with an Error", async () => {
      list.mockRejectedValueOnce(new Error("Network down"));
      const store = makeStore();

      await store.dispatch(fetchWorkflows());

      expect(store.getState().global.workflowsStatus).toBe("failed");
      expect(store.getState().global.workflowsError).toBe("Network down");
    });

    it("uses the default error message when the rejection carries no message", async () => {
      list.mockRejectedValueOnce({});
      const store = makeStore();

      await store.dispatch(fetchWorkflows());

      expect(store.getState().global.workflowsStatus).toBe("failed");
      expect(store.getState().global.workflowsError).toBe("Failed to fetch workflows");
    });
  });

  describe("fetchRecentRuns", () => {
    it("sets recentRunsStatus to loading and clears a previous error when pending", async () => {
      const store = makeStore();
      getToken.mockReturnValue(null);
      await store.dispatch(fetchRecentRuns());
      expect(store.getState().global.recentRunsError).toBe("Not authenticated.");

      getToken.mockReturnValue("tok");
      let resolve!: (value: { runs: WorkflowRun[]; total: number }) => void;
      getWorkflows.mockReturnValueOnce(
        new Promise<{ runs: WorkflowRun[]; total: number }>((r) => (resolve = r)),
      );
      const pending = store.dispatch(fetchRecentRuns());

      expect(store.getState().global.recentRunsStatus).toBe("loading");
      expect(store.getState().global.recentRunsError).toBeNull();

      resolve({ runs: [], total: 0 });
      await pending;
    });

    it("requests the six most recent runs with the stored token and stores them", async () => {
      getToken.mockReturnValue("tok-123");
      getWorkflows.mockResolvedValueOnce({ runs: [RUN], total: 1 });
      const store = makeStore();

      await store.dispatch(fetchRecentRuns());

      expect(getWorkflows).toHaveBeenCalledWith("tok-123", { limit: 6 });
      expect(store.getState().global).toEqual({
        ...INITIAL,
        recentRuns: [RUN],
        recentRunsStatus: "succeeded",
      });
    });

    it("fails with 'Not authenticated.' and skips the request when no token is stored", async () => {
      getToken.mockReturnValue(null);
      const store = makeStore();

      await store.dispatch(fetchRecentRuns());

      expect(getWorkflows).not.toHaveBeenCalled();
      expect(store.getState().global.recentRunsStatus).toBe("failed");
      expect(store.getState().global.recentRunsError).toBe("Not authenticated.");
    });

    it("records the error message when the runs request is rejected", async () => {
      getToken.mockReturnValue("tok");
      getWorkflows.mockRejectedValueOnce(new Error("Server error"));
      const store = makeStore();

      await store.dispatch(fetchRecentRuns());

      expect(store.getState().global.recentRunsStatus).toBe("failed");
      expect(store.getState().global.recentRunsError).toBe("Server error");
    });

    it("uses the default error message when the rejection carries no message", async () => {
      getToken.mockReturnValue("tok");
      getWorkflows.mockRejectedValueOnce({});
      const store = makeStore();

      await store.dispatch(fetchRecentRuns());

      expect(store.getState().global.recentRunsStatus).toBe("failed");
      expect(store.getState().global.recentRunsError).toBe("Failed to fetch recent runs");
    });
  });

  describe("globalCleared", () => {
    it("resets every field of a populated slice back to the idle initial state", () => {
      const populated: GlobalState = {
        workflows: [WORKFLOW],
        workflowsStatus: "failed",
        workflowsError: "stale workflows error",
        recentRuns: [RUN],
        recentRunsStatus: "failed",
        recentRunsError: "stale runs error",
      };

      expect(globalReducer(populated, globalCleared())).toEqual(INITIAL);
    });
  });
});
