/**
 * Mock REST backend for the Flowin E2E suite (mocked mode).
 *
 * Routes every `**​/api/**` request the dashboard makes on load and during a
 * run, so the UI renders deterministically with NO backend:
 *   - GET  /api/auth/me            → the current User (tier drives entitlement)
 *   - POST /api/auth/login         → { token, user }
 *   - POST /api/auth/logout        → 200
 *   - GET  /api/runs(?...)         → RawWorkflowRun[]   (history list)
 *   - GET  /api/runs/:id           → RawWorkflowRun     (reopen detail)
 *   - DELETE /api/runs/:id         → 204
 *   - GET  /api/capabilities       → { capabilities, model_catalog }
 *   - GET  /api/settings/preferences → { preferred_model, available_models }
 *   - GET  /api/chats              → []
 *   - anything else under /api     → 200 {}
 *
 * The controller is mutable mid-test (setUser / setRuns / setRunDetail) so a
 * spec can, e.g., set the history list, reopen a run, then assert the preview.
 */
import type { Page, Route } from "@playwright/test";
import { MODEL_CATALOG, CAPABILITIES } from "./constants";

export type Tier = "basic" | "pro" | "enterprise";

export interface MockUser {
  id: string;
  email: string;
  tier: Tier;
  is_admin?: boolean;
}

/** snake_case run shape the FE's normalizeWorkflowRun() expects (lib/api.ts). */
export interface RawRun {
  id: string;
  title: string;
  type: string;
  status: string; // completed | failed | cancelled | running | degraded | revising
  input: string;
  output: string | null;
  agent_outputs: string | null;
  agent_count: number;
  duration: number | null;
  error: string | null;
  token_usage: string | null;
  model_id: string | null;
  // Revision Families (B1) — optional so legacy rows still parse; the FE
  // normalizer (lib/api.ts) reads these to group a run into its family.
  parent_run_id?: string | null;
  root_run_id?: string;
  deliverable_mimetype?: string | null;
  deliverable_filename?: string | null;
  created_at: string;
  completed_at: string | null;
}

export function makeRun(partial: Partial<RawRun> & { id: string }): RawRun {
  return {
    title: "Untitled run",
    type: "user_stories",
    status: "completed",
    input: "test brief",
    output: null,
    agent_outputs: null,
    agent_count: 0,
    duration: 12.3,
    error: null,
    token_usage: null,
    model_id: null,
    created_at: "2026-06-13T12:00:00Z",
    completed_at: "2026-06-13T12:00:30Z",
    ...partial,
  };
}

/**
 * A launchable row shape the home deliverable grid (HomeLaunchGrid) expects from
 * GET /api/workflows. Without at least one row the grid's `rows.filter(...)`
 * throws "rows.filter is not a function" — the #1 known-red harness crash.
 */
export interface MockWorkflowRow {
  id: string;
  display_name: string;
  description: string;
  user_launchable: boolean;
  step_count: number;
}

/** The unnormalized RunFamily read model GET /api/runs/{id}/family returns. */
export interface MockFamilyMember {
  id: string;
  type: string;
  title: string;
  status: string;
  revision_index: number;
  parent_run_id: string | null;
  created_at: string;
  completed_at: string | null;
}
export interface MockRunFamily {
  root_id: string;
  members: MockFamilyMember[];
}

/**
 * The launchable catalog the home grid renders — a faithful mirror of the live
 * `GET /api/workflows` payload (the `user_launchable: true` workflow.yaml rows,
 * with their authored `display_name`/`description`/agent-count). Without at least
 * one row the grid's `rows.filter(...)` throws; the full set keeps the selection
 * specs (prototype/app_builder/migration/custom/ppt rows) exercising real ids.
 */
export const DEFAULT_WORKFLOWS: MockWorkflowRow[] = [
  { id: "user_stories", display_name: "Generate product requirements", description: "Epics, user stories, and Gherkin acceptance criteria — ready for Jira.", user_launchable: true, step_count: 6 },
  { id: "prototype", display_name: "Build an interactive prototype", description: "Navigable, high-fidelity HTML prototype from a brief or story set.", user_launchable: true, step_count: 5 },
  { id: "app_builder", display_name: "Build an end-to-end application", description: "Full-stack code, tests, and infrastructure from a single requirement.", user_launchable: true, step_count: 15 },
  { id: "ppt", display_name: "Pitch an idea", description: "Executive-grade deck with charts, data, and a clear narrative.", user_launchable: true, step_count: 3 },
  { id: "mulesoft_to_springboot", display_name: "Platform workflows", description: "Modernise a legacy estate — Mulesoft to AWS or .NET to Azure.", user_launchable: true, step_count: 13 },
  { id: "custom", display_name: "Compose a custom workflow", description: "Assemble specialist agents for tasks outside the standard pipelines.", user_launchable: true, step_count: 8 },
];

/** A well-formed single-member family so `[...runFamily.members]` never throws. */
export const defaultFamily = (id: string): MockRunFamily => ({
  root_id: id,
  members: [
    {
      id,
      type: "prototype",
      title: "Modern Website Prototype Design Reference",
      status: "completed",
      revision_index: 0,
      parent_run_id: null,
      created_at: "2026-07-04T09:00:00Z",
      completed_at: "2026-07-04T09:24:00Z",
    },
  ],
});

