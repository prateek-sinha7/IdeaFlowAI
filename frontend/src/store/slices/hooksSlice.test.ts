import { beforeEach, describe, expect, it, vi } from "vitest";
import { configureStore } from "@reduxjs/toolkit";
import type { GlobalHookEntry, HooksLibraryResponse } from "@/store/api/hooks";

const { library } = vi.hoisted(() => ({ library: vi.fn() }));

// System boundary: the HTTP adapter the thunk calls.
vi.mock("@/store/api/hooks", () => ({ hooksLibraryApi: { library } }));

import hooksReducer, { fetchHooks, hooksCleared, type HooksState } from "./hooksSlice";

const HOOK: GlobalHookEntry = {
  id: "lint-on-stop",
  name: "lint-on-stop",
  display_name: "Lint on stop",
  description: "Runs the linter",
  content: "run lint",
  event: "Stop",
  trigger: "*",
  compatible_agents: ["developer"],
  tags: ["quality"],
};

function makeStore() {
  return configureStore({ reducer: { hooks: hooksReducer } });
}

const INITIAL: HooksState = {
  hooks: [],
  totalCount: 0,
  hookEvents: [],
  status: "idle",
  error: null,
};

describe("hooksSlice", () => {
  beforeEach(() => {
    library.mockReset();
  });

  it("returns the idle empty state when initialised", () => {
    expect(hooksReducer(undefined, { type: "@@INIT" })).toEqual(INITIAL);
  });

  describe("fetchHooks", () => {
    it("sets status to loading and clears a previous error when pending", async () => {
      const store = makeStore();
      library.mockRejectedValueOnce(new Error("boom"));
      await store.dispatch(fetchHooks());
      expect(store.getState().hooks.error).toBe("boom");

      let resolve!: (value: HooksLibraryResponse) => void;
      library.mockReturnValueOnce(new Promise<HooksLibraryResponse>((r) => (resolve = r)));
      const pending = store.dispatch(fetchHooks());

      expect(store.getState().hooks.status).toBe("loading");
      expect(store.getState().hooks.error).toBeNull();

      resolve({ hooks: [], total_count: 0, events: [] });
      await pending;
    });

    it("stores hooks, total count and events when fulfilled", async () => {
      library.mockResolvedValueOnce({
        hooks: [HOOK],
        total_count: 1,
        events: [{ id: "Stop", label: "Stop" }],
      });
      const store = makeStore();

      await store.dispatch(fetchHooks());

      expect(store.getState().hooks).toEqual({
        hooks: [HOOK],
        totalCount: 1,
        hookEvents: [{ id: "Stop", label: "Stop" }],
        status: "succeeded",
        error: null,
      });
    });

    it("falls back to empty collections when the payload omits every field", async () => {
      library.mockResolvedValueOnce({});
      const store = makeStore();

      await store.dispatch(fetchHooks());

      expect(store.getState().hooks).toEqual({ ...INITIAL, status: "succeeded" });
    });

    it("records the error message when rejected with an Error", async () => {
      library.mockRejectedValueOnce(new Error("Network down"));
      const store = makeStore();

      await store.dispatch(fetchHooks());

      expect(store.getState().hooks.status).toBe("failed");
      expect(store.getState().hooks.error).toBe("Network down");
    });

    it("uses the default error message when the rejection carries no message", async () => {
      library.mockRejectedValueOnce({});
      const store = makeStore();

      await store.dispatch(fetchHooks());

      expect(store.getState().hooks.status).toBe("failed");
      expect(store.getState().hooks.error).toBe("Failed to fetch hooks");
    });

    it("keeps previously loaded hooks when a later fetch is rejected", async () => {
      library.mockResolvedValueOnce({ hooks: [HOOK], total_count: 1, events: [] });
      const store = makeStore();
      await store.dispatch(fetchHooks());

      library.mockRejectedValueOnce(new Error("later failure"));
      await store.dispatch(fetchHooks());

      expect(store.getState().hooks.hooks).toEqual([HOOK]);
      expect(store.getState().hooks.status).toBe("failed");
    });
  });

  describe("hooksCleared", () => {
    it("resets a populated slice back to the idle initial state", () => {
      const populated: HooksState = {
        hooks: [HOOK],
        totalCount: 1,
        hookEvents: [{ id: "Stop", label: "Stop" }],
        status: "failed",
        error: "stale error",
      };

      expect(hooksReducer(populated, hooksCleared())).toEqual(INITIAL);
    });
  });
});
