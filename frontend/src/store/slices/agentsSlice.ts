import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { agentsApi } from "@/store/api/agents";
import type { AgentDef } from "@/types/index";

export interface AgentsState {
  agents: AgentDef[];
  totalCount: number;
  pipelines: Record<string, number>;
  status: "idle" | "loading" | "succeeded" | "failed";
  error: string | null;
}

const initialState: AgentsState = {
  agents: [],
  totalCount: 0,
  pipelines: {},
  status: "idle",
  error: null,
};

// GET /api/agents/library — folder-scan-backed, single source of truth for
// the agent registry (FIX-051/ISS-035). Fetched once per sign-in via the
// listener middleware in store/listenerMiddleware.ts, not on every render.
export const fetchAgentLibrary = createAsyncThunk("agents/fetchLibrary", async () => {
  return agentsApi.library();
});

const agentsSlice = createSlice({
  name: "agents",
  initialState,
  reducers: {
    agentsCleared(state) {
      state.agents = [];
      state.totalCount = 0;
      state.pipelines = {};
      state.status = "idle";
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchAgentLibrary.pending, (state) => {
        state.status = "loading";
        state.error = null;
      })
      .addCase(fetchAgentLibrary.fulfilled, (state, action) => {
        state.status = "succeeded";
        // `?? []` / `?? {}` — see hooksSlice: consumers .map()/index these, so
        // undefined is a crash rather than an empty state.
        state.agents = action.payload.agents ?? [];
        state.totalCount = action.payload.total_count ?? 0;
        state.pipelines = action.payload.pipelines ?? {};
      })
      .addCase(fetchAgentLibrary.rejected, (state, action) => {
        state.status = "failed";
        state.error = action.error.message ?? "Failed to fetch agent library";
      });
  },
});

export const { agentsCleared } = agentsSlice.actions;
export default agentsSlice.reducer;
