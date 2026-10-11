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

const SONNET_46_ID = "eu.anthropic.claude-sonnet-4-6-20251101-v1:0";

// The 4 originally-user_allowed labels MODEL_CATALOG exposes (constants.ts).
const ALLOWED_LABELS = ["Haiku 4.5", "Sonnet 4.5", "Sonnet 4.6", "Opus 4.5"];

// ── Phase 39 redesign helpers ────────────────────────────────────────────────
// The standalone AgentModelPicker ("Per-Agent Model", one <select> per agent) is
// gone, and since 24332e0c the popup's Agents tab embeds the Composer canvas
// (no per-card "View capabilities & configure" button). The per-agent Model lever
// lives in the canvas config rail: click the agent's node → rail "Config" tab →
// a native <select aria-label="Model"> whose options are "Default" + each catalog
// model's label (the tier suffix was dropped — CanvasConfigRail: tier is a
// display-only legacy label) — the WHOLE catalog per DECIDE-02. The picked model
// threads up via `selections[agentId].model` on run_pipeline.
// First user_stories LIBRARY_AGENT ("Domain Discovery Agent").
const FIRST_AGENT_ID = "domain-analyst";
type PW = import("@playwright/test").Page;

/** Keep the popup's edits and close it. Cancel DISCARDS the session's edits
 *  (ISS-258/ISS-363 snapshot restore), so the per-agent lever is kept through the
 *  footer "Save workflow" → name → Save, which closes the popup with the edit. */
async function saveAndClosePopup(page: PW) {
  await page.locator("button:not([title])", { hasText: /^Save workflow$/ }).click();
  await page.getByPlaceholder(/Competitive research/i).fill("Model pick");
  await page.getByRole("button", { name: /^Save$/ }).click();
  await expect(page.getByRole("heading", { name: /^Advanced Workflow Configuration/ })).toHaveCount(0);
}

/** From the open Agents tab: drill into the FIRST agent's Model lever <select>. */
async function openFirstAgentModelLever(page: PW) {
  await page.getByTestId(`canvas-node-${FIRST_AGENT_ID}`).click();
  await page.getByRole("complementary").getByRole("tab", { name: "Config" }).click();
  // The rail's Model select is labelled plainly "Model" (one rail, one agent).
  const model = page.getByRole("complementary").getByRole("combobox", { name: "Model", exact: true });
  await expect(model).toBeVisible();
  return model;
}


test.describe("TS-E — per-agent model selection (AgentModelPicker)", () => {
  test.beforeEach(async ({ dashboard }) => {
    // Land on the user_stories brief view (seeds 6 agents, no run yet) and type
    // an idea so Run becomes enabled. Then open the Advanced popup (Agents tab is
    // default; the per-agent model lever lives in each agent's expander).
    await dashboard.goto();
    await dashboard.selectWorkflow("Generate product requirements");
    // Wait for the brief screen before filling (avoid the home-composer race).
    await expect(
      dashboard.page.getByRole("heading", { name: /Provide the brief/i }),
    ).toBeVisible({ timeout: 15000 });
    await dashboard.fillIdea("Generate epics for a refunds workflow");
    await dashboard.openAdvanced();
  });

  test("TS-E-01 per-agent config → Default-first Model lever", async ({ page }) => {
    // One configurable canvas node per agent. user_stories seeds 6.
    await expect(page.locator('[data-testid^="canvas-node-wrap-"]')).toHaveCount(6);

    // Drill into the first agent's rail Config → Model lever; its FIRST option
    // is the "Default" (no-override) sentinel.
    const model = await openFirstAgentModelLever(page);
    await expect(model.locator("option").first()).toHaveText("Default");
  });

  // The alternate-state copies are covered by their own describe block below
  // (TS-E-01b-*), since they need a DIFFERENT setup than this block's beforeEach
  // (no-agents uses the `custom` workflow; loading installs a route override
  // BEFORE the picker mounts) — so they can't share the user_stories beforeEach.

  test("TS-E-02 catalog reflects backend (user_allowed only)", async ({ page }) => {
    const model = await openFirstAgentModelLever(page);

    // Option texts = "Default" + each catalog model's label (no tier suffix).
    const optionTexts = await model.locator("option").allTextContents();

    // All 4 originally-user_allowed catalog models are offered.
    for (const label of ALLOWED_LABELS) {
      expect(optionTexts).toContain(label);
    }
    // The no-override sentinel leads the list.
    expect(optionTexts[0]).toBe("Default");

    // RECONCILED (41-04, DECIDE-02 / D-23 — changed-behavior): the client
    // user_allowed filter was DROPPED. The Model lever (the SAME AdvancedExpander
    // the full-page Composer's inline model picker reuses) offers the WHOLE catalog
    // — server `_validate_model_overrides` is the authoritative allow-list — so the
    // user_allowed:false model "Opus 4.6" IS offered and there are 6
    // options (Default + 5). Reconciled from the OLD filter contract to this reality.
    expect(optionTexts).toContain("Opus 4.6");
    expect(optionTexts).toHaveLength(ALLOWED_LABELS.length + 2);
  });

  test("TS-E-03 picking a non-default model emits it under selections on run_pipeline", async ({ dashboard, page, mockSse }) => {
    // Drill into the FIRST agent (Domain Discovery Agent) Config → Model lever and
    // choose "Sonnet 4.6". Select by VALUE (the model id) — robust to the option's
    // new "{label} ({tier})" text format.
    const model = await openFirstAgentModelLever(page);
    await model.selectOption(SONNET_46_ID);

    // Keep the edit (Save closes the popup with it), then run.
    await saveAndClosePopup(page);
    await expect(dashboard.runButton()).toBeEnabled();
    await dashboard.runButton().click();

    const f = await mockSse.waitForCommand("run_pipeline");
    expect(f.pipeline_type).toBe("user_stories");

    // Phase 39: per-agent model now threads via the top-level `selections` object
    // (agentId → { model, … }), NOT `model_overrides` (AgentsPopup no longer emits
    // overrides — the inline Model lever is the single source of truth). Assert by
    // VALUE: some agent's selection carries the Sonnet 4.6 model id.
    const selections = f.selections as Record<string, { model?: string }> | undefined;
    expect(selections).toBeTruthy();
    expect(typeof selections).toBe("object");
    expect(Object.values(selections!).map((s) => s.model)).toContain(SONNET_46_ID);
  });

  test("TS-E-04 re-selecting Default removes the per-agent model (selections omitted)", async ({ dashboard, page, mockSse }) => {
    // Pick a model, then put it back to Default for the same (first) agent.
    const model = await openFirstAgentModelLever(page);
    await model.selectOption(SONNET_46_ID);
    await model.selectOption(""); // Default (value "") → model key deleted

    await saveAndClosePopup(page);
    await expect(dashboard.runButton()).toBeEnabled();
    await dashboard.runButton().click();

    const f = await mockSse.waitForCommand("run_pipeline");

    // Clearing the agent's only lever empties its selection → the agent key is
    // dropped → `selections` is omitted entirely (byte-identical plain-run payload).
    // Tolerate an empty object; the contract is "no Sonnet 4.6 for any agent".
    const selections = f.selections as Record<string, { model?: string }> | undefined;
    if (selections === undefined) {
      expect(selections).toBeUndefined();
    } else {
      expect(Object.values(selections).map((s) => s.model)).not.toContain(SONNET_46_ID);
    }
  });
});