/**
 * The saved-workflow read model GET /api/user-workflows returns — a faithful
 * mirror of the FE's `UserWorkflowSummary` (lib/api.ts). Without this route the
 * mock catch-all returns `{}`, so `userWorkflows.filter(...)` throws at
 * SavedWorkflowsPage.tsx:170 (the Catalogue / My Workflows crash). The GET
 * handler always returns an ARRAY (empty by default), which alone fixes the
 * crash; `setUserWorkflows`/seeding populate it for the fidelity capture.
 */
export interface MockUserWorkflow {
  id: string;
  name: string;
  description?: string | null;
  base_pipeline_type: string;
  agent_ids: string[];
  model_overrides?: Record<string, string> | null;
  selections?: Record<string, Record<string, unknown>> | null;
  // Spec 012 (R-27/R-29) — the full `{"steps": [...]}` manifest, sent instead
  // of `selections` once a saved composition carries a per-node skill, custom
  // prompt, or sub-agent tree (mutually exclusive with `selections`, mirroring
  // the real `manifest_json` column split). Without echoing this back on GET,
  // a saved-workflow round-trip test can never see its own sub-agent tree.
  manifest?: { steps: unknown[]; capabilities?: Record<string, unknown> } | null;
  created_at?: string;
  updated_at?: string;
}

/** The date-scoped analytics rollup GET /api/analytics/summary returns
 *  (AnalyticsSummary in lib/api.ts). The minimal default renders the zero-state;
 *  SEEDED_ANALYTICS below fills every key for the populated fidelity capture. */
export interface MockAnalyticsSummary {
  kpis?: { total: number; completed: number; failed: number; success_rate: number };
  daily?: { date: string; total: number; completed: number; failed: number; input_tokens: number; output_tokens: number; total_tokens: number }[];
  pipelines?: { type: string; count: number; total_tokens: number; cost: number; avg_duration: number }[];
  models?: { model_id: string; count: number; total_tokens: number; cost: number }[];
  spend?: number;
  token_totals?: { input: number; output: number; cache_read: number; cache_write: number; total: number };
  type_avg_duration_sec: Record<string, number>;
}

/** The default analytics payload (zero-state) — byte-identical to the pre-seed
 *  handler shape so specs that don't opt into seeding are unregressed. */
export const DEFAULT_ANALYTICS: MockAnalyticsSummary = { type_avg_duration_sec: {} };

// ── Opt-in shell-capture scaffolding (NOT production data) ────────────────────
//
// The following seed sets exist ONLY so the Phase-40 shell fidelity capture can
// diff POPULATED surfaces (Catalogue / History / Analytics / Home-recents) that
// otherwise render empty in mocked mode. Production endpoints return only real
// owner-scoped data — this is capture scaffolding under SC-001/ND-D, mirroring
// the audit-seeding block below. Install it via `dashboard.seedShell()` /
// `setUserWorkflows` / `setRuns` / `setAnalytics`; the DEFAULTS stay empty so no
// existing spec regresses.

/** ≥2 representative saved workflows for the Catalogue capture. */
export const DEFAULT_USER_WORKFLOWS: MockUserWorkflow[] = [
  {
    id: "uw-sprint-deck",
    name: "Sprint kickoff deck",
    description: "Exec-ready deck summarising the sprint goal, scope and risks.",
    base_pipeline_type: "ppt",
    agent_ids: ["planner", "researcher", "deck-writer"],
    selections: { _wizard: { brief: "A 10-slide kickoff deck for the Q3 growth sprint — goals, scope, risks, timeline." } },
    created_at: "2026-06-20T10:00:00Z",
    updated_at: "2026-07-09T14:20:00Z",
  },
  {
    id: "uw-auth-migration",
    name: "Auth service migration",
    description: "Modernise the legacy Mulesoft auth flow onto Spring Boot.",
    base_pipeline_type: "mulesoft_to_springboot",
    agent_ids: ["analyzer", "planner", "code-generator", "test-writer"],
    selections: { _wizard: { brief: "Migrate the OAuth token-exchange flow from Mulesoft to Spring Boot on AWS." } },
    created_at: "2026-05-30T09:00:00Z",
    updated_at: "2026-07-02T11:05:00Z",
  },
  {
    id: "uw-onboarding-proto",
    name: "Onboarding prototype",
    description: "High-fidelity onboarding walkthrough prototype.",
    base_pipeline_type: "prototype",
    agent_ids: ["ux-writer", "prototype-builder"],
    selections: { _wizard: { brief: "A 4-step onboarding prototype: welcome, connect data, invite team, first run." } },
    created_at: "2026-07-01T08:30:00Z",
    updated_at: "2026-07-10T16:45:00Z",
  },
];

const tokenUsage = (input: number, output: number, cost: number, model = "eu.anthropic.claude-sonnet-4-5-20250929-v1:0") =>
  JSON.stringify({
    total_input_tokens: input,
    total_output_tokens: output,
    total_tokens: input + output,
    estimated_cost_usd: cost,
    model_id: model,
  });

