/**
 * TS-Z2 — Saved Workflows (user-authored, named, persisted custom workflows).
 * Mocked spec, analog `ts-z.catalog.spec.ts`. Proves the WHOLE Phase-21 loop:
 *
 *   compose a custom workflow → Save (POST /api/user-workflows)
 *     → it appears in the catalog "Your workflows" section (GET)
 *     → Rename it (PATCH) — the label updates
 *     → launch the saved row → it pre-loads its agents and reaches IdeaInputPage
 *       (the load-bearing 21-03 launch preload: initialAgentIds seeds pipelineAgents
 *       so Run is reachable for a `custom` workflow that otherwise seeds NO agents).
 *
 * MOCK PRECEDENCE (do NOT edit fixtures/): the fixtures' `installMockApi`
 * registers a single catch-all `page.route("**\/api\/**", …)` (which returns an
 * empty `{}` for any unhandled path — including `/api/user-workflows`, breaking
 * the catalog's `getUserWorkflows().map(...)`). Playwright matches `page.route`
 * handlers in REVERSE registration order, so a per-spec
 * `page.route("**\/api\/user-workflows*", …)` registered AFTER `dashboard.goto()`
 * is the LATER registration and therefore WINS. The handler is STATEFUL: GET
 * reflects POST/PATCH/DELETE so the saved-row lifecycle is observable end-to-end.
 *
 * `tier: "enterprise"` — `custom` is enterprise-only (entitlement gate); a lower
 * tier cannot compose/launch a custom workflow.
 */
import { test, expect } from "../fixtures/test";
import type { Page, Route } from "@playwright/test";

interface SavedRow {
  id: string;
  name: string;
  description?: string | null;
  base_pipeline_type: string;
  agent_ids: string[];
  model_overrides?: Record<string, string> | null;
  created_at?: string;
  updated_at?: string;
}

/**
 * Install a STATEFUL `/api/user-workflows` mock. Registered AFTER `dashboard.goto()`
 * so it wins by reverse-registration precedence over the fixtures' catch-all.
 *
 *   GET    → the live `rows` array (reflects prior POST/PATCH/DELETE)
 *   POST   → append a fresh row (echo it back, the create contract)
 *   PATCH  → rename the matching row (echo it back)
 *   DELETE → 204
 *
 * Returns `{ rows, posts }` so the spec can assert the create payload fired.
 */
async function mockUserWorkflows(page: Page) {
  // Seeds with REAL custom-eligible LIBRARY_AGENTS ids so that, on launch, the
  // IdeaInputPage seed (`initialAgentIds.map(id => LIBRARY_AGENTS.find(...))`)
  // resolves to a NON-empty pipeline → Run becomes reachable (the launch preload).
  const rows: SavedRow[] = [];
  const posts: Array<Record<string, unknown>> = [];

  // NOTE: glob `**` (not `*`) after the path so it also matches the
  // `/api/user-workflows/{id}` sub-path used by PATCH/DELETE (a single `*` does
  // NOT cross a `/` in Playwright glob → those would fall to the catch-all).
  await page.route("**/api/user-workflows**", async (route: Route) => {
    const req = route.request();
    const method = req.method();
    const url = req.url();
    // /api/user-workflows/{id} for PATCH/DELETE
    const idMatch = url.match(/\/api\/user-workflows\/([^/?]+)/);

    if (method === "GET") {
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(rows) });
    }
    if (method === "POST") {
      const body = (req.postDataJSON?.() ?? {}) as Record<string, unknown>;
      posts.push(body);
      const created: SavedRow = {
        id: `saved-${rows.length + 1}`,
        name: String(body.name ?? "Untitled"),
        description: (body.description as string) ?? null,
        base_pipeline_type: String(body.base_pipeline_type ?? "custom"),
        agent_ids: (body.agent_ids as string[]) ?? [],
        model_overrides: (body.model_overrides as Record<string, string>) ?? null,
        created_at: "2026-06-14T12:00:00Z",
        updated_at: "2026-06-14T12:00:00Z",
      };
      rows.push(created);
      return route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(created) });
    }
    if (method === "PATCH" && idMatch) {
      const id = idMatch[1];
      const body = (req.postDataJSON?.() ?? {}) as Record<string, unknown>;
      const row = rows.find((r) => r.id === id);
      if (row) {
        if (body.name != null) row.name = String(body.name);
        if (body.description !== undefined) row.description = (body.description as string) ?? null;
      }
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(row ?? {}) });
    }
    if (method === "DELETE" && idMatch) {
      const id = idMatch[1];
      const i = rows.findIndex((r) => r.id === id);
      if (i >= 0) rows.splice(i, 1);
      return route.fulfill({ status: 204, body: "" });
    }
    return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });

  return { rows, posts };
}

/** Navigate to the in-dashboard Catalog view via the header nav button. It
 *  re-MOUNTS WorkflowCatalog → triggers a fresh `getUserWorkflows` GET. */
async function openCatalog(page: Page) {
  await page.getByRole("button", { name: /^Catalog$/ }).click();
}