/**
 * TS-E-01b — the AgentModelPicker's ALTERNATE render states (was a single
 * fixme covering all of them). Each state needs a bespoke setup, so they live
 * in their own describe (no shared beforeEach) and are split into one test per
 * state so partial coverage is explicit:
 *
 *   • no-agents  ("Add agents to assign per-agent levers.") → REAL test.
 *       The `custom` workflow seeds ZERO agents (verified at runtime: the
 *       Agents tab reads "Agents (0)" and the lever panel renders 0 <select>s),
 *       so agents.length === 0 and the no-agents copy renders. We open via
 *       openAdvanced() and assert the no-agents <p> directly (Phase 39 retired the
 *       "Per-Agent Model" header — the lever now lives per-agent under Advanced).
 *
 *   • loading    ("Loading levers…")                       → REAL test.
 *       A per-test route override DELAYS GET /api/capabilities by 1.5s. Because
 *       page.route is additive and the most-recently-added handler wins, this
 *       override (in the TEST, not a fixture) beats the mockApi handler. We open
 *       the picker and assert the loading copy shows while the fetch is in flight.
 *
 *   • no-jwt / fetch-failure copy                          → DELETED (see the
 *       note at the end of this describe for the covering owner).
 */
test.describe("TS-E-01b — AgentModelPicker alternate states", () => {
  test("TS-E-01b-noagents composer shows no inline model picker (custom seeds 0 agents)", async ({
    dashboard,
    page,
  }) => {
    // RE-ANCHORED (41-04): the "Compose a custom workflow" entry now opens the
    // full-page Composer (mainView='composer'), NOT the brief screen. The custom
    // pipeline seeds 0 agents → no agent rows → NO inline model picker surface.
    await dashboard.goto({ tier: "enterprise" });
    await dashboard.selectWorkflow("Compose a custom workflow");

    // The Composer opens on Canvas (its default); switch to the Simple view.
    await expect(dashboard.composerEyebrow()).toBeVisible({ timeout: 15000 });
    await page.getByRole("button", { name: /^Simple$/ }).click();

    // 0 agent rows → the empty-state copy, no inline model picker, no config levers.
    await expect(page.locator('[data-testid^="agent-row-"]')).toHaveCount(0);
    await expect(page.getByText(/No agents yet/i)).toBeVisible();
    await expect(page.getByRole("button", { name: /Model for / })).toHaveCount(0);
    await expect(page.getByRole("combobox", { name: /Model for / })).toHaveCount(0);
  });

  test("TS-E-01b-loading shows the loading copy while /api/capabilities is in flight", async ({
    dashboard,
    page,
  }) => {
    // getCapabilities is a shared cached GET (ISS-782/ISS-796): the FIRST fetch
    // of the session is the only in-flight window, so the gate goes in BEFORE
    // the app boots. The handler holds the response until the test releases it —
    // deterministic, no sleep. Test-level page.route (additive; most-recent
    // handler wins over mockApi's).
    let release!: () => void;
    const released = new Promise<void>((r) => { release = r; });
    await page.route("**/api/capabilities", async (route) => {
      await released;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ capabilities: [], model_catalog: [] }),
      });
    });

    // The AdvancedExpander ("Loading levers…") is the full-page Composer's
    // per-agent config panel since 24332e0c (the Advanced popup's per-agent
    // levers moved to the canvas rail / the library inspector, which render no
    // loading copy). Reach it as TS-E-05 does: compose → add an agent → pill.
    await dashboard.goto({ tier: "enterprise" });
    await dashboard.selectWorkflow("Compose a custom workflow");
    await expect(dashboard.composerEyebrow()).toBeVisible({ timeout: 15000 });
    await page.getByRole("button", { name: /^Simple$/ }).click();
    await page.getByRole("button", { name: "Add agent" }).first().click();
    await page.getByRole("button", { name: /^All$/ }).first().click();
    await page.getByRole("button", { name: /\+ Add/ }).first().click();
    const pill = page.getByRole("button", { name: /Model for / }).first();
    await expect(pill).toBeVisible();
    // The pill opens the row's config panel, which mounts the AdvancedExpander.
    await pill.click();

    // While the fetch is held the lever panel shows the loading copy (in place
    // of the "Advanced — {name}" expander, which renders once loaded).
    await expect(page.getByText("Loading levers…")).toBeVisible();

    // Once the (empty) catalog resolves, the loading copy goes away — proving it
    // was the transient in-flight state, not a stuck spinner.
    release();
    await expect(page.getByText("Loading levers…")).toBeHidden();
    await expect(page.getByRole("button", { name: /Advanced — / }).first()).toBeVisible();
  });
  // TS-E-01b-nojwt-and-failcopy was DELETED (it was an empty skipped body). Neither
  // branch is reachable from a browser:
  //   • no-jwt: the dashboard route guard redirects a token-less load to /login
  //     before the picker can mount — that redirect is owned by
  //     ts-a.auth.spec.ts TS-A-01.
  //   • "Failed to load models.": only the fallback for a rejection with a nullish
  //     `.message`; a routed 500 / abort always carries a message, so the literal
  //     copy cannot be produced here. KNOWN GAP: AgentModelPicker.test.tsx does not
  //     yet cover the picker's error / no-jwt branches at the component layer.
});

