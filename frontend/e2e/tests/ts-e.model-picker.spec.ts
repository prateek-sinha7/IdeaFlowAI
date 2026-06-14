/**
 * TS-E — Per-agent model selection (AgentModelPicker).
 *
 * The picker lives in the AgentsPopup → Agents tab footer ("Per-Agent Model").
 * Its model list is LIVE from GET /api/capabilities → model_catalog, filtered to
 * `user_allowed` only. In mocked mode `mockApi` serves MODEL_CATALOG from
 * constants.ts: 5 models, 4 user-allowed ("Haiku 4.5", "Sonnet 4.5",
 * "Sonnet 4.6", "Opus 4.5"); "Opus 4.6" is user_allowed:false and must NOT show.
 *
 * A per-agent selection threads up via onModelOverridesChange → IdeaInputPage
 * extraParams → useWorkflow Object.assign → top-level `model_overrides` on the
 * outbound run_pipeline frame (agentId → modelId). No selection ⇒ the key is
 * omitted entirely (byte-identical payload, INV-3).
 *
 * The user_stories pipeline seeds 6 agents from LIBRARY_AGENTS (ordered); the
 * FIRST is "Domain Discovery Agent" (id `domain-analyst`). The picker rows are
 * labelled by agent NAME; the run_pipeline agent_ids / model_overrides keys are
 * the agent IDs — so we assert overrides by VALUE (the model id) which is robust
 * regardless of the name→id mapping.
 */
import { test, expect } from "../fixtures/test";

const SONNET_46_LABEL = "Sonnet 4.6";
const SONNET_46_ID = "eu.anthropic.claude-sonnet-4-6-20251101-v1:0";

// The 4 user_allowed labels MODEL_CATALOG exposes (constants.ts).
const ALLOWED_LABELS = ["Haiku 4.5", "Sonnet 4.5", "Sonnet 4.6", "Opus 4.5"];
// user_allowed:false → must never appear in the picker.
const DISALLOWED_LABEL = "Opus 4.6";

