/**
 * Frontend-only chaining plumbing (Plan 34-01).
 *
 * The ACTUAL chaining data (which workflows may chain into which, and
 * whether a specific edge is beta) is now backend-owned — every workflow
 * authors its own `chained_from` consent list on its manifest, exposed via
 * GET /api/workflows and consumed through `useWorkflowChaining()`
 * (hooks/useWorkflowMetadata.ts). The formerly frontend-hardcoded
 * CHAIN_OPTIONS/CHAINABLE_FROM_TYPES/canChainFrom/availableChainTargets have
 * been retired — do not resurrect them; a source workflow's eligibility to
 * offer "chain into X" now comes from X's own manifest, not a static list
 * here.
 *
 * What legitimately remains frontend-only, and stays in this file:
 *   - baseWorkflowType: normalizes a WorkflowType to its base pipeline id
 *     (strips _revision, maps od_prototype -> prototype). Used well beyond
 *     chaining (e.g. RevisionFamilyView's grouping), so it stays generic here.
 *   - The sessionStorage keys the wizard pages read to pre-fill from a chain
 *     action.
 */

import type { WorkflowType } from "@/types/index";

export function baseWorkflowType(t: WorkflowType | string): string {
  const base = t.replace(/_revision$/, "");
  return base;
}

/** sessionStorage key for the brief pre-filled from a chain action. */
export const CHAIN_BRIEF_KEY = "chain.brief";
/** sessionStorage key for the pipeline type that initiated the chain. */
export const CHAIN_FROM_KEY = "chain.from";
/** sessionStorage key for the source WorkflowRun ID when chaining (Phase 3 / T055).
 *  Wizard pages store this so the backend can retrieve the original planning_context. */
export const CHAIN_SOURCE_RUN_ID_KEY = "chain.source_run_id";
