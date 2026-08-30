import { createListenerMiddleware } from "@reduxjs/toolkit";
import { signedIn, signedOut } from "@/store/slices/authSlice";
import { fetchAgentLibrary, agentsCleared } from "@/store/slices/agentsSlice";
import { fetchSkills, skillsCleared } from "@/store/slices/skillsSlice";
import { fetchHooks, hooksCleared } from "@/store/slices/hooksSlice";
import { fetchWorkflows, fetchRecentRuns, globalCleared } from "@/store/slices/globalSlice";
import type { RootState, AppDispatch } from "@/store/index";

export const listenerMiddleware = createListenerMiddleware();

/** Drop every per-account preloaded slice, so nothing survives into another session. */
function clearPreloads(dispatch: AppDispatch): void {
  dispatch(agentsCleared());
  dispatch(skillsCleared());
  dispatch(hooksCleared());
  dispatch(globalCleared());
}

// `signedIn` fires only from the dashboard/home page's mount-time auth check
// (the app's landing route — "/" just redirects to "/login", and /dashboard
// is where it lands). Preloading here means agents/skills/workflows are
// already in the store by the time the user opens the Library or catalog
// tabs inside DashboardLayout — no fetch-on-open latency. Guarded so
// remounts within the same session don't refetch.
listenerMiddleware.startListening({
  actionCreator: signedIn,
  effect: async (action, listenerApi) => {
    const dispatch = listenerApi.dispatch as AppDispatch;
    // ISS-200: the guards below know only WHETHER a preload succeeded, never
    // WHOSE it was. A `signedIn` carrying a different token than the one already
    // in the store is an account switch — soft, because handleLogout dispatches
    // signedOut and handleSessionExpiry hard-navigates, so anything that reaches
    // here with a new token bypassed both. Drop the previous account's preload
    // first; the guards then see "idle" and refetch for the new user.
    // getOriginalState() must be read before the first await.
    const previousToken = (listenerApi.getOriginalState() as RootState).auth.token;
    if (previousToken !== action.payload.token) clearPreloads(dispatch);
    const state = listenerApi.getState() as RootState;
    // Workflows + recent runs feed HomeLaunchGrid's (the landing view) first
    // paint; agents/skills/hooks back the Library/catalog tabs.
    // ISS-232: these two groups used to be AWAITED IN SEQUENCE, on the premise
    // that the Library tabs are "opened later". A cold/deep-linked
    // /library/{type}/{slug} breaks that premise — LibraryPage's URL-seed
    // effect can only open the detail modal once its catalog reaches
    // "succeeded", so the sequential await left the plain listing rendered
    // under the detail URL for as long as the home pair took (measured 12.2s
    // on a slow /api/workflows). All five are independent GETs against
    // different endpoints, so they go out together and the home pair still
    // resolves no later than it did before.
    const preloadHome: Promise<unknown>[] = [];
    if (state.global.workflowsStatus !== "loading" && state.global.workflowsStatus !== "succeeded") {
      preloadHome.push(dispatch(fetchWorkflows()));
    }
    if (state.global.recentRunsStatus !== "loading" && state.global.recentRunsStatus !== "succeeded") {
      preloadHome.push(dispatch(fetchRecentRuns()));
    }
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
    await Promise.all([...preloadHome, ...preloadLibrary]);
  },
});

listenerMiddleware.startListening({
  actionCreator: signedOut,
  effect: (_action, listenerApi) => {
    clearPreloads(listenerApi.dispatch as AppDispatch);
  },
});
