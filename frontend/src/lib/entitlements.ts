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
    // spec 017 — same deck as ppt, plus a real .pptx. Entitled wherever ppt is.
    "ppt", "ppt_v2", "ppt_revision",
  ]),
  hexaware: new Set([
    "user_stories", "user_stories_revision",
    "prototype", "prototype_revision",
    // file-manifest copy of the DB-composed Prototype v2; entitled on the backend
    // wherever `prototype` is (backend/app/core/entitlements.py).
    "prototype_v2", "prototype_v2_revision", "prototype_v2_feature_revision",
    // revision-pipeline-agent-reuse spec: these share the main prototype
    // pipeline's agents. Entitled on the backend wherever `prototype` is —
    // the UI hid them, so the backend allowed a launch the catalog never offered.
    "prototype_large_revision", "prototype_feature_revision",
    // file-manifest workflow: full-application user stories from a prototype (spec 021)
    "backlog", "backlog_revision",
  ]),
  pro: new Set([
    "user_stories", "user_stories_revision",
    // spec 017 — same deck as ppt, plus a real .pptx. Entitled wherever ppt is.
    "ppt", "ppt_v2", "ppt_revision",
    "prototype", "prototype_revision",
    // file-manifest copy of the DB-composed Prototype v2; entitled on the backend
    // wherever `prototype` is (backend/app/core/entitlements.py).
    "prototype_v2", "prototype_v2_revision", "prototype_v2_feature_revision",
    // revision-pipeline-agent-reuse spec: these share the main prototype
    // pipeline's agents. Entitled on the backend wherever `prototype` is —
    // the UI hid them, so the backend allowed a launch the catalog never offered.
    "prototype_large_revision", "prototype_feature_revision",
    "app_builder", "app_builder_revision",
    // file-manifest workflow: full-application user stories from a prototype (spec 021)
    "backlog", "backlog_revision",
  ]),
  enterprise: new Set([
    "user_stories", "user_stories_revision",
    // spec 017 — same deck as ppt, plus a real .pptx. Entitled wherever ppt is.
    "ppt", "ppt_v2", "ppt_revision",
    "prototype", "prototype_revision",
    // file-manifest copy of the DB-composed Prototype v2; entitled on the backend
    // wherever `prototype` is (backend/app/core/entitlements.py).
    "prototype_v2", "prototype_v2_revision", "prototype_v2_feature_revision",
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
    // spec 018: temporary smoke-test pipeline for the playwright tool set.
    // Entitled on the backend but missed here on first pass — same drift class
    // as the ex_A* fixtures above.
    "ex_playwright_smoke_test",
    // file-manifest workflow: full-application user stories from a prototype (spec 021)
    "backlog", "backlog_revision",
    // reference fan-out fixture — kept in parity with the backend map.
    "sample_subagents_parallel",
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

/**
 * Engine demonstrations, not product capability. The backend's conditional-gate
 * fixtures use an `ex_` / `sample_` / `sc001` id prefix and stay
 * `user_launchable` because they genuinely run — but on a flat grid "Spanish
 * Greeter" read like a peer of "Build an end-to-end application". Classifying
 * on the prefix is presentation only: no manifest changes, nothing stops being
 * launchable, and a new fixture following the convention is sorted automatically.
 * A beta row stays under Coming Soon even when it matches.
 */
const EXAMPLE_ID_PREFIX = /^(ex_|sample_|sc001)/i;
export const isExampleWorkflow = (id: string): boolean => EXAMPLE_ID_PREFIX.test(id);

/** The fields of a live catalog row (`GET /api/workflows`) the split below reads. */
type CatalogRow = { id: string; user_launchable: boolean; is_beta?: boolean };

/**
 * The home catalog's split of the live workflow list: launchable rows as product
 * workflows, Engine examples, or Coming Soon (beta wins over the example prefix).
 */
export function splitCatalog<W extends CatalogRow>(workflows: readonly W[]) {
  const launchable = workflows.filter((w) => w.user_launchable);
  return {
    productRows: launchable.filter((w) => !w.is_beta && !isExampleWorkflow(w.id)),
    exampleRows: launchable.filter((w) => !w.is_beta && isExampleWorkflow(w.id)),
    betaRows: launchable.filter((w) => w.is_beta),
  };
}

/**
 * What a tier's plan includes, read off that same split: the product and example
 * rows the catalog enables for `tier`. The Usage & Limits deliverable-access grid
 * lists them and the plan modal counts them, so neither can disagree with the
 * catalog (ISS-1195).
 */
export function catalogAccess<W extends CatalogRow>(workflows: readonly W[], tier: Tier) {
  const { productRows, exampleRows } = splitCatalog(workflows);
  const runnable = (w: W) => canRunPipeline(tier, w.id);
  return { productRows: productRows.filter(runnable), exampleRows: exampleRows.filter(runnable) };
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
