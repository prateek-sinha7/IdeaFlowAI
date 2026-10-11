/**
 * TS-Z2 — Saved Workflows (user-authored, named, persisted custom workflows).
 * Mocked spec, analog `ts-z.catalog.spec.ts`. Proves the WHOLE Phase-21 loop:
 *
 *   compose a custom workflow → Save (POST /api/user-workflows)
 *     → it appears in the catalog "Your workflows" section (GET)
 *     → Rename it (PATCH) — the label updates
 *     → launch the saved row → it pre-loads its agents into the full-page Composer
 *       (the load-bearing 21-03 launch preload: initialAgentIds seeds pipelineAgents
 *       so Run is reachable for a `custom` workflow that otherwise seeds NO agents).
 *
 * Since 41-04 (e1490fad) every `custom` entry (My Workflows "New workflow",
 * launching a saved custom row) opens the full-page ComposerPage, not IdeaInputPage.
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

    // GET /api/user-workflows/{id} — the single row. Launching a saved row pushes
    // /workflows/{id}/run, whose page.tsx effect fetches the row by id to pick the
    // surface (composer vs input); answering it with the LIST sent that effect a
    // row-less payload and bounced the launch to the default brief screen.
    if (method === "GET" && idMatch) {
      const row = rows.find((r) => r.id === idMatch[1]);
      return row
        ? route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(row) })
        : route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "Not found" }) });
    }
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
    await dashboard.goto({ tier: "enterprise" });
    const { posts } = await mockUserWorkflows(page); // AFTER goto → wins over the catch-all

    await expect(page.getByRole("heading", { name: "What would you like to build today?" })).toBeVisible();

    // RE-ANCHORED. FIX-181 (9665f489) removed Home's "+ Create workflow" button;
    // the dedicated create entry is now My Workflows' "New workflow" (ec1ea70f),
    // wired to the SAME handleSelectFeature("custom"). Since 41-04 (e1490fad)
    // that opens the full-page Composer (not IdeaInputPage) on an EMPTY canvas.
    await openSavedWorkflows(page);
    await expect(page.getByRole("heading", { name: "My Workflows" })).toBeVisible();
    await page.getByRole("button", { name: "New workflow" }).click();
    await expect(dashboard.composerEyebrow()).toBeVisible();
    await expect(dashboard.composerSummary()).toContainText("0 agents");

    // Add an agent: the canvas "Add agent at end" → AgentLibrary "+ Add" (the
    // library closes on +Add).
    await page.getByRole("button", { name: "Add agent at end" }).click();
    await expect(page.getByRole("heading", { name: "Add agent" })).toBeVisible();
    await page.getByRole("button", { name: /^\+ Add$/ }).first().click();
    await expect(page.getByRole("heading", { name: "Add agent" })).toHaveCount(0);
    await expect(dashboard.composerSummary()).toContainText("1 agents");

    // The Composer names the workflow INLINE (its header "Workflow name" field —
    // the NameWorkflowModal step is retired here), then its single header
    // "Save workflow" persists (POST) and flips to the "Saved" confirmation.
    await dashboard.composerNameInput().fill("My saved workflow");
    await page.getByRole("button", { name: "Save workflow" }).click();

    // The composer shows the "Saved" confirmation and the POST fired with the
    // composer triple (base_pipeline_type custom + a non-empty agent_ids).
    await expect(page.getByText("Saved", { exact: true })).toBeVisible();
    expect(posts.length).toBe(1);
    expect(posts[0].name).toBe("My saved workflow");
    expect(posts[0].base_pipeline_type).toBe("custom");
    expect((posts[0].agent_ids as string[]).length).toBeGreaterThan(0);
  });

  test("TS-Z2-02 saved row appears in 'Your workflows', renames, and launches pre-loaded", async ({ dashboard, mockSse, page }) => {
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
    // RE-ANCHORED: since 41-04 (e1490fad) a saved `custom` row launches into the
    // full-page Composer PRE-LOADED (handleLaunchSaved → mainView "composer",
    // /workflows/{id}/run), not IdeaInputPage — there is no "Advanced … N agents"
    // affordance or "Run workflow" button there.
    const renamedRowEl = page.locator(".group", { has: page.getByText("Renamed workflow", { exact: true }) });
    await renamedRowEl.getByRole("button", { name: /Run workflow/ }).click();
    await page.waitForURL(/\/workflows\/saved-1\/run$/);
    await expect(dashboard.composerEyebrow()).toBeVisible();

    // Pre-loaded proof (the load-bearing 21-03 change): the saved agents seed the
    // composer — the header summary counts 2 agents, both render by name, and
    // with a brief typed "Run once" launches exactly those agents. Without the
    // launch preload a `custom` workflow seeds ZERO agents → Run once is blocked
    // ("Add at least one agent first") and nothing launches.
    await expect(dashboard.composerSummary()).toContainText("2 agents");
    // Each seeded agent renders as its own canvas node (per-node controls are
    // labelled with the agent's full name; the node title drops the " Agent" suffix).
    await expect(page.getByRole("button", { name: "Rename Market Research Agent", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Rename Strategy Analysis Agent", exact: true })).toBeVisible();
    await dashboard.composerBrief().fill("Research the AI coding-assistant market and produce a SWOT.");
    const runBtn = dashboard.composerRunOnce();
    await expect(runBtn).toBeEnabled();
    await expect(runBtn).not.toHaveAttribute("title", "Add at least one agent first"); // the seed loaded
    await runBtn.click();
    const frame = await mockSse.waitForCommand("run_pipeline");
    expect(frame.pipeline_type).toBe("custom");
    expect(frame.agent_ids).toEqual(["market-research-agent", "swot-analyst"]);
  });
});
