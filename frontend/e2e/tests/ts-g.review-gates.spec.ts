/**
 * TS-G — Pre-run Review-gates section (ReviewGatesSection on IdeaInputPage).
 *
 * The section renders on IdeaInputPage below the "Advanced" button. It lists
 * one row (a checkbox inside a <label>) per pipeline agent; checked agents pause
 * the pipeline for a Human review gate after they finish. The header is an
 * expandable <button aria-expanded> whose summary reads "no gates" or
 * "{n} agent[s] pause for review". Each agent is pre-checked iff its static
 * frontmatter declares `gate === "Human_Gate"` (and then shows a `default` pill).
 *
 * The wiring contract (see ReviewGatesSection.tsx / .test.tsx):
 *   - the section reports (gateAgentIds, touched) upward;
 *   - IdeaInputPage attaches `gate_agent_ids` to the run_pipeline payload ONLY
 *     when `touched` is true (even `[]`); untouched ⇒ the field is omitted so the
 *     backend keeps its static default. `gate_agent_ids` lands TOP-LEVEL on the
 *     run_pipeline frame (useWorkflow merges extraParams via Object.assign).
 *
 * NOTE on the seeded workflow: we use `user_stories` (selected from home +
 * an idea typed). Its six LIBRARY_AGENTS all carry `gate: null`, so there are
 * NO Human_Gate defaults — the summary starts at "no gates" and no `default`
 * pill renders. TS-G-02 asserts exactly that reality and that toggling works.
 *
 * The checkbox <input> is `.sr-only` (visually hidden) — we interact via the
 * enclosing <label> by clicking the agent name text.
 */
import { test, expect } from "../fixtures/test";
import type { Locator } from "@playwright/test";

const IDEA = "Generate epics and stories for a refunds workflow with multi-currency support";
const WORKFLOW = "Generate product requirements"; // → user_stories, IdeaInputPage flow

// The user_stories lineup (LIBRARY_AGENTS, in pipeline order). All gate: null.
const USER_STORIES_AGENT_NAMES = [
  "Domain Discovery Agent",
  "Backlog Architecture Agent",
  "Estimation Agent",
  "Quality Requirements Agent",
  "Quality Review Agent",
  "Delivery Compilation Agent",
];

/** The Review-gates expandable header button (carries aria-expanded). */
function gatesHeader(page: import("@playwright/test").Page): Locator {
  return page.getByRole("button", { name: /Review gates/ });
}

/** The <label> row for an agent, located by its visible name text. */
function gateRow(page: import("@playwright/test").Page, agentName: string): Locator {
  // Each row is a <label> containing the agent name; scope to it so a click
  // toggles that row's `.sr-only` checkbox (clicking the label/name works).
  return page.locator("label").filter({ hasText: agentName });
}

