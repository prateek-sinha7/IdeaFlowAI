export type Tier = "basic" | "pro" | "enterprise" | "hexaware";
export type WorkflowType = string;

/**
 * MIRROR of `backend/app/core/entitlements.py::TIER_PIPELINES`. The backend is
 * authoritative — it is what actually returns 403; this copy only decides what the
 * UI offers. Keep them identical, key for key.
 *
 * They had already drifted, in both directions, and each direction was a real bug:
 *   - `hello_html` was listed on every tier here and on none there. The UI gave it
 *     an icon, a label and a launch card; launching it 403'd. It has no manifest and
 *     no agents on the backend, so it was removed rather than added.
 *   - `custom_revision` and `od_prototype_revision` were entitled on the backend and
 *     missing here, so the UI hid Revise for runs that could in fact be revised.
 * `od_prototype` is gone entirely — the label was collapsed onto `prototype`.
 *
 * `backend/tests/unit/test_entitlement_parity.py` now fails if these two diverge,
 * so the next drift is caught at test time rather than by a user hitting a 403.
 */
export const TIER_PIPELINES: Record<Tier, Set<string>> = {
  basic: new Set([
    "user_stories", "user_stories_revision",
    "ppt", "ppt_revision",
  ]),
  hexaware: new Set([
    "user_stories", "user_stories_revision",
    "prototype", "prototype_revision",
    // revision-pipeline-agent-reuse spec: these share the main prototype
    // pipeline's agents. Entitled on the backend wherever `prototype` is —
    // the UI hid them, so the backend allowed a launch the catalog never offered.
    "prototype_large_revision", "prototype_feature_revision",
  ]),
  pro: new Set([
    "user_stories", "user_stories_revision",
    "ppt", "ppt_revision",
    "prototype", "prototype_revision",
    // revision-pipeline-agent-reuse spec: these share the main prototype
    // pipeline's agents. Entitled on the backend wherever `prototype` is —
    // the UI hid them, so the backend allowed a launch the catalog never offered.
    "prototype_large_revision", "prototype_feature_revision",
    "app_builder", "app_builder_revision",
  ]),
  enterprise: new Set([
    "user_stories", "user_stories_revision",
    "ppt", "ppt_revision",
    "prototype", "prototype_revision",
    // revision-pipeline-agent-reuse spec: these share the main prototype
    // pipeline's agents. Entitled on the backend wherever `prototype` is —
    // the UI hid them, so the backend allowed a launch the catalog never offered.
    "prototype_large_revision", "prototype_feature_revision",
    "app_builder", "app_builder_revision",
    "custom", "custom_revision",
    // `migration` is a UI meta-grouping, not a launchable pipeline: the card
    // forces the user to pick mulesoft_to_springboot or dotnet_to_azure before
    // Run. It has no manifest and is never dispatched, but CreationHub gates the
    // card on canRunPipeline(tier, "migration"), so the entry must exist here —
    // and therefore on the backend too, or the parity test fails.
    "migration",
    "mulesoft_to_springboot", "dotnet_to_azure",
    // spec-014 conditional-gates fixtures. Launchable, non-beta and entitled on
    // the backend, but absent here — so the catalog rendered the cards locked
    // behind an upgrade prompt that no tier could satisfy.
    "ex_A2_branch",
    "ex_A1_loop",
    "ex_A4_human_gate",
    "ex_A4_human_divert",
    "ex_A3_divert",
    "ex_A3_b_spanish",
    "ex_A3_c_dutch",
  ]),
};

export const TIER_LABELS: Record<Tier, string> = {
  basic: "Basic",
  pro: "Pro",
  enterprise: "Enterprise",
  hexaware: "Hexaware",
};

export const UPGRADE_PATH: Record<Tier, Tier | null> = {
  basic: "pro",
  pro: "enterprise",
  enterprise: null,
  hexaware: "enterprise",
};

export function canRunPipeline(tier: Tier, pipelineType: string): boolean {
  return TIER_PIPELINES[tier]?.has(pipelineType) ?? false;
}

export function getRequiredTier(pipelineType: string): Tier | null {
  for (const tier of ["basic", "pro", "enterprise", "hexaware"] as Tier[]) {
    if (TIER_PIPELINES[tier].has(pipelineType)) return tier;
  }
  return null;
}

export function getUpgradeTier(currentTier: Tier, pipelineType: string): Tier | null {
  if (canRunPipeline(currentTier, pipelineType)) return null;
  for (const tier of ["basic", "pro", "enterprise", "hexaware"] as Tier[]) {
    if (TIER_PIPELINES[tier].has(pipelineType)) return tier;
  }
  return null;
}
