import { describe, expect, it, vi, beforeEach } from "vitest";
import { configureStore } from "@reduxjs/toolkit";
import authReducer, { signedIn } from "@/store/slices/authSlice";
import agentsReducer from "@/store/slices/agentsSlice";
import skillsReducer from "@/store/slices/skillsSlice";
import hooksReducer from "@/store/slices/hooksSlice";
import globalReducer, { fetchWorkflows, fetchRecentRuns } from "@/store/slices/globalSlice";

// ─────────────────────────────────────────────────────────────────
// ISS-200 — listenerMiddleware's `signedIn` preload guard gates ONLY on
// fetch status (`workflowsStatus`/`recentRunsStatus` !== "loading"/"succeeded"),
// never on WHICH user that "succeeded" status belongs to. Sibling of ISS-188
// (BUG-20260827-234030-create): once one account's preload has resolved
// "succeeded" in the store, a second `signedIn` for a DIFFERENT account never
// re-triggers `fetchWorkflows`/`fetchRecentRuns`, so the first account's data
// stays in `state.global` for the second account to read.
//
// Never hits the network: `@/store/api/workflows` and `@/lib/api` are mocked
// so only the synchronous `.pending` dispatch (fired by createAsyncThunk
// before any await) is observed — that's enough to prove whether the
// listener even attempted a refetch.
// ─────────────────────────────────────────────────────────────────

vi.mock("@/store/api/workflows", () => ({
  workflowsApi: { list: vi.fn(() => new Promise(() => {})) }, // never resolves
}));
vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getWorkflows: vi.fn(() => new Promise(() => {})),
}));

import { listenerMiddleware } from "@/store/listenerMiddleware";

function makeStore(preloadedState: Record<string, unknown>) {
  return configureStore({
    reducer: {
      auth: authReducer,
      agents: agentsReducer,
      skills: skillsReducer,
      hooks: hooksReducer,
      global: globalReducer,
    },
    preloadedState,
    middleware: (getDefault) => getDefault().prepend(listenerMiddleware.middleware),
  });
}

describe("listenerMiddleware signedIn preload guard (ISS-200)", () => {
  beforeEach(() => vi.clearAllMocks());

  it("refetches recentRuns/workflows when signedIn fires for a DIFFERENT user, even though the prior account's fetch already succeeded", async () => {
    const store = makeStore({
      global: {
        workflows: [{ id: "leaked-workflow" }],
        workflowsStatus: "succeeded",
        workflowsError: null,
        recentRuns: [{ id: "leaked-run" }],
        recentRunsStatus: "succeeded",
        recentRunsError: null,
      },
    });

    // Dispatch signedIn for a NEW user and inspect whether
    // workflowsStatus/recentRunsStatus flip to "loading" — that only
    // happens if the listener actually dispatched
    // fetchWorkflows()/fetchRecentRuns() for this new sign-in.
    store.dispatch(signedIn({ token: "different-users-token", user: { id: "user-b" } as never }));

    // Let the listener's synchronous startListening effect body run its
    // first microtask tick (the guard check + dispatch happen before the
    // first `await`).
    await Promise.resolve();
    await Promise.resolve();

    const state = store.getState();
    expect(state.global.workflowsStatus).toBe("loading");
    expect(state.global.recentRunsStatus).toBe("loading");
  });
});