test.describe("TS-G — pre-run Review-gates section", () => {
  test.beforeEach(async ({ dashboard }) => {
    // Land on IdeaInputPage for user_stories with an idea typed (Run-enabled).
    await dashboard.goto();
    await dashboard.selectWorkflow(WORKFLOW);
    // Phase 39: selecting a workflow is a real transition to the "Provide the
    // brief" screen. Fill the brief only AFTER that screen mounts, else the fill
    // races the still-mounted home composer and the brief textarea stays empty
    // (which keeps the Run button disabled — the TS-G-03 failure mode).
    await expect(
      dashboard.page.getByRole("heading", { name: /Provide the brief/i }),
    ).toBeVisible({ timeout: 15000 });
    await dashboard.fillIdea(IDEA);
    // The section renders below "Advanced" once agents exist (always, here).
    await expect(gatesHeader(dashboard.page)).toBeVisible();
  });

  test("TS-G-01 collapsed summary + expand reveals helper text and one row per agent", async ({ dashboard }) => {
    const page = dashboard.page;
    const header = gatesHeader(page);

    // Collapsed by default → aria-expanded=false, body (helper text) hidden.
    await expect(header).toHaveAttribute("aria-expanded", "false");
    const helper = page.getByText(
      "Checked agents pause the pipeline for your review after they finish. Pre-set to the recommended defaults — adjust as needed.",
    );
    await expect(helper).toBeHidden();

    // No user_stories agent is gated by default → summary reads "no gates".
    await expect(header).toContainText("no gates");

    // Expand → aria-expanded flips, helper text + one row per agent appear.
    await header.click();
    await expect(header).toHaveAttribute("aria-expanded", "true");
    await expect(helper).toBeVisible();
    for (const name of USER_STORIES_AGENT_NAMES) {
      await expect(gateRow(page, name)).toBeVisible();
    }
    // Exactly six checkbox inputs (one per agent), all sr-only.
    await expect(page.locator('input[type="checkbox"].sr-only')).toHaveCount(
      USER_STORIES_AGENT_NAMES.length,
    );
  });

  test("TS-G-02 default gates: user_stories has no Human_Gate defaults → no `default` pill; toggling works", async ({ dashboard }) => {
    const page = dashboard.page;
    const header = gatesHeader(page);

    // Default reality for user_stories: zero default gates.
    await expect(header).toContainText("no gates");

    await header.click();
    await expect(header).toHaveAttribute("aria-expanded", "true");

    // No `default` pill renders anywhere (no agent has gate === "Human_Gate").
    await expect(page.getByText("default", { exact: true })).toHaveCount(0);

    // Every checkbox starts unchecked (the pre-check set is empty).
    const checkboxes = page.locator('input[type="checkbox"].sr-only');
    await expect(checkboxes).toHaveCount(USER_STORIES_AGENT_NAMES.length);
    for (let i = 0; i < USER_STORIES_AGENT_NAMES.length; i++) {
      await expect(checkboxes.nth(i)).not.toBeChecked();
    }

    // Toggling a row checks its checkbox and updates the summary to the
    // "{n} agent pause for review" copy (n=1 → singular "agent").
    await gateRow(page, USER_STORIES_AGENT_NAMES[0]).click();
    await expect(
      gateRow(page, USER_STORIES_AGENT_NAMES[0]).locator('input[type="checkbox"]'),
    ).toBeChecked();
    await expect(header).toContainText("1 agent pause for review");
    await expect(header).not.toContainText("agents pause");

    // A second toggle pluralizes the summary.
    await gateRow(page, USER_STORIES_AGENT_NAMES[1]).click();
    await expect(header).toContainText("2 agents pause for review");

    // Un-toggling the first returns toward "no gates" semantics (n=1 again).
    await gateRow(page, USER_STORIES_AGENT_NAMES[0]).click();
    await expect(header).toContainText("1 agent pause for review");
  });

  test("TS-G-03a toggle → run_pipeline carries gate_agent_ids (because the section was touched)", async ({ dashboard, mockWs }) => {
    const page = dashboard.page;
    const header = gatesHeader(page);

    // Expand, check one agent (click the row → toggles its sr-only checkbox).
    await header.click();
    await gateRow(page, USER_STORIES_AGENT_NAMES[0]).click();
    await expect(
      gateRow(page, USER_STORIES_AGENT_NAMES[0]).locator('input[type="checkbox"]'),
    ).toBeChecked();

    // Close the section, then Run.
    await header.click();
    await expect(header).toHaveAttribute("aria-expanded", "false");

    await expect(dashboard.runButton()).toBeEnabled();
    await dashboard.runButton().click();

    const f = await mockWs.waitForClientFrame("run_pipeline");
    // Touched ⇒ gate_agent_ids present (TOP-LEVEL) as an array of the checked ids.
    expect(Array.isArray(f.gate_agent_ids)).toBe(true);
    // Domain Discovery Agent → id "domain-analyst" (the row we checked).
    expect(f.gate_agent_ids).toEqual(["domain-analyst"]);
  });

  test("TS-G-03b run without touching the section → gate_agent_ids omitted", async ({ dashboard, mockWs }) => {
    // Do NOT touch the Review-gates section at all. Run straight away.
    await expect(dashboard.runButton()).toBeEnabled();
    await dashboard.runButton().click();

    const f = await mockWs.waitForClientFrame("run_pipeline");
    // Untouched ⇒ the field is omitted entirely (backend uses its static default).
    expect(f.gate_agent_ids).toBeUndefined();
  });

  // TS-G-04 — the section self-hides when there are zero agents (returns null).
  // We CAN reach a real 0-agent IdeaInputPage: the `custom` workflow seeds NO
  // default agents. Its agents live in the separate CUSTOM_AGENTS array, which
  // IdeaInputPage does NOT use for seeding — it seeds from
  // `LIBRARY_AGENTS.filter(a => a.pipeline_type === effectiveType)`, and no
  // LIBRARY_AGENTS row carries `pipeline_type: "custom"`. So on the custom page
  // `pipelineAgents` starts as [] → <ReviewGatesSection> receives an empty list
  // and returns null → the "Review gates" header is absent. `custom` is
  // enterprise-gated, so we navigate as an enterprise user.
  test("TS-G-04 hidden when no agents (custom workflow seeds zero agents)", async ({ dashboard }) => {
    const page = dashboard.page;

    // CONTRAST: the seeded `user_stories` page (from beforeEach) DOES show the
    // header — proving the null-render below is genuinely agent-count-driven.
    await expect(gatesHeader(page)).toBeVisible();

    // Navigate fresh to the custom IdeaInputPage as an enterprise user (full
    // page reload discards the prior user_stories state).
    await dashboard.goto({ tier: "enterprise" });
    await dashboard.selectWorkflow("Compose a custom workflow");
    // Confirm we're on the custom IdeaInputPage (its heading copy), and that it
    // truly has zero agents — the Run button reads "Add agents first".
    await expect(page.getByRole("heading", { name: "Describe the task" })).toBeVisible();
    await dashboard.fillIdea("Research the competitive landscape for AI coding assistants.");
    await expect(dashboard.runButton()).toContainText("Add agents first");

    // 0 agents → ReviewGatesSection returns null → no "Review gates" header.
    await expect(gatesHeader(page)).toHaveCount(0);
  });
});