// Dynamic timestamps so the TODAY / EARLIER / OLDER date buckets render
// correctly whenever the capture runs (dateBucketOf is relative to `new Date()`).
const _now = Date.now();
const _iso = (msAgo: number) => new Date(_now - msAgo).toISOString();
const HOUR = 3_600_000, DAY = 86_400_000;

/** A representative history set: a 2-version revision family (TODAY) + a failed
 *  run (EARLIER) + a cancelled run (OLDER), each with token_usage so the family
 *  grouping + status/token/version chips render. Also feeds the Home "Jump back
 *  in" recents (both bind GET /api/runs). */
export const SEEDED_HISTORY_RUNS: RawRun[] = [
  makeRun({
    id: "run-proto-v1", root_run_id: "run-proto-v1", parent_run_id: null,
    type: "prototype", status: "completed", title: "Growth dashboard prototype",
    input: "A KPI dashboard for a 5-person growth squad.",
    token_usage: tokenUsage(820_000, 240_000, 3.42), model_id: "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
    duration: 184.2, created_at: _iso(3 * HOUR), completed_at: _iso(3 * HOUR - 184_000),
  }),
  makeRun({
    id: "run-proto-v2", root_run_id: "run-proto-v1", parent_run_id: "run-proto-v1",
    type: "prototype_revision", status: "completed", title: "Growth dashboard prototype (revised)",
    input: "Add a cohort-retention chart and dark mode.",
    token_usage: tokenUsage(410_000, 150_000, 1.91), model_id: "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
    duration: 96.8, created_at: _iso(1 * HOUR), completed_at: _iso(1 * HOUR - 96_000),
  }),
  makeRun({
    id: "run-stories-fail", root_run_id: "run-stories-fail", parent_run_id: null,
    type: "user_stories", status: "failed", title: "Billing epics & stories",
    input: "Epics + Gherkin for the metered-billing rework.",
    error: "A downstream agent exceeded its budget and the run was halted.",
    token_usage: tokenUsage(190_000, 60_000, 0.88), model_id: "eu.anthropic.claude-haiku-4-5-20251001-v1:0",
    duration: 42.1, created_at: _iso(3 * DAY), completed_at: _iso(3 * DAY - 42_000),
  }),
  makeRun({
    id: "run-deck-cancel", root_run_id: "run-deck-cancel", parent_run_id: null,
    type: "ppt", status: "cancelled", title: "Investor update deck",
    input: "A 12-slide investor update for the Series B round.",
    token_usage: tokenUsage(60_000, 15_000, 0.28), model_id: "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
    duration: 18.0, created_at: _iso(30 * DAY), completed_at: null,
  }),
];

/** The revision family for the seeded prototype root (GET /api/runs/{id}/family)
 *  so the History detail's version timeline / chips render both versions. */
export const seededHistoryFamily = (id: string): MockRunFamily => {
  if (id === "run-proto-v1" || id === "run-proto-v2") {
    return {
      root_id: "run-proto-v1",
      members: [
        { id: "run-proto-v1", type: "prototype", title: "Growth dashboard prototype", status: "completed", revision_index: 0, parent_run_id: null, created_at: _iso(3 * HOUR), completed_at: _iso(3 * HOUR - 184_000) },
        { id: "run-proto-v2", type: "prototype_revision", title: "Growth dashboard prototype (revised)", status: "completed", revision_index: 1, parent_run_id: "run-proto-v1", created_at: _iso(1 * HOUR), completed_at: _iso(1 * HOUR - 96_000) },
      ],
    };
  }
  return defaultFamily(id);
};

/** A populated analytics summary (non-zero KPIs / daily bars / donut /
 *  by-pipeline / by-model / token totals) for the Analytics fidelity capture. */
export const SEEDED_ANALYTICS: MockAnalyticsSummary = {
  kpis: { total: 34, completed: 29, failed: 5, success_rate: 0.85 },
  token_totals: { input: 8_420_000, output: 2_610_000, cache_read: 1_200_000, cache_write: 240_000, total: 11_030_000 },
  spend: 41.87,
  daily: Array.from({ length: 14 }, (_, i) => {
    const input = 200_000 + ((i * 137) % 9) * 55_000;
    const output = 60_000 + ((i * 71) % 7) * 18_000;
    const total = 2 + ((i * 3) % 5);
    return {
      date: new Date(_now - (13 - i) * DAY).toISOString().slice(0, 10),
      total, completed: Math.max(total - (i % 2), 0), failed: i % 2,
      input_tokens: input, output_tokens: output, total_tokens: input + output,
    };
  }),
  pipelines: [
    { type: "prototype", count: 12, total_tokens: 5_100_000, cost: 19.4, avg_duration: 172.5 },
    { type: "user_stories", count: 9, total_tokens: 2_300_000, cost: 8.1, avg_duration: 54.2 },
    { type: "ppt", count: 8, total_tokens: 2_030_000, cost: 9.8, avg_duration: 61.0 },
    { type: "app_builder", count: 5, total_tokens: 1_600_000, cost: 4.6, avg_duration: 320.7 },
  ],
  models: [
    { model_id: "eu.anthropic.claude-sonnet-4-5-20250929-v1:0", count: 21, total_tokens: 8_100_000, cost: 33.2 },
    { model_id: "eu.anthropic.claude-haiku-4-5-20251001-v1:0", count: 13, total_tokens: 2_930_000, cost: 8.67 },
  ],
  type_avg_duration_sec: { prototype: 172.5, user_stories: 54.2, ppt: 61.0, app_builder: 320.7 },
};