/**
 * TS-E-05 — the FULL-PAGE COMPOSER's inline model picker (41-04).
 *
 * "Compose a custom workflow" opens the full-page Composer (mainView='composer').
 * Custom seeds 0 agents, so we ADD one from the reused AgentLibrary, then drill the
 * composer's INLINE model picker: the row's model pill opens the per-agent config
 * panel, which mounts the REUSED `AdvancedExpander` — the SAME Model lever the modal
 * uses (aria-label "Model for {name}", whole catalog per DECIDE-02). This anchors the
 * model-picker coverage onto the composer without re-implementing the lever (INV-3).
 */
test.describe("TS-E-05 — composer inline model picker (full-page Composer)", () => {
  test("composer add-agent → inline model pill → reused Model lever offers the whole catalog", async ({
    dashboard,
    page,
  }) => {
    await dashboard.goto({ tier: "enterprise" });
    await dashboard.selectWorkflow("Compose a custom workflow");
    await expect(dashboard.composerEyebrow()).toBeVisible({ timeout: 15000 });
    // The Composer opens on Canvas; the inline model pill lives on Simple rows.
    await page.getByRole("button", { name: /^Simple$/ }).click();

    // Add an agent from the reused AgentLibrary (custom seeds 0).
    await page.getByRole("button", { name: "Add agent" }).first().click();
    await expect(page.getByRole("heading", { name: /^Add agent$/ })).toBeVisible();
    await page.getByRole("button", { name: /^All$/ }).first().click();
    await page.getByRole("button", { name: /\+ Add/ }).first().click();

    // A row now exists with the composer's INLINE model picker (the pill).
    const pill = page.getByRole("button", { name: /Model for / }).first();
    await expect(pill).toBeVisible();

    // Open the config panel + the reused AdvancedExpander → the Model lever <select>.
    await pill.click();
    await page.getByRole("button", { name: /Advanced — / }).first().click();
    const model = page.getByRole("combobox", { name: /Model for / }).first();
    await expect(model).toBeVisible();

    // The lever is the whole catalog (Default-first), reused from the shared payload.
    const optionTexts = await model.locator("option").allTextContents();
    expect(optionTexts[0]).toBe("Default");
    // (Option text is the model label alone — the tier suffix was dropped.)
    expect(optionTexts).toContain("Opus 4.6");
  });
});
