import { createAsyncThunk, createSelector, createSlice } from "@reduxjs/toolkit";
import { workflowsApi, type WorkflowSummary } from "@/store/api/workflows";
import { getToken, getWorkflows } from "@/lib/api";
import type { WorkflowRun } from "@/types/index";
import type { RootState } from "@/store";

const RECENT_RUNS_LIMIT = 6;

// App-wide operational state: workflow catalog and recent runs (separate from
// catalog metadata which lives in metadataSlice).
export interface GlobalState {
  workflows: WorkflowSummary[];
  workflowsStatus: "idle" | "loading" | "succeeded" | "failed";
  workflowsError: string | null;
  recentRuns: WorkflowRun[];
  recentRunsStatus: "idle" | "loading" | "succeeded" | "failed";
  recentRunsError: string | null;
}

const initialState: GlobalState = {
  workflows: [],
  workflowsStatus: "idle",
  workflowsError: null,
  recentRuns: [],
  recentRunsStatus: "idle",
  recentRunsError: null,
};

// GET /api/workflows — the manifest-driven workflow catalog (see FIX-051).
// Fetched once per sign-in via listenerMiddleware.ts, alongside fetchRecentRuns
// (both feed the home landing's first paint) — agents/skills follow after.
export const fetchWorkflows = createAsyncThunk("global/fetchWorkflows", async () => {
  return workflowsApi.list();
});

// GET /api/runs — the "Jump back in" seed for HomeLaunchGrid's first paint.
// dashboard/page.tsx keeps its own live-synced recentRuns (used for SSE run
// lookups too) — this is only the instant-paint snapshot, superseded once
// that live version arrives via the recentRuns prop.
export const fetchRecentRuns = createAsyncThunk("global/fetchRecentRuns", async () => {
  const token = getToken();
  if (!token) throw new Error("Not authenticated.");
  const { runs } = await getWorkflows(token, { limit: RECENT_RUNS_LIMIT });
  return runs;
});

const globalSlice = createSlice({
  name: "global",
  initialState,
  reducers: {
    globalCleared(state) {
      state.workflows = [];
      state.workflowsStatus = "idle";
      state.workflowsError = null;
      state.recentRuns = [];
      state.recentRunsStatus = "idle";
      state.recentRunsError = null;
    }
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchWorkflows.pending, (state) => {
        state.workflowsStatus = "loading";
        state.workflowsError = null;
      })
      .addCase(fetchWorkflows.fulfilled, (state, action) => {
        state.workflowsStatus = "succeeded";
        state.workflows = action.payload;
      })
      .addCase(fetchWorkflows.rejected, (state, action) => {
        state.workflowsStatus = "failed";
        state.workflowsError = action.error.message ?? "Failed to fetch workflows";
      })
      .addCase(fetchRecentRuns.pending, (state) => {
        state.recentRunsStatus = "loading";
        state.recentRunsError = null;
      })
      .addCase(fetchRecentRuns.fulfilled, (state, action) => {
        state.recentRunsStatus = "succeeded";
        state.recentRuns = action.payload;
      })
      .addCase(fetchRecentRuns.rejected, (state, action) => {
        state.recentRunsStatus = "failed";
        state.recentRunsError = action.error.message ?? "Failed to fetch recent runs";
      });
  },
});

export const { globalCleared } = globalSlice.actions;
export default globalSlice.reducer;

// ─────────────────────────────────────────────────────────────────────────
// Workflow label resolution — single source of truth, reducer-backed.
//
// Prefers the real, backend-driven workflow catalog (state.global.workflows,
// populated by fetchWorkflows/GET /api/workflows) so a workflow's display
// name always matches what the catalog actually calls it. Falls back to a
// static map for pipeline_type values that can appear on a persisted
// WorkflowRun but are not (or no longer) present in the live catalog —
// legacy/retired ids (od_ppt, od_prototype, ...) and revision suffixes,
// which the catalog never lists as their own launchable entry.
// ─────────────────────────────────────────────────────────────────────────

const FALLBACK_WORKFLOW_LABELS: Record<string, string> = {
  user_stories: "User Stories",
  user_stories_revision: "User Stories (Revised)",
  ppt: "Presentation",
  ppt_revision: "Presentation (Revised)",
  // KAN-130: od_ppt and od_prototype are legacy pipeline_type values that can
  // still appear on an older persisted WorkflowRun.type; the live catalog no
  // longer lists them, so they'd otherwise fall back to the raw alias string.
  prototype: "Prototype",
  prototype_revision: "Prototype (Revised)",
  app_builder: "App Builder",
  app_builder_revision: "App Builder (Revised)",
  mulesoft_to_springboot: "Mulesoft Migration",
  dotnet_to_azure: ".NET Migration",
  reverse_engineer: "Reverse Engineer",
  custom: "Custom Workflow",
};

/** state.global.workflows indexed by id, memoized so lookups don't rebuild
 * the map on every call. */
const selectWorkflowLabelIndex = createSelector(
  (state: RootState) => state.global.workflows,
  (workflows) => {
    const index: Record<string, string> = {};
    for (const w of workflows) {
      if (w.display_name) index[w.id] = w.display_name;
    }
    return index;
  },
);

/** Resolve a pipeline/workflow type to its display label: live catalog first,
 * then the static fallback map, then the raw type string. Use via
 * `useAppSelector(selectWorkflowLabel(type))` or the `useWorkflowLabels` hook
 * (hooks/useWorkflowMetadata.ts) — available anywhere, not tied to any one
 * component. */