// ── Opt-in Configure-capture scaffolding (Phase 41 / HARN-01 · D-CFG-STUBS) ────
//
// The three Configure data APIs (`/api/prototype/templates`,
// `/api/prototype/design-systems`, `/api/ppt/templates`) are UNSTUBBED in the
// mocked harness — the catch-all returns `{}`, so the Configure Templates +
// Design-System accordions/overlays render empty in mocked mode and there is no
// current analog to pair in the fidelity gallery (D-CFG-STUBS). These seed sets
// stub them with representative rows so a capture opts in to POPULATED overlays.
// NOT production data (labelled per SC-001/ND-D — production endpoints return
// only the real owner-scoped registry). Install via `dashboard.seedConfigure()`
// / the setters; the DEFAULT registries stay EMPTY so no existing spec regresses
// (mirrors the 40-01 `/api/user-workflows` idiom — the GET handler always
// returns an ARRAY, empty by default).

/** GET /api/prototype/templates row — mirrors PrototypeTemplate (lib/prototype-api.ts).
 *  `has_preview` MUST be true or TemplateGallery filters the row out (:59). */
export interface MockPrototypeTemplate {
  id: string;
  name: string;
  description: string;
  mode: string | null;
  platform: string | null; // DESKTOP | MOBILE — rendered as the card badge (:481)
  scenario: string | null;
  triggers: string[];
  craft_required: string[];
  example_prompt: string | null;
  has_preview: boolean;
}

/** GET /api/prototype/design-systems row — mirrors DesignSystemListItem.
 *  `category` groups the chips; the swatch band is fetched per-id (falls back to
 *  a neutral placeholder in mocked mode — no token/preview needed to render). */
export interface MockDesignSystem {
  id: string;
  name: string;
  category: string;
  description: string;
  has_preview: boolean;
}

/** GET /api/ppt/templates row — mirrors PPTTemplate (lib/ppt-api.ts).
 *  `has_preview` MUST be true or PPTTemplateGallery filters the row out (:58). */
export interface MockPPTTemplate {
  id: string;
  name: string;
  description: string;
  mode: string | null;
  platform: string | null;
  scenario: string | null;
  triggers: string[];
  craft_required: string[];
  example_prompt: string | null;
  has_preview: boolean;
  design_system: { requires?: boolean; [key: string]: unknown };
}

/** ≥3 representative prototype templates (a "start blank" + web DESKTOP/MOBILE),
 *  all `has_preview` so the TemplateGallery grid renders them. */
export const DEFAULT_PROTOTYPE_TEMPLATES: MockPrototypeTemplate[] = [
  {
    id: "blank-canvas", name: "No template — start blank",
    description: "A clean slate: the agents choose the visual DNA from your brief.",
    mode: "web", platform: "DESKTOP", scenario: "general",
    triggers: ["blank", "scratch"], craft_required: [], example_prompt: null, has_preview: true,
  },
  {
    id: "saas-dashboard", name: "SaaS analytics dashboard",
    description: "KPI cards, charts and a data table on a light shell — a product analytics look.",
    mode: "web", platform: "DESKTOP", scenario: "dashboard",
    triggers: ["dashboard", "analytics", "saas"], craft_required: ["charts"],
    example_prompt: "A KPI dashboard for a 5-person growth squad.", has_preview: true,
  },
  {
    id: "mobile-onboarding", name: "Mobile onboarding flow",
    description: "A four-step mobile onboarding walkthrough — welcome, connect, invite, first run.",
    mode: "web", platform: "MOBILE", scenario: "onboarding",
    triggers: ["mobile", "onboarding", "app"], craft_required: [],
    example_prompt: "A 4-step onboarding prototype.", has_preview: true,
  },
];

/** Representative design systems across ≥2 grouped categories so the grouped
 *  chip list renders category headers + rows (swatch dots via the per-id band). */
export const DEFAULT_DESIGN_SYSTEMS: MockDesignSystem[] = [
  { id: "analytics-hub", name: "Analytics Hub", category: "AI & LLM", description: "Cool neutrals with an electric-indigo accent; data-dense.", has_preview: true },
  { id: "ink-alabaster", name: "Ink & Alabaster", category: "AI & LLM", description: "High-contrast editorial monochrome on a warm paper ground.", has_preview: true },
  { id: "velocity-motors", name: "Velocity Motors", category: "Automotive", description: "Graphite + signal-orange; bold industrial type.", has_preview: true },
  { id: "ledger-pro", name: "Ledger Pro", category: "Finance", description: "Trustworthy deep-teal with restrained gold; tabular clarity.", has_preview: false },
];

