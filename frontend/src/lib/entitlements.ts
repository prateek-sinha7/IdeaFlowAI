export type Tier = "basic" | "pro" | "enterprise";
export type WorkflowType = string;

export const TIER_PIPELINES: Record<Tier, Set<string>> = {
  basic: new Set(["user_stories", "user_stories_revision", "ppt", "ppt_revision"]),
  pro: new Set([
    "user_stories", "user_stories_revision",
    "ppt", "ppt_revision",
    "prototype", "prototype_revision",
    "od_prototype",
    "app_builder", "app_builder_revision",
  ]),
  enterprise: new Set([
    "user_stories", "user_stories_revision",
    "ppt", "ppt_revision",
    "prototype", "prototype_revision",
    "od_prototype",
    "app_builder", "app_builder_revision",
    "custom", "migration", "mulesoft_to_springboot", "dotnet_to_azure",
  ]),
};

export const TIER_LABELS: Record<Tier, string> = {
  basic: "Basic",
  pro: "Pro",
  enterprise: "Enterprise",
};

export const UPGRADE_PATH: Record<Tier, Tier | null> = {
  basic: "pro",
  pro: "enterprise",
  enterprise: null,
};

export function canRunPipeline(tier: Tier, pipelineType: string): boolean {
  return TIER_PIPELINES[tier]?.has(pipelineType) ?? false;
}

export function getRequiredTier(pipelineType: string): Tier | null {
  for (const tier of ["basic", "pro", "enterprise"] as Tier[]) {
    if (TIER_PIPELINES[tier].has(pipelineType)) return tier;
  }
  return null;
}

export function getUpgradeTier(currentTier: Tier, pipelineType: string): Tier | null {
  if (canRunPipeline(currentTier, pipelineType)) return null;
  for (const tier of ["basic", "pro", "enterprise"] as Tier[]) {
    if (TIER_PIPELINES[tier].has(pipelineType)) return tier;
  }
  return null;
}
