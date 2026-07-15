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

/** Open the saved-workflows page. Phase-39 RETIRED the "Catalog" header nav and
 *  moved "Your workflows" out of the catalog into a dedicated SavedWorkflowsPage,
 *  reached via the "My Workflows" header nav item (AppHeader navItems, key
 *  `saved-workflows`). Navigating there MOUNTS SavedWorkflowsPage → triggers a
 *  fresh `getUserWorkflows` GET. */
async function openSavedWorkflows(page: Page) {
  await page.getByRole("button", { name: "My Workflows" }).click();
}

test.describe("TS-Z2 — saved workflows (enterprise: compose → Save → appears → rename → launch)", () => {
  test.use({ tier: "enterprise" });

  test("TS-Z2-01 compose custom → Save persists a POST", async ({ dashboard, page }) => {
    test.fixme(true, "pre-existing feat/ui-2 red at 8c2f0b9d — not Phase 42 (RUNUI-09 baseline)");
    await dashboard.goto({ tier: "enterprise" });
    const { posts } = await mockUserWorkflows(page); // AFTER goto → wins over the catch-all

    // Phase-39: the "+ Create workflow" entry lives on the HOME view (the
    // HomeLaunchGrid header, SAVE-FROM-BOTH), which `dashboard.goto()` already
    // lands on — no separate catalog nav.
    await expect(page.getByRole("heading", { name: "What would you like to build today?" })).toBeVisible();

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
    // The library closes on +Add — wait for that before closing the popup so the
    // Cancel click can't race the library's own Cancel button.
    await expect(page.getByRole("heading", { name: "Add agent" })).toHaveCount(0);

    // Close the popup back to the composer. Phase-39 replaced the footer's plain
    // "Save changes" close with "Save workflow" (which opens the save modal), so
    // the popup's real close path is now "Cancel" — the added agent already lives
    // in the composer's parent state, so cancelling the popup does not discard it.
    // With the library closed, the popup footer's is the only "Cancel" on-page.
    await page.getByRole("button", { name: /^Cancel$/ }).click();
    await expect(page.getByRole("heading", { name: "Workflow configuration" })).toHaveCount(0);

    // Now the composer's own "Save workflow" (IdeaInputPage toolbar — the only one
    // left once the popup is closed) opens NameWorkflowModal → name → Save (POST),
    // and surfaces the "Saved" confirmation.
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
    test.fixme(true, "pre-existing feat/ui-2 red at 8c2f0b9d — not Phase 42 (RUNUI-09 baseline)");
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

    // Open the saved-workflows page (Phase-39 moved "Your workflows" here) → the
    // saved row renders by its OWN name. On SavedWorkflowsPage the card name is a
    // <p> (not a heading); the page's own <h1> is "My Workflows".
    await openSavedWorkflows(page);
    await expect(page.getByRole("heading", { name: "My Workflows" })).toBeVisible();
    await expect(page.getByText("My saved workflow", { exact: true })).toBeVisible();

    // ── Rename via the per-row kebab (aria-label "Workflow actions") →
    //    NameWorkflowModal (prefilled) → PATCH. ──
    const savedRowEl = page.locator(".group", { has: page.getByText("My saved workflow", { exact: true }) });
    await savedRowEl.hover();
    await savedRowEl.getByRole("button", { name: "Workflow actions" }).click();
    await page.getByRole("menuitem", { name: /^Rename$/ }).click();
    await expect(page.getByRole("heading", { name: "Rename workflow" })).toBeVisible();
    const nameInput = page.getByPlaceholder(/Competitive research/i);
    await expect(nameInput).toHaveValue("My saved workflow"); // prefilled
    await nameInput.fill("Renamed workflow");
    await page.getByRole("button", { name: /^Save$/ }).click();

    // Optimistic label update — the card now reads the new name.
    await expect(page.getByText("Renamed workflow", { exact: true })).toBeVisible();
    await expect(page.getByText("My saved workflow", { exact: true })).toHaveCount(0);

    // ── Launch the saved row via its card "Run workflow" button → onLaunchSaved →
    //    DashboardLayout seeds the composer and routes to IdeaInputPage PRE-LOADED.
    //    The launch preload (21-03) seeds pipelineAgents from agent_ids, so Run is
    //    reachable for this custom row (which would otherwise seed NO agents →
    //    "Add agents first"). Re-scope the card locator by the RENAMED name. ──
    const renamedRowEl = page.locator(".group", { has: page.getByText("Renamed workflow", { exact: true }) });
    await renamedRowEl.getByRole("button", { name: /Run workflow/ }).click();
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
