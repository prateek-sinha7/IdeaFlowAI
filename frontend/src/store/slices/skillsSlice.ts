import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { skillsLibraryApi, type GlobalSkillEntry, type SkillsLibraryFilterOption } from "@/store/api/skills";

export interface SkillsState {
  skills: GlobalSkillEntry[];
  totalCount: number;
  skillCategories: SkillsLibraryFilterOption[];
  status: "idle" | "loading" | "succeeded" | "failed";
  error: string | null;
}

const initialState: SkillsState = {
  skills: [],
  totalCount: 0,
  skillCategories: [],
  status: "idle",
  error: null,
};

// GET /api/skills/library — the global Skills catalog (folder-scanned from
// backend/skills/global/, distinct from GET /api/agents/skills' per-user
// overrides — see backend/app/agents/skills_catalog.py). Fetched once per
// sign-in via listenerMiddleware.ts, same trigger point as fetchAgentLibrary.
export const fetchSkills = createAsyncThunk("skills/fetchList", async () => {
  return skillsLibraryApi.library();
});

const skillsSlice = createSlice({
  name: "skills",
  initialState,
  reducers: {
    skillsCleared(state) {
      state.skills = [];
      state.totalCount = 0;
      state.skillCategories = [];
      state.status = "idle";
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchSkills.pending, (state) => {
        state.status = "loading";
        state.error = null;
      })
      .addCase(fetchSkills.fulfilled, (state, action) => {
        state.status = "succeeded";
        // `?? []` — see hooksSlice: consumers .map() these, so undefined is a
        // crash rather than an empty state.
        state.skills = action.payload.skills ?? [];
        state.totalCount = action.payload.total_count ?? 0;
        state.skillCategories = action.payload.categories ?? [];
      })
      .addCase(fetchSkills.rejected, (state, action) => {
        state.status = "failed";
        state.error = action.error.message ?? "Failed to fetch skills";
      });
  },
});

export const { skillsCleared } = skillsSlice.actions;
export default skillsSlice.reducer;
