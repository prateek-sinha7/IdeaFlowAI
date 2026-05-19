/**
 * Shared rules for "chain to next pipeline" — used by the AgentProgressPanel
 * (after a fresh run completes) and the WorkflowHistory detail view (when
 * the user opens a past completed run).
 *
 * Keeping the predicates and option list in one place stops the three
 * surfaces from drifting apart — e.g. one panel allowing chaining from a
 * revision while another silently disables it.
 */

import type { WorkflowType } from "@/types/index";

export interface ChainOption {
  type: WorkflowType;
  label: string;
  description: string;
}

/**
 * The pipelines we surface as auto-chained next-step targets.
 * Includes app_builder so users can chain from any deliverable into a full app build.
 */
export const CHAIN_OPTIONS: readonly ChainOption[] = [
  { type: "ppt", label: "Presentation", description: "Turn results into slides" },
  { type: "user_stories", label: "User Stories", description: "Generate product backlog" },
  { type: "prototype", label: "Prototype", description: "Build interactive UI" },
  { type: "app_builder", label: "App Builder", description: "Build a full-stack application" },
];

/**
 * Workflow types that are eligible to chain (the "from" side). Includes
 * each base deliverable plus its `_revision` form, so a refine pass can
 * still hand off to a sibling pipeline.
 */
export const CHAINABLE_FROM_TYPES: ReadonlySet<WorkflowType> = new Set<WorkflowType>([
  "ppt", "ppt_revision",
  "user_stories", "user_stories_revision",
  "prototype", "prototype_revision",
  "od_prototype" as WorkflowType,
  "app_builder", "app_builder_revision",
]);

/**
 * Strip the `_revision` suffix so a refined run is treated as having
 * completed the same capability as its base form (and won't offer
 * chaining back to itself).
 */
export function baseWorkflowType(t: WorkflowType): string {
  return t.replace(/_revision$/, "");
}

/** True when this workflow type is allowed to chain. */
export function canChainFrom(workflowType: WorkflowType): boolean {
  return CHAINABLE_FROM_TYPES.has(workflowType);
}

/**
 * Filter `CHAIN_OPTIONS` to the targets the user hasn't already
 * completed. The current `workflowType` and every type in
 * `completedTypes` count as completed; comparison is on the base
 * (revision-stripped) form so `ppt_revision` blocks `ppt` and vice
 * versa.
 */
export function availableChainTargets(
  workflowType: WorkflowType,
  completedTypes: readonly WorkflowType[] = [],
): ChainOption[] {
  const completedBase = new Set<string>(
    [...completedTypes, workflowType].map(baseWorkflowType),
  );
  return CHAIN_OPTIONS.filter((p) => !completedBase.has(baseWorkflowType(p.type)));
}
