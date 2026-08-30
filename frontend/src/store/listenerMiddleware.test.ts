import { describe, expect, it, vi, beforeEach } from "vitest";
import { configureStore } from "@reduxjs/toolkit";
import authReducer, { signedIn } from "@/store/slices/authSlice";
import agentsReducer from "@/store/slices/agentsSlice";
import skillsReducer from "@/store/slices/skillsSlice";
import hooksReducer from "@/store/slices/hooksSlice";
import globalReducer, { fetchWorkflows, fetchRecentRuns } from "@/store/slices/globalSlice";
import type { WorkflowSummary } from "@/store/api/workflows";
import type { WorkflowRun } from "@/types/index";

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

const reducer = {
  auth: authReducer,
  agents: agentsReducer,
  skills: skillsReducer,
  hooks: hooksReducer,
  global: globalReducer,
};

/** Only the slice fields a case actually seeds; the rest fall back to the slice's
 *  own initial state. Typed per-slice rather than as `Record<string, unknown>` —
 *  that widened `preloadedState` enough to break configureStore's inference, so
 *  TS resolved `reducer` against the single-Reducer overload and rejected both
 *  the reducer map and the middleware tuple. */
type SeedState = { [K in keyof typeof reducer]?: Partial<ReturnType<(typeof reducer)[K]>> };

function makeStore(preloadedState: SeedState) {
  return configureStore({
    reducer,
    // Cast at the boundary only: a partial slice is what these cases deliberately
    // seed, and the reducers fill the rest.
    preloadedState: preloadedState as Parameters<typeof configureStore>[0]["preloadedState"],
    middleware: (getDefault) => getDefault().prepend(listenerMiddleware.middleware),
  });
}

describe("listenerMiddleware signedIn preload guard (ISS-200)", () => {
  beforeEach(() => vi.clearAllMocks());

  it("refetches recentRuns/workflows when signedIn fires for a DIFFERENT user, even though the prior account's fetch already succeeded", async () => {
    const store = makeStore({
      global: {
        // Sentinel rows: only the id is read, and only to prove the FIRST
        // account's data is what sits in the store when the second signs in.
        workflows: [{ id: "leaked-workflow" } as WorkflowSummary],
        workflowsStatus: "succeeded",
        workflowsError: null,
        recentRuns: [{ id: "leaked-run" } as WorkflowRun],
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