/** ≥2 deck templates for the PPT gallery. */
export const DEFAULT_PPT_TEMPLATES: MockPPTTemplate[] = [
  {
    id: "exec-pitch", name: "Executive pitch",
    description: "A crisp investor-grade narrative deck — problem, solution, traction, ask.",
    mode: "deck", platform: null, scenario: "pitch",
    triggers: ["pitch", "investor", "exec"], craft_required: ["charts"],
    example_prompt: "A 12-slide Series B investor update.", has_preview: true,
    design_system: { requires: false },
  },
  {
    id: "quarterly-review", name: "Quarterly business review",
    description: "A data-forward QBR template — KPIs, wins, risks, next-quarter plan.",
    mode: "deck", platform: null, scenario: "review",
    triggers: ["qbr", "review", "quarterly"], craft_required: ["charts", "tables"],
    example_prompt: "A Q3 business review deck for the leadership team.", has_preview: true,
    design_system: { requires: true },
  },
];

export interface MockApiOptions {
  user?: Partial<MockUser>;
  runs?: RawRun[];
  capabilities?: { capabilities: unknown[]; model_catalog: unknown[] };
  /** Resolve a single run by id (reopen). Falls back to the runs list. */
  runDetail?: (id: string) => RawRun | undefined;
  /** Launchable rows for the home grid (GET /api/workflows). */
  workflows?: MockWorkflowRow[];
  /** Saved workflows for the Catalogue (GET /api/user-workflows). Default []. */
  userWorkflows?: MockUserWorkflow[];
  /** Analytics rollup (GET /api/analytics/summary). Default zero-state. */
  analytics?: MockAnalyticsSummary;
  /** Revision family for GET /api/runs/{id}/family. */
  family?: (id: string) => MockRunFamily;
  /** Prototype templates (GET /api/prototype/templates). Default []. */
  prototypeTemplates?: MockPrototypeTemplate[];
  /** Design systems (GET /api/prototype/design-systems). Default []. */
  designSystems?: MockDesignSystem[];
  /** PPT/deck templates (GET /api/ppt/templates). Default []. */
  pptTemplates?: MockPPTTemplate[];
}

/** Agent library served by GET /api/agents/library.
 *
 *  Mirrors the real endpoint's shape. The last entry is the reusable BLANK
 *  TEMPLATE (`custom-agent`): the composer instantiates it into a fresh
 *  `custom-agent:<instance_id>` node on every add, so it must remain addable an
 *  unlimited number of times and must never be filtered out as "already added".
 */
const DEFAULT_AGENT_LIBRARY = {
  agents: [
    { id: "market-research-agent", name: "Market Research Agent", role: "Competitive & Industry Analysis", description: "Analyzes your market and competitors.", pipeline_type: "custom", order: 1, icon: "\u{1F4C8}", estimated_duration: 6, has_skill: true, gate: null },
    { id: "swot-analyst", name: "Strategy Analysis Agent", role: "SWOT & Strategic Positioning", description: "Identifies strengths and weaknesses.", pipeline_type: "custom", order: 2, icon: "\u{1F3AF}", estimated_duration: 5, has_skill: true, gate: null },
    { id: "roadmap-planner", name: "Roadmap Planning Agent", role: "Phased Delivery Strategy", description: "Builds a phased product roadmap.", pipeline_type: "custom", order: 3, icon: "\u{1F5D3}", estimated_duration: 6, has_skill: true, gate: null },
    { id: "domain-analyst", name: "Domain Analyst", role: "Requirements Analysis", description: "Analyzes the problem domain.", pipeline_type: "user_stories", order: 1, icon: "\u{1F9E0}", estimated_duration: 5, has_skill: true, gate: null },
    { id: "custom-agent", name: "Custom Agent", role: "Blank agent", description: "A blank agent you define with your own prompt.", pipeline_type: "custom", order: 99, icon: "\u{1F9E9}", estimated_duration: 60, has_skill: false, gate: null },
  ],
  total_count: 5,
  pipelines: {},
};

/** GET /api/skills/library. `compatible_agents: []` means "compatible with
 *  everything" (R-33), so these show for every agent in the picker. */
const DEFAULT_SKILLS_LIBRARY = {
  skills: [
    { id: "emoji", name: "emoji", display_name: "Emoji", description: "Adds an emoji heading.", category: "workflow", content: "# Emoji", isBeta: false, compatible_agents: [], tags: [] },
    { id: "joke", name: "joke", display_name: "Joke", description: "Adds a one-line joke.", category: "workflow", content: "# Joke", isBeta: false, compatible_agents: [], tags: [] },
    { id: "html-page", name: "html-page", display_name: "HTML Page", description: "Emits a single HTML page.", category: "engineering", content: "# HTML", isBeta: false, compatible_agents: [], tags: [] },
  ],
  total_count: 3,
  categories: [
    { id: "all", label: "All" },
    { id: "workflow", label: "Workflow" },
    { id: "engineering", label: "Engineering" },
  ],
};

/** GET /api/hooks/library. */
const DEFAULT_HOOKS_LIBRARY = {
  hooks: [
    { id: "lint-on-write", name: "lint-on-write", display_name: "Lint on write", description: "Lints each written file.", event: "post_tool_use", trigger: "write_file", compatible_agents: [], tags: [] },
  ],
  total_count: 1,
  events: [
    { id: "all", label: "All" },
    { id: "post_tool_use", label: "Post tool use" },
  ],
};

