import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { hooksLibraryApi, type GlobalHookEntry, type HooksLibraryFilterOption } from "@/store/api/hooks";

export interface HooksState {
  hooks: GlobalHookEntry[];
  totalCount: number;
  hookEvents: HooksLibraryFilterOption[];
  status: "idle" | "loading" | "succeeded" | "failed";
  error: string | null;
}

const initialState: HooksState = {
  hooks: [],
  totalCount: 0,
  hookEvents: [],
  status: "idle",
  error: null,
};

// GET /api/hooks/library — the global Hooks catalog (folder-scanned from
// backend/hooks/global/, distinct from per-user hook configurations).
// See backend/app/agents/hooks_catalog.py. Fetched once per sign-in via
// listenerMiddleware.ts, same trigger point as fetchSkills/fetchAgentLibrary.
export const fetchHooks = createAsyncThunk("hooks/fetchList", async () => {
  return hooksLibraryApi.library();
});

const hooksSlice = createSlice({
  name: "hooks",
  initialState,
  reducers: {
    hooksCleared(state) {
      state.hooks = [];
      state.totalCount = 0;
      state.hookEvents = [];
      state.status = "idle";
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchHooks.pending, (state) => {
        state.status = "loading";
        state.error = null;
      })
      .addCase(fetchHooks.fulfilled, (state, action) => {
        state.status = "succeeded";
        // `?? []` is load-bearing: a malformed/empty payload would otherwise
        // set these to undefined, and every consumer calls .map() on them —
        // one bad response full-page-crashes the composer behind the error
        // boundary. An empty catalog is a degraded UI; undefined is a crash.
        state.hooks = action.payload.hooks ?? [];
        state.totalCount = action.payload.total_count ?? 0;
        state.hookEvents = action.payload.events ?? [];
      })
      .addCase(fetchHooks.rejected, (state, action) => {
        state.status = "failed";
        state.error = action.error.message ?? "Failed to fetch hooks";
      });
  },
});

export const { hooksCleared } = hooksSlice.actions;
export default hooksSlice.reducer;
