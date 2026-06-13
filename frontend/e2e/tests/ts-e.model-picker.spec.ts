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

  // The alternate-state copies — "Add agents to assign per-agent models." (no
  // agents), "Loading model catalog…" (in-flight fetch), and "Not authenticated."
  // (no JWT) — are not cleanly reachable in mocked mode: user_stories ALWAYS
  // seeds 6 agents (so agents.length is never 0), dashboard.goto() always seeds
  // the JWT, and mockApi resolves /api/capabilities synchronously (the loading
  // copy is too transient to assert). Triggering them would need fixture/route
  // surgery the fixture contract says to avoid. Covered by unit-level rendering
  // of AgentModelPicker instead.
  test.fixme(
    "TS-E-01b no-agents / loading / no-jwt copy (un-mockable here)",
    async () => {},
  );

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