export const selectWorkflowLabel = (type: string) => (state: RootState) => {
  const index = selectWorkflowLabelIndex(state);
  return index[type] ?? FALLBACK_WORKFLOW_LABELS[type] ?? type;
};

/** state.global.workflows indexed by id, for components that want the raw
 * lookup table (e.g. to resolve many labels in a loop without re-selecting
 * per item). Exported so `useWorkflowLabels` (hooks/useWorkflowMetadata.ts) can
 * build its `(type) => label` resolver from a single selector subscription. */
export { selectWorkflowLabelIndex, FALLBACK_WORKFLOW_LABELS };

/** state.global.workflows indexed by id -> short_name (falling back to the
 * catalog's plain `name`), memoized. Sibling to selectWorkflowLabelIndex —
 * same slice, different field: short_name is the concise/technical label
 * ("Dutch Target (Hello World)") fit for tight UI surfaces like run-history
 * type badges, vs display_name's action-phrase framing ("Pitch an idea")
 * meant for the catalog/launch surfaces. No static fallback map here (unlike
 * selectWorkflowLabel) — a type absent from the live catalog has no
 * shorter/nicer name to fall back to; callers handle the "unresolved" case
 * (index[type] undefined) themselves. */
const selectWorkflowShortNameIndex = createSelector(
  (state: RootState) => state.global.workflows,
  (workflows) => {
    const index: Record<string, string> = {};
    for (const w of workflows) {
      const short = w.short_name ?? w.name;
      if (short) index[w.id] = short;
    }
    return index;
  },
);

export { selectWorkflowShortNameIndex };

// ─────────────────────────────────────────────────────────────────────────
// Workflow chaining — backend-owned (Plan 34-01), reducer-derived.
//
// The backend authors ONLY `chained_from` per workflow (a target's own
// consent list: which source workflow ids may offer "chain into me"). This
// REPLACES the formerly frontend-hardcoded CHAIN_OPTIONS/CHAINABLE_FROM_TYPES
// in lib/workflowChaining.ts, which is being retired. The frontend never
// authors chaining data — it only derives the REVERSE view ("what can I
// chain INTO from workflow X") by inverting every workflow's chained_from
// once, memoized, so it's always 100% consistent with the backend by
// construction (no separate authored `chained_to` field to drift out of sync).
// ─────────────────────────────────────────────────────────────────────────

export interface ChainTarget {
  id: string;
  /** Workflow name (Pascal Case) — the SUBTITLE for the chain-suggestion UI.
   * Comes from the target workflow's name field, falling back to display_name, then id. */
  label: string;
  /** True when THIS specific source->target edge is beta ("Coming Soon"),
   * even if the target workflow itself is not is_beta. */
  beta: boolean;
  /** Action text for this chain relationship — the HEADING for the chain-suggestion UI
   * (e.g., "Ship the code"). Defined per source->target edge in the target's chained_from manifest. */
  text: string;
  /** Frontend routing path for workflows that redirect to a wizard page
   * (template + design-system selection) instead of firing directly.
   * Computed in Redux based on target id — pure UI routing, never backend-owned.
   * Undefined for workflows that fire directly. */
  wizard_path?: string;
  /** Workflow's display name (full sentence) for additional context if needed. */
  display_name?: string;
  /** Workflow's short name (concise label) for tight UI surfaces. */
  short_name?: string;
  /** Workflow's icon name (Lucide component) for the chain-suggestion icon. */
  icon?: string;
  /** Passthrough: all additional fields from the backend's chained_from entry */
  [key: string]: unknown;
}

/** state.global.workflows inverted: source workflow id -> the list of
 * ChainTarget it may offer as "chain into X" (derived from every OTHER
 * workflow's own authored `chained_from` consent entry naming this source). */
const selectChainIntoIndex = createSelector(
  (state: RootState) => state.global.workflows,
  (workflows) => {
    const WIZARD_ROUTES: Record<string, string> = {
      ppt: "/workflow/create?mode=ppt",
      ppt_v2: "/workflow/create?mode=ppt_v2",
      prototype: "/workflow/create?mode=prototype",
    };
    const index: Record<string, ChainTarget[]> = {};
    for (const target of workflows) {
      for (const entry of target.chained_from ?? []) {
        const label = target.name ?? target.display_name ?? target.id;
        const wizard_path = WIZARD_ROUTES[target.id];
        // Start with all entry data (id, beta, text, + any other backend fields)
        const chainTarget: ChainTarget = {
          ...entry,
          id: target.id,
          label,
          display_name: target.display_name ?? undefined,
          short_name: target.short_name ?? undefined,
        };
        if (target.icon) chainTarget.icon = target.icon;
        if (wizard_path) chainTarget.wizard_path = wizard_path;
        (index[entry.id] ??= []).push(chainTarget);
      }
    }
    return index;
  },
);

  /** Workflow id -> wizard path (for workflows that redirect to a wizard page
   * instead of firing directly). Pure frontend routing, never backend-authored. */
  const selectWorkflowWizardPath = (id: string): string | undefined => {
    const routes: Record<string, string> = {
      ppt: "/workflow/create?mode=ppt",
      ppt_v2: "/workflow/create?mode=ppt_v2",
      prototype: "/workflow/create?mode=prototype",
    };
    return routes[id];
  };

export { selectChainIntoIndex, selectWorkflowWizardPath };