test.describe("TS-Z2 — saved workflows (enterprise: compose → Save → appears → rename → launch)", () => {
  test.use({ tier: "enterprise" });

  test("TS-Z2-01 compose custom → Save persists a POST", async ({ dashboard, page }) => {
    await dashboard.goto({ tier: "enterprise" });
    const { posts } = await mockUserWorkflows(page); // AFTER goto → wins over the catch-all
    await openCatalog(page);

    // "+ Create workflow" → onSelectFeature("custom") → the custom composer
    // (IdeaInputPage). `custom` seeds ZERO agents, so Save is disabled until one
    // is added (the same gate as Run).
    await page.getByRole("button", { name: /Create workflow/i }).click();
    await expect(dashboard.ideaTextarea()).toBeVisible();

    // Add an agent: Advanced → "+ Add agent" → AgentLibrary "+ Add".
    await dashboard.openAdvanced();
    await page.getByRole("button", { name: /\+ Add agent/i }).first().click();
    await expect(page.getByRole("heading", { name: "Add agent" })).toBeVisible();
    await page.getByRole("button", { name: /^\+ Add$/ }).first().click();
    // Close the library + popup back to the composer.
    await page.getByRole("button", { name: /Save changes/i }).click();

    // Now "Save workflow" is enabled → NameWorkflowModal → name → Save (POST).
    await page.getByRole("button", { name: /Save workflow/i }).click();
    await expect(page.getByRole("heading", { name: "Save workflow" })).toBeVisible();
    await page.getByPlaceholder(/Competitive research/i).fill("My saved workflow");
    await page.getByRole("button", { name: /^Save$/ }).click();

    // The composer shows the "Saved" confirmation and the POST fired with the
    // composer triple (base_pipeline_type custom + a non-empty agent_ids).
    await expect(page.getByText("Saved", { exact: true })).toBeVisible();
    expect(posts.length).toBe(1);
    expect(posts[0].name).toBe("My saved workflow");
    expect(posts[0].base_pipeline_type).toBe("custom");
    expect((posts[0].agent_ids as string[]).length).toBeGreaterThan(0);
  });

  test("TS-Z2-02 saved row appears in 'Your workflows', renames, and launches pre-loaded", async ({ dashboard, page }) => {
    await dashboard.goto({ tier: "enterprise" });
    const { rows } = await mockUserWorkflows(page);

    // Pre-seed a persisted custom row (the prior-test Save outcome) with REAL
    // custom agent ids so the launch seed resolves to a non-empty pipeline.
    rows.push({
      id: "saved-1",
      name: "My saved workflow",
      description: "Competitive research deck",
      base_pipeline_type: "custom",
      agent_ids: ["market-research-agent", "swot-analyst"],
      model_overrides: null,
      created_at: "2026-06-14T12:00:00Z",
      updated_at: "2026-06-14T12:00:00Z",
    });

    // Open the catalog → the "Your workflows" section renders the saved row by its
    // OWN name (user rows render their name; the never-raw-name rule is manifest-only).
    await openCatalog(page);
    await expect(page.getByText("Your workflows")).toBeVisible();
    await expect(page.getByRole("heading", { name: "My saved workflow" })).toBeVisible();

    // ── Rename via the per-row kebab → NameWorkflowModal (prefilled) → PATCH. ──
    const savedRowEl = page.locator(".group", { has: page.getByRole("heading", { name: "My saved workflow" }) });
    await savedRowEl.hover();
    await savedRowEl.getByRole("button").last().click(); // the kebab (MoreHorizontal)
    await page.getByRole("button", { name: /^Rename$/ }).click();
    await expect(page.getByRole("heading", { name: "Rename workflow" })).toBeVisible();
    const nameInput = page.getByPlaceholder(/Competitive research/i);
    await expect(nameInput).toHaveValue("My saved workflow"); // prefilled
    await nameInput.fill("Renamed workflow");
    await page.getByRole("button", { name: /^Save$/ }).click();

    // Optimistic label update — the row now reads the new name.
    await expect(page.getByRole("heading", { name: "Renamed workflow" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "My saved workflow" })).toHaveCount(0);

    // ── Launch the saved row → onLaunchSaved → DashboardLayout seeds the composer
    //    and routes to IdeaInputPage PRE-LOADED. The launch preload (21-03) seeds
    //    pipelineAgents from agent_ids, so Run is reachable for this custom row
    //    (which would otherwise seed NO agents → "Add agents first"). ──
    await page.getByRole("heading", { name: "Renamed workflow" }).click();
    await expect(dashboard.ideaTextarea()).toBeVisible();

    // Pre-loaded proof (the load-bearing 21-03 change): the seeded agents are
    // reflected in the "Advanced … N agents" affordance (non-zero), AND once a
    // brief is typed the Run button reads "Run workflow" and is ENABLED. Without
    // the launch preload a `custom` workflow seeds ZERO agents → Run would read
    // "Add agents first" and stay disabled.
    await expect(page.getByRole("button", { name: /Advanced/ })).toBeVisible();
    await expect(page.getByText(/2 agents/)).toBeVisible();
    await dashboard.fillIdea("Research the AI coding-assistant market and produce a SWOT.");
    const runBtn = page.getByRole("button", { name: /Run workflow/ });
    await expect(runBtn).toBeVisible(); // NOT "Add agents first" → the seed loaded
    await expect(runBtn).toBeEnabled();
  });
});
