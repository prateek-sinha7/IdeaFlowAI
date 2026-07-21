/**
 * TS-Z — Workflow Catalog (data-driven browse + launch). Mocked spec, analog
 * `ts-i.agent-panels.spec.ts`. Proves the TWO-GATE filter and that a catalog
 * launch reaches the EXISTING run flow (IdeaInputPage).
 *
 * MOCK PRECEDENCE (do NOT edit fixtures/): the fixtures' `installMockApi`
 * registers a single catch-all `page.route("**\/api\/**", …)` during fixture
 * setup, and Playwright matches `page.route` handlers in REVERSE registration
 * order. So a per-spec `page.route("**\/api\/workflows*", …)` registered AFTER
 * `dashboard.goto()` is the LATER registration and therefore WINS — it
 * fulfills the workflows payload and the catch-all (which has no
 * `/api/workflows` branch → falls through to an empty `{}`) never sees it.
 */
import { test, expect } from "../fixtures/test";

// A mixed WorkflowSummary[] list exercising both gates:
//   - user_stories         : launchable, entitled at basic+              → SHOWN
//   - app_builder           : launchable, needs pro (gated at basic)      → SHOWN-LOCKED
//   - user_stories_revision : NOT launchable (gate 1)                     → HIDDEN
//   - od_ppt                : NOT launchable (gate 1)                     → HIDDEN
const WORKFLOWS_PAYLOAD = [
  {
    id: "user_stories",
    name: "raw-user-stories",
    description: "Epics, user stories, and Gherkin acceptance criteria.",
    step_count: 3,
    steps: [],
    user_launchable: true,
    display_name: "Generate product requirements",
    icon: null,
    launch_surface: null,
  },
  {
    id: "app_builder",
    name: "raw-app-builder",
    description: "Full-stack code, tests, and infrastructure.",
    step_count: 5,
    steps: [],
    user_launchable: true,
    display_name: "Build an end-to-end application",
    icon: null,
    launch_surface: null,
  },
  {
    id: "user_stories_revision",
    name: "raw-revision",
    description: "Revision loop.",
    step_count: 2,
    steps: [],
    user_launchable: false,
    display_name: null,
    icon: null,
    launch_surface: null,
  },
  {
    id: "od_ppt",
    name: "raw-od-ppt",
    description: "On-demand deck.",
    step_count: 2,
    steps: [],
    user_launchable: false,
    display_name: null,
    icon: null,
    launch_surface: null,
  },
];

/** Register the per-spec /api/workflows mock AFTER goto so it wins by
 *  reverse-registration precedence over the fixtures' catch-all. */
async function mockWorkflows(page: import("@playwright/test").Page) {
  await page.route("**/api/workflows*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(WORKFLOWS_PAYLOAD),
    }),
  );
}

/** Surface the data-driven catalog. Phase-39 RETIRED the separate "Catalog"
 *  header nav — the catalog IS the home view now (HomeLaunchGrid, sourced from
 *  GET /api/workflows and gated identically). The per-spec `/api/workflows` mock
 *  is registered AFTER `dashboard.goto()`, so reload the page to force
 *  HomeLaunchGrid to re-fetch and render the per-spec payload. */
async function openCatalog(page: import("@playwright/test").Page) {
  await page.reload();
  await expect(page.getByRole("heading", { name: "What would you like to build today?" })).toBeVisible();
}

test.describe("TS-Z — workflow catalog (basic tier: filter + gating)", () => {
  test.use({ tier: "basic" });

  test("TS-Z-01 filters non-launchable + revision/od_* out; gated row shown-locked", async ({ dashboard, page }) => {
    await dashboard.goto({ tier: "basic" });
    await mockWorkflows(page); // registered AFTER goto → wins over the catch-all
    await openCatalog(page);

    // Wait for the home→catalog view transition (AnimatePresence mode="wait")
    // to fully settle: the catalog mounts EXACTLY 2 launchable rows (user_stories
    // entitled + app_builder gated), while the exiting home CreationHub carries
    // 6. Pin the count so subsequent assertions run against the catalog only.
    const rows = page.getByRole("button").filter({ has: page.getByRole("heading", { level: 2 }) });
    await expect(rows).toHaveCount(2);

    // Entitled launchable renders by its FRIENDLY label.
    await expect(page.getByText("Generate product requirements")).toBeVisible();

    // Gate 1 — user_launchable:false rows are NEVER rendered.
    await expect(page.getByText(/Revised|user_stories_revision|raw-revision/i)).toHaveCount(0);
    await expect(page.getByText(/od_ppt|raw-od-ppt/i)).toHaveCount(0);
    // Home-only CreationHub rows confirm we are NOT on the home view.
    await expect(page.getByText("Pitch an idea")).toHaveCount(0);
    await expect(page.getByText("Platform workflows")).toHaveCount(0);

    // Gate 2 — a launchable-but-tier-gated row (app_builder needs pro) is SHOWN,
    // decorated with the lock/"Requires Pro plan" affordance (not hidden).
    await expect(page.getByText("Build an end-to-end application")).toBeVisible();
    await expect(page.getByText(/Requires Pro plan/i)).toHaveCount(1);

    // The raw API `name` is never rendered as a user-facing label.
    await expect(page.getByText("raw-user-stories")).toHaveCount(0);
  });

  test("TS-Z-02 launching an entitled idea-box row reaches the existing IdeaInputPage flow", async ({ dashboard, page }) => {
    await dashboard.goto({ tier: "basic" });
    await mockWorkflows(page);
    await openCatalog(page);

    // Settle the transition: the catalog mounts exactly 2 launchable rows.
    const rows = page.getByRole("button").filter({ has: page.getByRole("heading", { level: 2 }) });
    await expect(rows).toHaveCount(2);

    // Click the entitled launchable row → handleSelectFeature → mainView "input".
    // Scope to the launch row via its <h2> child — the Phase-39 row's sibling
    // "Inspect …" Info button shares the label in its aria-label (strict-mode-safe).
    await page
      .getByRole("button")
      .filter({ has: page.getByRole("heading", { level: 2, name: /Generate product requirements/i }) })
      .click();

    // The existing IdeaInputPage surface appears: an idea textarea + the Run
    // button (the SAME launch surface CreationHub routes to). The actual run
    // hand-off is already covered by ts-i.
    await expect(dashboard.ideaTextarea()).toBeVisible();
    await expect(dashboard.runButton()).toBeVisible();
  });
});

test.describe("TS-Z — workflow catalog (enterprise tier: all entitled)", () => {
  test.use({ tier: "enterprise" });

  test("TS-Z-03 at enterprise the previously-gated launchable is entitled (no lock)", async ({ dashboard, page }) => {
    await dashboard.goto({ tier: "enterprise" });
    await mockWorkflows(page);
    await openCatalog(page);

    // Settle the transition: the catalog mounts exactly 2 launchable rows.
    const rows = page.getByRole("button").filter({ has: page.getByRole("heading", { level: 2 }) });
    await expect(rows).toHaveCount(2);

    await expect(page.getByText("Build an end-to-end application")).toBeVisible();
    // Entitled at enterprise → no upgrade affordance on this row.
    await expect(page.getByText(/Requires Pro plan/i)).toHaveCount(0);
    // Gate 1 still hides the non-launchable rows regardless of tier.
    await expect(page.getByText(/Revised|raw-revision/i)).toHaveCount(0);
    await expect(page.getByText(/od_ppt|raw-od-ppt/i)).toHaveCount(0);
  });
});