export class MockApi {
  user: MockUser;
  runs: RawRun[];
  capabilities: { capabilities: unknown[]; model_catalog: unknown[] };
  /** GET /api/agents/library payload (includes the reusable custom-agent template). */
  agentLibrary: { agents: unknown[]; total_count: number; pipelines: Record<string, number> };
  /** GET /api/skills/library — drives the per-agent AgentSkillsPicker. */
  skillsLibrary: { skills: unknown[]; total_count: number; categories: unknown[] };
  /** GET /api/hooks/library — drives the run-level HooksTab. */
  hooksLibrary: { hooks: unknown[]; total_count: number; events: unknown[] };
  workflows: MockWorkflowRow[];
  /** Saved workflows the Catalogue reads (GET /api/user-workflows). */
  userWorkflows: MockUserWorkflow[];
  /** Analytics rollup (GET /api/analytics/summary). */
  analytics: MockAnalyticsSummary;
  /** Configure data registries (Phase 41 / HARN-01) — GET /api/prototype/templates
   *  · /api/prototype/design-systems · /api/ppt/templates. Default EMPTY (opt-in
   *  seeding via seedConfigure()/setters); production returns the real registry. */
  prototypeTemplates: MockPrototypeTemplate[];
  designSystems: MockDesignSystem[];
  pptTemplates: MockPPTTemplate[];
  /** Which seeded audit set the 3 audit reads return (settled=clean, failed=blocked). */
  auditVariant: "settled" | "failed" = "settled";
  private family: (id: string) => MockRunFamily;
  private runDetail?: (id: string) => RawRun | undefined;
  /** Recorded request log for assertions (method + path). */
  readonly requests: { method: string; url: string; body?: unknown }[] = [];

  constructor(opts: MockApiOptions) {
    this.user = {
      id: "u-test",
      email: "qa@flowinqa.com",
      tier: "enterprise",
      is_admin: false,
      ...opts.user,
    };
    this.runs = opts.runs ?? [];
    this.capabilities = opts.capabilities ?? {
      capabilities: CAPABILITIES as unknown as unknown[],
      model_catalog: MODEL_CATALOG as unknown as unknown[],
    };
    this.agentLibrary = DEFAULT_AGENT_LIBRARY;
    this.skillsLibrary = DEFAULT_SKILLS_LIBRARY;
    this.hooksLibrary = DEFAULT_HOOKS_LIBRARY;
    this.workflows = opts.workflows ?? DEFAULT_WORKFLOWS;
    // Default EMPTY (not seeded) so existing specs are byte-unchanged; the
    // GET handler still returns an array, which fixes the Catalogue crash.
    this.userWorkflows = opts.userWorkflows ?? [];
    this.analytics = opts.analytics ?? DEFAULT_ANALYTICS;
    // Default EMPTY (opt-in) so existing specs are byte-unchanged; the GET
    // handlers still return an ARRAY (never the {} catch-all), fixing the shape.
    this.prototypeTemplates = opts.prototypeTemplates ?? [];
    this.designSystems = opts.designSystems ?? [];
    this.pptTemplates = opts.pptTemplates ?? [];
    this.family = opts.family ?? defaultFamily;
    this.runDetail = opts.runDetail;
  }

  setUser(patch: Partial<MockUser>) {
    this.user = { ...this.user, ...patch };
  }
  setRuns(runs: RawRun[]) {
    this.runs = runs;
  }
  setWorkflows(rows: MockWorkflowRow[]) {
    this.workflows = rows;
  }
  setUserWorkflows(rows: MockUserWorkflow[]) {
    this.userWorkflows = rows;
  }
  setAnalytics(summary: MockAnalyticsSummary) {
    this.analytics = summary;
  }
  setPrototypeTemplates(rows: MockPrototypeTemplate[]) {
    this.prototypeTemplates = rows;
  }
  setDesignSystems(rows: MockDesignSystem[]) {
    this.designSystems = rows;
  }
  setPPTTemplates(rows: MockPPTTemplate[]) {
    this.pptTemplates = rows;
  }
  setFamily(fn: (id: string) => MockRunFamily) {
    this.family = fn;
  }
  setAuditVariant(v: "settled" | "failed") {
    this.auditVariant = v;
  }
  setRunDetail(fn: (id: string) => RawRun | undefined) {
    this.runDetail = fn;
  }

  private resolveDetail(id: string): RawRun | undefined {
    return this.runDetail?.(id) ?? this.runs.find((r) => r.id === id);
  }

