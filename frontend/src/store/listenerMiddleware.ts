import { createListenerMiddleware } from "@reduxjs/toolkit";
import { signedIn, signedOut } from "@/store/slices/authSlice";
import { fetchAgentLibrary, agentsCleared } from "@/store/slices/agentsSlice";
import { fetchSkills, skillsCleared } from "@/store/slices/skillsSlice";
import { fetchHooks, hooksCleared } from "@/store/slices/hooksSlice";
import { fetchWorkflows, fetchRecentRuns, globalCleared } from "@/store/slices/globalSlice";
import type { RootState, AppDispatch } from "@/store/index";

export const listenerMiddleware = createListenerMiddleware();

// `signedIn` fires only from the dashboard/home page's mount-time auth check
// (the app's landing route — "/" just redirects to "/login", and /dashboard
// is where it lands). Preloading here means agents/skills/workflows are
// already in the store by the time the user opens the Library or catalog
// tabs inside DashboardLayout — no fetch-on-open latency. Guarded so
// remounts within the same session don't refetch.
listenerMiddleware.startListening({
  actionCreator: signedIn,
  effect: async (_action, listenerApi) => {
    const dispatch = listenerApi.dispatch as AppDispatch;
    const state = listenerApi.getState() as RootState;
    // Workflows + recent runs first, in parallel — both feed HomeLaunchGrid's
    // (the landing view) first paint. Agents/skills back the Library/catalog
    // tabs, opened later, so they follow after.
    const preloadHome: Promise<unknown>[] = [];
    if (state.global.workflowsStatus !== "loading" && state.global.workflowsStatus !== "succeeded") {
      preloadHome.push(dispatch(fetchWorkflows()));
    }
    if (state.global.recentRunsStatus !== "loading" && state.global.recentRunsStatus !== "succeeded") {
      preloadHome.push(dispatch(fetchRecentRuns()));
    }
    await Promise.all(preloadHome);

    // Load agents, skills, hooks in parallel
    const preloadLibrary: Promise<unknown>[] = [];
    if (state.agents.status !== "loading" && state.agents.status !== "succeeded") {
      preloadLibrary.push(dispatch(fetchAgentLibrary()));
    }
    if (state.skills.status !== "loading" && state.skills.status !== "succeeded") {
      preloadLibrary.push(dispatch(fetchSkills()));
    }
    if (state.hooks.status !== "loading" && state.hooks.status !== "succeeded") {
      preloadLibrary.push(dispatch(fetchHooks()));
    }
    await Promise.all(preloadLibrary);
  },
});

listenerMiddleware.startListening({
  actionCreator: signedOut,
  effect: (_action, listenerApi) => {
    listenerApi.dispatch(agentsCleared());
    listenerApi.dispatch(skillsCleared());
    listenerApi.dispatch(hooksCleared());
    listenerApi.dispatch(globalCleared());
  },
});