test.describe("TS-E — per-agent model selection (AgentModelPicker)", () => {
  test.beforeEach(async ({ dashboard }) => {
    // Land on the user_stories brief view (seeds 6 agents, no run yet) and type
    // an idea so Run becomes enabled. Then open the per-agent model picker.
    await dashboard.goto();
    await dashboard.selectWorkflow("Generate product requirements");
    await dashboard.fillIdea("Generate epics for a refunds workflow");
    await dashboard.openModelPicker();
  });

  test("TS-E-01 header + one Default-first <select> per agent", async ({ page }) => {
    // Header present (rendered by the picker once mounted).
    await expect(page.getByText("Per-Agent Model")).toBeVisible();

    // One native <select> per agent. user_stories seeds 6 LIBRARY_AGENTS, so we
    // expect ≥ 1 (and in practice exactly 6) — wait for the catalog to load so
    // the rows render (vs the transient "Loading model catalog…" state).
    const selects = page.locator("select");
    await expect(selects.first()).toBeVisible();
    const count = await selects.count();
    expect(count).toBeGreaterThanOrEqual(1);

    // The picker rows are labelled by agent NAME; the first user_stories agent
    // is "Domain Discovery Agent". The name appears twice on screen (flow-grid
    // card + picker row), so scope to the picker ROW = the select's parent div.
    const firstRow = selects.first().locator("xpath=..");
    await expect(firstRow.getByText("Domain Discovery Agent", { exact: true })).toBeVisible();

    // Every select's FIRST option is the "Default" (no-override) sentinel.
    for (let i = 0; i < count; i++) {
      const firstOption = selects.nth(i).locator("option").first();
      await expect(firstOption).toHaveText("Default");
    }
  });

  // The alternate-state copies are covered by their own describe block below
  // (TS-E-01b-*), since they need a DIFFERENT setup than this block's beforeEach
  // (no-agents uses the `custom` workflow; loading installs a route override
  // BEFORE the picker mounts) — so they can't share the user_stories beforeEach.

  test("TS-E-02 catalog reflects backend (user_allowed only)", async ({ page }) => {
    const firstSelect = page.locator("select").first();
    await expect(firstSelect).toBeVisible();

    // Option texts = "Default" + each user_allowed model label.
    const optionTexts = await firstSelect.locator("option").allTextContents();

    // All 4 user-allowed catalog models are offered…
    for (const label of ALLOWED_LABELS) {
      expect(optionTexts).toContain(label);
    }
    // …and the user_allowed:false model is filtered out.
    expect(optionTexts).not.toContain(DISALLOWED_LABEL);

    // Sanity: the no-override sentinel leads the list (5 options total: Default + 4).
    expect(optionTexts[0]).toBe("Default");
    expect(optionTexts).toHaveLength(ALLOWED_LABELS.length + 1);
  });

  test("TS-E-03 picking a non-default model emits model_overrides on run_pipeline", async ({ dashboard, page, mockWs }) => {
    // Choose "Sonnet 4.6" for the FIRST agent's select (Domain Discovery Agent).
    const firstSelect = page.locator("select").first();
    await expect(firstSelect).toBeVisible();
    await firstSelect.selectOption({ label: SONNET_46_LABEL });

    // Close the popup (Save changes) and run.
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(dashboard.runButton()).toBeEnabled();
    await dashboard.runButton().click();

    const f = await mockWs.waitForClientFrame("run_pipeline");
    expect(f.pipeline_type).toBe("user_stories");

    // model_overrides is a top-level object (agentId → modelId). We assert by
    // VALUE: the Sonnet 4.6 model id is present for some agent (the first one).
    const overrides = f.model_overrides as Record<string, string> | undefined;
    expect(overrides).toBeTruthy();
    expect(typeof overrides).toBe("object");
    expect(Object.values(overrides!)).toContain(SONNET_46_ID);
  });

  test("TS-E-04 re-selecting Default removes the override (key omitted)", async ({ dashboard, page, mockWs }) => {
    // Pick a model, then put it back to Default for the same (first) agent.
    const firstSelect = page.locator("select").first();
    await expect(firstSelect).toBeVisible();
    await firstSelect.selectOption({ label: SONNET_46_LABEL });
    await firstSelect.selectOption({ label: "Default" }); // value "" → override deleted

    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(dashboard.runButton()).toBeEnabled();
    await dashboard.runButton().click();

    const f = await mockWs.waitForClientFrame("run_pipeline");

    // All-default ⇒ extraParams omitted ⇒ no model_overrides key at all. (If a
    // future impl sends an empty object, accept that too — the contract is "no
    // override for this agent".)
    const overrides = f.model_overrides as Record<string, string> | undefined;
    if (overrides === undefined) {
      expect(overrides).toBeUndefined();
    } else {
      expect(Object.values(overrides)).not.toContain(SONNET_46_ID);
      expect(Object.keys(overrides)).toHaveLength(0);
    }
  });
});

/**
 * TS-E-01b — the AgentModelPicker's ALTERNATE render states (was a single
 * fixme covering all of them). Each state needs a bespoke setup, so they live
 * in their own describe (no shared beforeEach) and are split into one test per
 * state so partial coverage is explicit:
 *
 *   • no-agents  ("Add agents to assign per-agent models.") → REAL test.
 *       The `custom` workflow seeds ZERO agents (verified at runtime: the
 *       Agents tab reads "Agents (0)" and the picker renders 0 <select>s), so
 *       agents.length === 0 and the no-agents copy renders. Note: we open via
 *       openAdvanced() (NOT openModelPicker()) because openModelPicker asserts
 *       "Per-Agent Model" which is non-unique under strict mode here — we assert
 *       the no-agents <p> directly, which IS unique.
 *
 *   • loading    ("Loading model catalog…")               → REAL test.
 *       A per-test route override DELAYS GET /api/capabilities by 1.5s. Because
 *       page.route is additive and the most-recently-added handler wins, this
 *       override (in the TEST, not a fixture) beats the mockApi handler. We open
 *       the picker and assert the loading copy shows while the fetch is in flight.
 *
 *   • no-jwt / fetch-failure copy                          → stays FIXME (below).
 *       See the precise reasons on the test.fixme.
 */
