import { beforeEach, describe, expect, it, vi } from "vitest";
import { configureStore } from "@reduxjs/toolkit";
import type { AgentDef } from "@/types/index";
import type { AgentLibraryResponse } from "@/store/api/agents";

const { library } = vi.hoisted(() => ({ library: vi.fn() }));

// System boundary: the HTTP adapter the thunk calls.
vi.mock("@/store/api/agents", () => ({ agentsApi: { library } }));

import agentsReducer, { agentsCleared, fetchAgentLibrary, type AgentsState } from "./agentsSlice";

const AGENT: AgentDef = {
  id: "ba",
  name: "Business Analyst",
  role: "analyst",
  description: "Writes stories",
  pipeline_type: "user_stories",
  order: 1,
  icon: "user",
  estimated_duration: 30,
  has_skill: false,
} as AgentDef;

function makeStore() {
  return configureStore({ reducer: { agents: agentsReducer } });
}

const INITIAL: AgentsState = {
  agents: [],
  totalCount: 0,
  pipelines: {},
  status: "idle",
  error: null,
};

describe("agentsSlice", () => {
  beforeEach(() => {
    library.mockReset();
  });

  it("returns the idle empty state when initialised", () => {
    expect(agentsReducer(undefined, { type: "@@INIT" })).toEqual(INITIAL);
  });

  describe("fetchAgentLibrary", () => {
    it("sets status to loading and clears a previous error when pending", async () => {
      const store = makeStore();
      library.mockRejectedValueOnce(new Error("boom"));
      await store.dispatch(fetchAgentLibrary());
      expect(store.getState().agents.error).toBe("boom");

      let resolve!: (value: AgentLibraryResponse) => void;
      library.mockReturnValueOnce(new Promise<AgentLibraryResponse>((r) => (resolve = r)));
      const pending = store.dispatch(fetchAgentLibrary());

      expect(store.getState().agents.status).toBe("loading");
      expect(store.getState().agents.error).toBeNull();

      resolve({ agents: [], total_count: 0, pipelines: {} });
      await pending;
    });

    it("stores agents, total count and pipelines when fulfilled", async () => {
      library.mockResolvedValueOnce({
        agents: [AGENT],
        total_count: 1,
        pipelines: { user_stories: 3 },
      });
      const store = makeStore();

      await store.dispatch(fetchAgentLibrary());

      expect(store.getState().agents).toEqual({
        agents: [AGENT],
        totalCount: 1,
        pipelines: { user_stories: 3 },
        status: "succeeded",
        error: null,
      });
    });

    it("falls back to empty collections when the payload omits every field", async () => {
      library.mockResolvedValueOnce({});
      const store = makeStore();

      await store.dispatch(fetchAgentLibrary());

      expect(store.getState().agents).toEqual({ ...INITIAL, status: "succeeded" });
    });

    it("records the error message when rejected with an Error", async () => {
      library.mockRejectedValueOnce(new Error("Network down"));
      const store = makeStore();

      await store.dispatch(fetchAgentLibrary());

      expect(store.getState().agents.status).toBe("failed");
      expect(store.getState().agents.error).toBe("Network down");
    });

    it("uses the default error message when the rejection carries no message", async () => {
      library.mockRejectedValueOnce({});
      const store = makeStore();

      await store.dispatch(fetchAgentLibrary());

      expect(store.getState().agents.status).toBe("failed");
      expect(store.getState().agents.error).toBe("Failed to fetch agent library");
    });

    it("keeps previously loaded agents when a later fetch is rejected", async () => {
      library.mockResolvedValueOnce({ agents: [AGENT], total_count: 1, pipelines: {} });
      const store = makeStore();
      await store.dispatch(fetchAgentLibrary());

      library.mockRejectedValueOnce(new Error("later failure"));
      await store.dispatch(fetchAgentLibrary());

      expect(store.getState().agents.agents).toEqual([AGENT]);
      expect(store.getState().agents.status).toBe("failed");
    });
  });

  describe("agentsCleared", () => {
    it("resets a populated slice back to the idle initial state", () => {
      const populated: AgentsState = {
        agents: [AGENT],
        totalCount: 1,
        pipelines: { user_stories: 3 },
        status: "failed",
        error: "stale error",
      };

      expect(agentsReducer(populated, agentsCleared())).toEqual(INITIAL);
    });
  });
});
