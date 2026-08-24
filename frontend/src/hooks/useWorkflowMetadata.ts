import { useCallback } from "react";
import { useAppSelector } from "@/store/hooks";
import type { WorkflowSummary } from "@/lib/api";
import {
  selectWorkflowLabelIndex,
  FALLBACK_WORKFLOW_LABELS,
  selectWorkflowShortNameIndex,
  selectChainIntoIndex,
  type ChainTarget,
} from "@/store/slices/globalSlice";

/**
 * Catalog-derived metadata hooks (Plan 34-01) — both read the SAME live
 * `state.global.workflows` slice (the real, backend-driven catalog — see
 * globalSlice.ts's fetchWorkflows), just projecting different fields off it.
 * Consolidated into one file since they're the same kind of hook doing the
 * same job: subscribe once, return a stable resolver function.
 */

/**
 * Reducer-backed workflow label resolver, available anywhere without prop
 * drilling. Returns a stable `(type) => label` function: live catalog
 * display_name first, then a static fallback map for legacy/off-catalog
 * pipeline_type values (od_ppt, od_prototype, ...), then the raw type string.
 *
 * Call once per component (`const label = useWorkflowLabels();`) and use the
 * returned function at every render-time call site — a hook itself can't be
 * called inline inside `.map()`/JSX the way the old plain `getWorkflowLabel`
 * function was.
 */
export function useWorkflowLabels(): (type: string) => string {
  const index = useAppSelector(selectWorkflowLabelIndex);
  return useCallback(
    (type: string) => index[type] ?? FALLBACK_WORKFLOW_LABELS[type] ?? type,
    [index],
  );
}

/**
 * The whole catalog ROW for a pipeline type, not just one projected field.
 *
 * Sibling to the two resolvers above and reading the same live
 * `state.global.workflows` slice, for callers that need more than a label —
 * IdeaInputPage derives its page copy (tag/subtitle) from `display_name` +
 * `description` when a type has no hand-written TYPE_CONFIG entry, which is
 * what stops an unknown-but-launchable workflow from crashing the page.
 *
 * Returns `undefined` before the catalog has loaded, or for a type it does not
 * carry — callers must have their own generic fallback.
 */
export function useWorkflowCatalogEntry(): (type: string) => WorkflowSummary | undefined {
  const workflows = useAppSelector((state) => state.global.workflows);
  return useCallback((type: string) => workflows.find((w) => w.id === type), [workflows]);
}

/**
 * Reducer-backed workflow SHORT-name resolver — same catalog subscription as
 * useWorkflowLabels, projecting short_name (falling back to name) instead of
 * display_name. Returns `undefined` for a type the live catalog doesn't (yet)
 * carry — deliberately no raw-type-string fallback here, so callers can tell
 * "resolved" apart from "unresolved" and fall back to their own generic label.
 *
 * Call once per component (`const shortNameFor = useWorkflowShortNames();`)
 * and use the returned function at every render-time call site.
 */
export function useWorkflowShortNames(): (type: string) => string | undefined {
  const index = useAppSelector(selectWorkflowShortNameIndex);
  return useCallback((type: string) => index[type], [index]);
}

/**
 * Reducer-backed "what can I chain into" resolver — REPLACES the formerly
 * frontend-hardcoded CHAIN_OPTIONS/CHAINABLE_FROM_TYPES/canChainFrom/
 * availableChainTargets in lib/workflowChaining.ts. Chaining is backend-owned:
 * every workflow authors its OWN `chained_from` consent list (which SOURCE
 * workflow ids may offer "chain into me"); this hook inverts that once,
 * memoized, into "what can workflow X chain INTO" — always 100% consistent
 * with the backend by construction, never a separately-authored/driftable
 * frontend list.
 *
 * Call once per component (`const chainInto = useWorkflowChaining();`) and
 * use the returned function at every render-time call site.
 */
export function useWorkflowChaining(): (sourceType: string) => ChainTarget[] {
  const index = useAppSelector(selectChainIntoIndex);
  return useCallback((sourceType: string) => index[sourceType] ?? [], [index]);
}

export type { ChainTarget };