  async handle(route: Route) {
    const req = route.request();
    const method = req.method();
    const url = new URL(req.url());
    const path = url.pathname;
    let body: unknown;
    try {
      body = req.postDataJSON?.();
    } catch {
      /* non-json */
    }
    this.requests.push({ method, url: path, body });

    const json = (data: unknown, status = 200) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(data) });

    // --- auth ---
    if (path.endsWith("/api/auth/me")) return json(this.user);
    if (path.endsWith("/api/auth/login") && method === "POST") {
      const b = (body as { email?: string }) ?? {};
      return json({ token: "e2e.login.jwt", user: { ...this.user, email: b.email ?? this.user.email } });
    }
    if (path.endsWith("/api/auth/logout")) return json({ ok: true });
    if (path.endsWith("/api/auth/change-password")) return json({ message: "ok" });

    // --- agent library (GET /api/agents/library) ---
    // Without this the store stays empty and the Agent Library renders nothing,
    // so no composer test can add an agent. Includes the reusable blank
    // `custom-agent` TEMPLATE, which must stay addable N times.
    if (path.endsWith("/api/agents/library")) return json(this.agentLibrary);
    if (path.endsWith("/api/skills/library")) return json(this.skillsLibrary);
    if (path.endsWith("/api/hooks/library")) return json(this.hooksLibrary);

    // --- capabilities (model picker) ---
    if (path.endsWith("/api/capabilities")) return json(this.capabilities);

    // --- settings ---
    if (path.endsWith("/api/settings/preferences")) {
      return json({
        preferred_model: null,
        available_models: (this.capabilities.model_catalog as { id: string; label: string; description: string; tier: string }[])
          .map((m) => ({ id: m.id, name: m.label, description: m.description, tier: m.tier })),
      });
    }

    // --- workflows catalog (home launch grid) — fixes `rows.filter` crash ---
    if (path.endsWith("/api/workflows")) return json(this.workflows);

    // --- Configure data registries (Phase 41 / HARN-01 · D-CFG-STUBS) — the
    //     Templates / Design-System / PPT accordions + overlays bind these. Stubbed
    //     so the mocked Configure surface renders POPULATED overlays for the
    //     fidelity gate; production returns the real owner-scoped registry
    //     (SC-001/ND-D). Always an ARRAY (never the {} catch-all); EMPTY by default
    //     until a capture opts in via seedConfigure()/the setters. The detail +
    //     /preview subpaths (…/templates/{id}, …/design-systems/{id}[/preview]) do
    //     NOT match these endsWith checks and fall through to the catch-all. ---
    if (path.endsWith("/api/prototype/templates")) return json(this.prototypeTemplates);
    if (path.endsWith("/api/prototype/design-systems")) return json(this.designSystems);
    if (path.endsWith("/api/ppt/templates")) return json(this.pptTemplates);

    // --- saved workflows (Catalogue / My Workflows) — fixes the
    //     `userWorkflows.filter is not a function` crash (SavedWorkflowsPage:170).
    //     GET always returns an ARRAY; create/rename/delete are stubbed so the
    //     kebab actions don't fall through to the empty catch-all. ---
    const uwIdMatch = path.match(/\/api\/user-workflows\/([^/]+)$/);
    if (uwIdMatch) {
      const id = uwIdMatch[1];
      if (method === "DELETE") {
        this.userWorkflows = this.userWorkflows.filter((w) => w.id !== id);
        return route.fulfill({ status: 204, body: "" });
      }
      // PATCH (rename/edit)
      const b = (body as Partial<MockUserWorkflow>) ?? {};
      const existing = this.userWorkflows.find((w) => w.id === id);
      const updated: MockUserWorkflow = {
        ...(existing ?? { id, name: "Workflow", base_pipeline_type: "custom", agent_ids: [] }),
        ...b, id, updated_at: new Date().toISOString(),
      };
      this.userWorkflows = this.userWorkflows.map((w) => (w.id === id ? updated : w));
      return json(updated);
    }
    if (path.endsWith("/api/user-workflows")) {
      if (method === "POST") {
        const b = (body as Partial<MockUserWorkflow>) ?? {};
        const created: MockUserWorkflow = {
          id: `uw-${this.userWorkflows.length + 1}-${Date.now()}`,
          name: b.name ?? "New workflow",
          description: b.description ?? null,
          base_pipeline_type: b.base_pipeline_type ?? "custom",
          agent_ids: b.agent_ids ?? [],
          model_overrides: b.model_overrides ?? null,
          selections: b.selections ?? null,
          manifest: b.manifest ?? null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
        this.userWorkflows = [created, ...this.userWorkflows];
        return json(created);
      }
      return json(this.userWorkflows);
    }

    // --- analytics summary (home grid duration chips + Analytics page) ---
    if (path.endsWith("/api/analytics/summary")) return json(this.analytics);

    // --- revision family (right panel Version menu) — fixes `[...members]` crash ---
    const familyMatch = path.match(/\/api\/runs\/([^/]+)\/family$/);
    if (familyMatch) return json(this.family(familyMatch[1]));

    // --- audit reads (Audit tab) — categorized gate / validation / exec rows ---
    //
    // Harness seeding (NOT fabricated production data): the audit tab derives its
    // fuller category taxonomy (gate / validation / secret-scan / exec / perf /
    // behavioral) from signals in the real row. To EXERCISE every category + the
    // failed variant in the fidelity capture, we seed representative rows here.
    // `auditVariant` swaps the settled (clean, passed-all-gates) set for the
    // failed (blocked/denied/secrets-hit) set. Real runs return only what the
    // backend recorded — this is capture scaffolding, not a production shape.
    const gateMatch = path.match(/\/api\/runs\/([^/]+)\/gate-events$/);
    if (gateMatch) {
      const id = gateMatch[1];
      const gate_events = this.auditVariant === "failed"
        ? [
            { id: "g1", gate: "Specification approved", step: "prototype-specify", outcome: "approved", detail: { note: "Paused for review · approved by you" }, created_at: "2026-07-04T09:03:00Z" },
            { id: "g2", gate: "Behavioral guideline check", step: "prototype-plan", outcome: "pass", detail: { note: "Agents followed the workspace operating rules" }, created_at: "2026-07-04T09:06:00Z" },
            { id: "g3", gate: "Secret scan — credentials detected", step: "prototype-build", outcome: "block", detail: { note: "A step tried to write credentials to .env — blocked" }, created_at: "2026-07-04T09:08:00Z" },
            { id: "g4", gate: "Security gate", step: "prototype-build", outcome: "block", detail: { note: "Run halted at the security gate" }, created_at: "2026-07-04T09:08:30Z" },
          ]
        : [
            { id: "g1", gate: "Specification approved", step: "prototype-specify", outcome: "approved", detail: { note: "Paused for review · approved by you" }, created_at: "2026-07-04T09:03:00Z" },
            { id: "g2", gate: "Build approved", step: "prototype-build", outcome: "approved", detail: { note: "Build approved by you" }, created_at: "2026-07-04T09:05:00Z" },
            { id: "g3", gate: "Behavioral guideline check", step: "prototype-plan", outcome: "pass", detail: { note: "Agents followed the workspace operating rules for this run" }, created_at: "2026-07-04T09:06:00Z" },
            { id: "g4", gate: "Secret scan — no credentials written", step: "prototype-build", outcome: "pass", detail: { note: "No secrets written, logged, or exposed" }, created_at: "2026-07-04T09:07:00Z" },
          ];
      return json({ workflow_id: id, gate_events });
    }
    const validationMatch = path.match(/\/api\/runs\/([^/]+)\/validation-results$/);
    if (validationMatch) {
      const id = validationMatch[1];
      const validation_results = this.auditVariant === "failed"
        ? [
            { id: "v1", validator: "static_check", step: "prototype-specify", severity: "pass", issues: [], created_at: "2026-07-04T09:20:00Z" },
            { id: "v2", validator: "security_review", step: "prototype-build", severity: "CRITICAL", issues: ["Credential write attempt outside the sandbox"], created_at: "2026-07-04T09:21:00Z" },
          ]
        : [
            { id: "v1", validator: "static_check", step: "prototype-build", severity: "pass", issues: [], created_at: "2026-07-04T09:20:00Z" },
            { id: "v2", validator: "render_check", step: "prototype-build", severity: "pass", issues: [], created_at: "2026-07-04T09:21:00Z" },
            { id: "v3", validator: "a11y_check", step: "prototype-build", severity: "LOW", issues: ["2 images missing alt text"], created_at: "2026-07-04T09:22:00Z" },
          ];
      return json({ workflow_id: id, validation_results });
    }
    const execMatch = path.match(/\/api\/runs\/([^/]+)\/exec-runs$/);
    if (execMatch) {
      const id = execMatch[1];
      const exec_runs = this.auditVariant === "failed"
        ? [
            { id: "e1", step: "prototype-build", argv_json: ["python", "seed.py", "--write-env"], outcome: "denied", exit_code: null, duration_ms: 40, policy_snapshot_json: {}, output_digest: "sha256:9f1c…", created_at: "2026-07-04T09:23:00Z" },
          ]
        : [
            { id: "e1", step: "prototype-build", argv_json: ["npm", "run", "build"], outcome: "allowed", exit_code: 0, duration_ms: 4120, policy_snapshot_json: {}, output_digest: "sha256:a1b2…", created_at: "2026-07-04T09:23:00Z" },
            { id: "e2", step: "prototype-build", argv_json: ["otel-span", "render-benchmark"], outcome: "allowed", exit_code: 0, duration_ms: 210, policy_snapshot_json: {}, output_digest: "sha256:c3d4…", created_at: "2026-07-04T09:24:00Z" },
          ];
      return json({ workflow_id: id, exec_runs });
    }

    // --- runs (history) ---
    const runDetailMatch = path.match(/\/api\/runs\/([^/]+)(\/chain-context)?$/);
    if (runDetailMatch) {
      const id = runDetailMatch[1];
      if (runDetailMatch[2] === "/chain-context") {
        return json({ workflow_id: id, pipeline_type: "user_stories", title: "", brief: "", structured_summary: "", agent_summaries: [], context_block: "" });
      }
      if (method === "DELETE") return route.fulfill({ status: 204, body: "" });
      const detail = this.resolveDetail(id);
      if (!detail) return json({ detail: "not found" }, 404);
      return json(detail);
    }
    if (path.endsWith("/api/runs")) return json(this.runs);

    // --- chats (secondary) ---
    if (path.match(/\/api\/chats(\/.*)?$/)) {
      if (method === "POST") return json({ id: "chat-1", title: "New chat", last_activity: "2026-06-13T12:00:00Z", created_at: "2026-06-13T12:00:00Z" });
      return json([]);
    }

    // --- anything else under /api → empty 200 ---
    return json({});
  }
}

/** Install the mock REST backend on a page. Call before navigation. */
export async function installMockApi(page: Page, opts: MockApiOptions = {}): Promise<MockApi> {
  const mock = new MockApi(opts);
  await page.route("**/api/**", (route) => mock.handle(route));
  return mock;
}