test.describe("TS-E-01b — AgentModelPicker alternate states", () => {
  test("TS-E-01b-noagents shows the no-agents copy (custom seeds 0 agents)", async ({
    dashboard,
    page,
  }) => {
    // `custom` is the only workflow that seeds 0 agents → agents.length === 0.
    await dashboard.goto({ tier: "enterprise" });
    await dashboard.selectWorkflow("Compose a custom workflow");
    await dashboard.fillIdea(
      "Research the competitive landscape for AI coding assistants",
    );

    // Open the Advanced popup (Agents tab is default; the AgentModelPicker is its
    // footer). We deliberately use openAdvanced(), not openModelPicker(), because
    // the latter asserts the (here non-unique) "Per-Agent Model" header.
    await dashboard.openAdvanced();

    // Sanity: the Agents tab confirms there really are 0 agents…
    await expect(
      page.getByRole("button", { name: /Agents \(0\)/ }),
    ).toBeVisible();
    // …and there are no per-agent <select> rows.
    await expect(page.locator("select")).toHaveCount(0);

    // The no-agents branch copy is shown (catalog loaded, no error, 0 agents).
    await expect(
      page.getByText("Add agents to assign per-agent models."),
    ).toBeVisible();
  });

  test("TS-E-01b-loading shows the loading copy while /api/capabilities is in flight", async ({
    dashboard,
    page,
  }) => {
    // Land on user_stories (seeds 6 agents) so the picker mounts and fetches.
    await dashboard.goto({ tier: "enterprise" });
    await dashboard.selectWorkflow("Generate product requirements");
    await dashboard.fillIdea("Generate epics for a refunds workflow");

    // Per-test route override (additive; most-recent handler wins) that DELAYS
    // the capabilities fetch long enough to observe the loading state. This is a
    // TEST-level page.route — not a fixture edit — which the contract allows.
    await page.route("**/api/capabilities", async (route) => {
      await new Promise((r) => setTimeout(r, 1500));
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ capabilities: [], model_catalog: [] }),
      });
    });

    // Open Advanced → the picker mounts and kicks off the (now-delayed) fetch.
    await dashboard.openAdvanced();

    // While the fetch is in flight the picker shows the loading copy. Assert it
    // appears within the delay window (well under 1.5s).
    await expect(page.getByText("Loading model catalog…")).toBeVisible({
      timeout: 1000,
    });

    // And once the (empty) catalog resolves, the loading copy goes away — proving
    // it was the transient in-flight state, not a stuck spinner.
    await expect(page.getByText("Loading model catalog…")).toBeHidden({
      timeout: 4000,
    });
  });

  // no-jwt ("Not authenticated.") and the fetch-failure COPY ("Failed to load
  // models.") are NOT reachable in mocked mode:
  //
  //   • no-jwt: the picker only renders inside the dashboard, but the dashboard
  //     has a route guard — navigating without a token redirects straight to
  //     /login (verified: url becomes …/login, the home heading never mounts), so
  //     the AgentModelPicker (and its "Not authenticated." branch) is never
  //     reached. Clearing the token mid-session would likewise bounce to /login.
  //
  //   • "Failed to load models." copy: that string is only the FALLBACK used when
  //     the rejected error has a nullish `.message`. A route → 500 surfaces the
  //     response body / statusText instead (e.g. the red error box shows "{}"),
  //     and route.abort() yields a TypeError whose message is "Failed to fetch" —
  //     neither is nullish, so the literal "Failed to load models." copy can't be
  //     produced via route manipulation. (The error UI itself IS reachable, but
  //     asserting this exact copy would be a false assertion.)
  test.fixme(
    "TS-E-01b-nojwt-and-failcopy: no-jwt redirects to /login (picker never mounts); 500/abort surface the body/statusText, never the literal 'Failed to load models.' fallback",
    async () => {},
  );
});
