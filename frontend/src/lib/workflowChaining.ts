/**
 * Shared rules for "chain to next pipeline" — used by the AgentProgressPanel
 * (after a fresh run completes) and the WorkflowHistory detail view (when
 * the user opens a past completed run).
 */

import type { WorkflowType } from "@/types/index";

export interface ChainOption {
  type: WorkflowType;
  label: string;
  description: string;
  /**
   * When true, clicking this chain option redirects to a wizard page
   * instead of firing the pipeline directly. The wizard handles
   * template/design-system selection before the pipeline starts.
   */
  requiresWizard?: boolean;
  /** The wizard page path to navigate to (only used when requiresWizard=true). */
  wizardPath?: string;
}

/**
 * The pipelines we surface as auto-chained next-step targets.
 *
 * prototype and ppt require wizard flows (template + DS selection) so they
 * redirect to their respective wizard pages instead of firing directly.
 * user_stories fires directly via the standard pipeline path.
 *
 * NOTE: app_builder is deliberately NOT a chain-TO target. It is a
 * heavyweight, full-stack pipeline launched explicitly from the Creation Hub,
 * not a lightweight "suggested next step". It remains chainable FROM (see
 * CHAINABLE_FROM_TYPES) so you can still chain OUT of an app_builder run.
 */
export const CHAIN_OPTIONS: readonly ChainOption[] = [
  {
    type: "ppt",
    label: "Presentation",
    description: "Turn results into slides",
    requiresWizard: true,
    wizardPath: "/workflow/create?mode=ppt",
  },
  {
    type: "user_stories",
    label: "User Stories",
    description: "Generate product backlog",
  },
  {
    type: "prototype",
    label: "Prototype",
    description: "Build interactive UI",
    requiresWizard: true,
    wizardPath: "/workflow/create?mode=prototype",
  },
];

export const CHAINABLE_FROM_TYPES: ReadonlySet<WorkflowType> = new Set<WorkflowType>([
  "ppt", "ppt_revision",
  "od_ppt" as WorkflowType,
  "od_ppt_revision" as WorkflowType,
  "user_stories", "user_stories_revision",
  "prototype", "prototype_revision",
  "od_prototype" as WorkflowType,
  "app_builder", "app_builder_revision",
]);

export function baseWorkflowType(t: WorkflowType): string {
  const base = t.replace(/_revision$/, "");
  if (base === "od_prototype") return "prototype";
  if (base === "od_ppt") return "ppt";
  return base;
}

export function canChainFrom(workflowType: WorkflowType): boolean {
  return CHAINABLE_FROM_TYPES.has(workflowType);
}

export function availableChainTargets(
  workflowType: WorkflowType,
  completedTypes: readonly WorkflowType[] = [],
): ChainOption[] {
  const completedBase = new Set<string>(
    [...completedTypes, workflowType].map(baseWorkflowType),
  );
  return CHAIN_OPTIONS.filter((p) => !completedBase.has(baseWorkflowType(p.type)));
}

/** sessionStorage key for the brief pre-filled from a chain action. */
export const CHAIN_BRIEF_KEY = "chain.brief";
/** sessionStorage key for the pipeline type that initiated the chain. */
export const CHAIN_FROM_KEY = "chain.from";
/** sessionStorage key for the source WorkflowRun ID when chaining (Phase 3 / T055).
 *  Wizard pages store this so the backend can retrieve the original planning_context. */
export const CHAIN_SOURCE_RUN_ID_KEY = "chain.source_run_id";
