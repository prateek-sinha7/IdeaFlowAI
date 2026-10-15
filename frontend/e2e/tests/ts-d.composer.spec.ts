/**
 * TS-D — Agent composer (AgentsPopup + AgentLibrary). Opened from the
 * IdeaInputPage "Advanced" affordance. Drives the workflow-configuration modal:
 * tabs, role locks, optional-agent removal, the add-agent cap, the Agent
 * Library, and the per-agent capabilities modal.
 *
 * Since 24332e0c the popup's Agents tab embeds the Composer's CanvasView (one
 * node card per agent) instead of the old flow-card grid, so:
 *   • roles: a Core (locked) node shows a "Core" pill; Core AND Required nodes
 *     both render their "Remove <name>" button DISABLED; only optional nodes are
 *     removable (the separate "Required" pill is gone);
 *   • the add cell "+ Add agent (N left)" became the canvas "Add agent at end" /
 *     "Insert agent before step N" buttons, disabled once the optional cap
 *     (IdeaInputPage maxOptional = 5) is reached;
 *   • drag-reorder of grid cards became the node's "Move <name> earlier/later";
 *   • Agent Library category labels come from the catalog (short_name ||
 *     display_name), e.g. app_builder → "Build an end-to-end application".
 *
 * Seeded via `user_stories` (CreationHub row "Generate product requirements"):
 * its 6 default agents are domain-analyst (Core) → epic-architect …
 * backlog-reviewer (Required) → backlog-compiler (Core). NONE are optional out
 * of the box, so optional-agent cases add one from another library category.
 */
import { test, expect } from "../fixtures/test";
import type { Locator, Page } from "@playwright/test";
import type { DashboardPage } from "../fixtures/dashboard";

const USER_STORIES_AGENTS = [
  "Domain Discovery Agent",
  "Backlog Architecture Agent",
  "Estimation Agent",
  "Quality Requirements Agent",
  "Quality Review Agent",
  "Delivery Compilation Agent",
];

/** Optional (non-user_stories) agents in the mock library, by category label. */
const APP_BUILDER = "Build an end-to-end application";
const APP_BUILDER_AGENTS = ["Architecture Agent", "API Contract Agent", "Infrastructure Agent", "DevOps Agent"];
const CUSTOM_AGENTS = ["Market Research Agent", "Strategy Analysis Agent", "Roadmap Planning Agent"];

/** Select user_stories + type a brief so the IdeaInputPage seeds agents, then
 *  open the composer. Stays on the input view (no Run) — the popup lives there. */
async function openComposer(dashboard: DashboardPage) {
  await dashboard.goto();
  await dashboard.selectWorkflow("Generate product requirements");
  await dashboard.fillIdea("Generate epics and stories for a refunds workflow");
  await dashboard.openAdvanced();
}

/** The Agents tab button, e.g. "Agents (6)". Reads the live count off its label. */
function agentsTab(dashboard: DashboardPage): Locator {
  return dashboard.page.getByRole("button", { name: /^Agents \(\d+\)$/ });
}

async function agentsTabCount(dashboard: DashboardPage): Promise<number> {
  const label = await agentsTab(dashboard).textContent();
  const m = label?.match(/\((\d+)\)/);
  return m ? Number(m[1]) : NaN;
}

function removeButton(page: Page, agentName: string): Locator {
  // The node card is itself role="button" and absorbs its descendants' names;
  // the aria-label attribute selector is unambiguous.
  return page.locator(`button[aria-label="Remove ${agentName}"]`);
}

/** Open the Agent Library, switch to `category`, and "+ Add" the named agent.
 *  The library closes after each add. */
async function addFromLibrary(page: Page, category: string, agentName: string) {
  await page.getByRole("button", { name: "Browse agent library →" }).click();
  await expect(page.getByRole("heading", { name: "Add agent" })).toBeVisible();
  await page.getByRole("button", { name: category, exact: true }).click();
  await page.locator('[data-testid^="library-card-"]', { hasText: agentName }).locator('[title="Add agent"]').click();
  await expect(page.getByRole("heading", { name: "Add agent" })).toHaveCount(0);
  await expect(removeButton(page, agentName)).toBeEnabled();
}

/** Root-level agent names in pipeline (DOM) order, read off each node's
 *  "Remove <name>" label. */
async function rootOrder(page: Page): Promise<string[]> {
  return page.evaluate(() =>
    Array.from(document.querySelectorAll('[data-testid^="canvas-node-wrap-"]'))
      .map((wrap) => wrap.querySelector('button[aria-label^="Remove "]')?.getAttribute("aria-label") ?? "")
      .map((label) => label.replace(/^Remove /, "")),
  );
}

test.describe("TS-D — agent composer", () => {
  test("TS-D-01 open via Advanced, tabs present, close via Cancel and Save changes", async ({ dashboard }) => {
    await openComposer(dashboard);

    // The folded title carries the "Advanced" eyebrow and the workflow label.
    await expect(dashboard.advancedHeading()).toHaveText(/Advanced Workflow Configuration — Generate product requirements/);

    // Both header tabs exist (scoped to the tab strip — the embedded canvas rail
    // has its own "Workflow" toggle).
    await expect(agentsTab(dashboard)).toHaveText(/Agents\s*\(6\)/);
    await expect(dashboard.advancedTab("Workflow")).toBeVisible();

    // Close via Cancel → modal gone.
    await dashboard.page.getByRole("button", { name: "Cancel" }).click();
    await expect(dashboard.advancedHeading()).toHaveCount(0);

    // Reopen — the footer carries a "Save workflow" action (opens the
    // save-to-catalogue flow rather than just closing). The popup footer's is the
    // only title-less one (the IdeaInputPage toolbar's carries a `title` tooltip).
    await dashboard.openAdvanced();
    await expect(
      dashboard.page.locator("button:not([title])", { hasText: /^Save workflow$/ }),
    ).toBeVisible();
    await dashboard.page.getByRole("button", { name: "Cancel" }).click();
    await expect(dashboard.advancedHeading()).toHaveCount(0);
  });

  test("TS-D-02 roles & locks: Core pills, Core/Required locked, optional is removable", async ({ dashboard }) => {
    const page = dashboard.page;
    await openComposer(dashboard);

    // The two Core (locked) agents carry the pill; the header legend explains it.
    await expect(page.getByText("Core = locked")).toBeVisible();
    for (const core of ["Domain Discovery Agent", "Delivery Compilation Agent"]) {
      await expect(page.locator('[data-testid^="canvas-node-"]', { has: removeButton(page, core) }).getByText("Core", { exact: true })).toBeVisible();
    }
    // Required agents carry the pill too: every non-optional role is Core (BUG-025), same predicate as the Remove lock …
    await expect(page.locator('[data-testid^="canvas-node-"]', { has: removeButton(page, "Estimation Agent") }).getByText("Core", { exact: true })).toBeVisible();
    // … and no default agent (Core or Required) can be removed.
    for (const name of USER_STORIES_AGENTS) await expect(removeButton(page, name)).toBeDisabled();

    // Add one optional agent (another category) → its Remove is enabled.
    await addFromLibrary(page, "Custom", CUSTOM_AGENTS[0]);
    await expect(removeButton(page, CUSTOM_AGENTS[0])).toBeEnabled();
  });

  test("TS-D-03 remove optional agent decrements the Agents (N) tab count", async ({ dashboard }) => {
    const page = dashboard.page;
    await openComposer(dashboard);

    await addFromLibrary(page, "Custom", CUSTOM_AGENTS[0]);
    const before = await agentsTabCount(dashboard);
    expect(before).toBe(7); // 6 defaults + the one we added

    await removeButton(page, CUSTOM_AGENTS[0]).click();
    await expect(removeButton(page, CUSTOM_AGENTS[0])).toHaveCount(0);
    // Raw textContent has no space before the count span ("Agents(6)").
    await expect(agentsTab(dashboard)).toHaveText(new RegExp(`Agents\\s*\\(${before - 1}\\)`));
  });

  test("TS-D-05 add cell opens the Agent Library and is capped at 5 optional agents", async ({ dashboard }) => {
    const page = dashboard.page;
    await openComposer(dashboard);

    const addAtEnd = page.getByRole("button", { name: "Add agent at end" });
    await expect(addAtEnd).toBeEnabled();

    // Clicking it opens the AgentLibrary.
    await addAtEnd.click();
    await expect(page.getByRole("heading", { name: "Add agent" })).toBeVisible();
    await expect(page.getByPlaceholder("Search agents...")).toBeVisible();
    // Add the 1st optional agent through the library this cell opened.
    await page.getByRole("button", { name: "Custom", exact: true }).click();
    await page.locator('[data-testid^="library-card-"]', { hasText: CUSTOM_AGENTS[0] }).locator('[title="Add agent"]').click();
    await expect(page.getByRole("heading", { name: "Add agent" })).toHaveCount(0);
    await expect(removeButton(page, CUSTOM_AGENTS[0])).toBeEnabled();

    // Fill the optional cap (maxOptional = 5 for a built-in): after the 5th add
    // every add affordance is disabled.
    const optional = [...CUSTOM_AGENTS.map((n) => ["Custom", n]), [APP_BUILDER, APP_BUILDER_AGENTS[0]], [APP_BUILDER, APP_BUILDER_AGENTS[1]]];
    for (const [category, name] of optional.slice(1, 4)) await addFromLibrary(page, category, name);
    await expect(addAtEnd).toBeEnabled();
    await addFromLibrary(page, optional[4][0], optional[4][1]);
    await expect(agentsTab(dashboard)).toHaveText(/Agents\s*\(11\)/);
    await expect(addAtEnd).toBeDisabled();
    await expect(page.getByRole("button", { name: /^Insert agent before step \d+$/ }).first()).toBeDisabled();
  });

  test("TS-D-06 Agent Library category nav, and +Add adds the agent and closes the library", async ({ dashboard }) => {
    const page = dashboard.page;
    await openComposer(dashboard);

    await page.getByRole("button", { name: "Browse agent library →" }).click();
    await expect(page.getByRole("heading", { name: "Add agent" })).toBeVisible();

    // Category nav — one entry per pipeline, labelled from the catalog
    // (short_name || display_name; ".NET → Azure" has no catalog row here).
    for (const cat of [
      "All", "Generate product requirements", "Pitch an idea", "Build an interactive prototype",
      APP_BUILDER, "Platform workflows", ".NET → Azure", "Custom",
    ]) {
      await expect(page.getByRole("button", { name: cat, exact: true })).toBeVisible();
    }

    const countBefore = await agentsTabCount(dashboard);

    // A card's "+ Add" (title="Add agent") adds the agent AND closes the library.
    await page.getByRole("button", { name: APP_BUILDER, exact: true }).click();
    await page.locator('[title="Add agent"]').first().click();

    await expect(page.getByRole("heading", { name: "Add agent" })).toHaveCount(0);
    await expect(agentsTab(dashboard)).toHaveText(new RegExp(`Agents\\s*\\(${countBefore + 1}\\)`));
  });

  test("TS-D-08 capabilities modal shows the three sections", async ({ dashboard }) => {
    await openComposer(dashboard);

    // RE-ANCHORED. The per-agent capabilities inspector (AgentCapabilitiesModal,
    // a 4-tab Overview / Skills / Hooks / Config dialog since SHELL-04) is
    // unchanged in role, but its entry point and copy moved:
    //   • 24332e0c replaced the popup's flow-card grid (and its
    //     "View capabilities & configure" Info button) with the embedded canvas;
    //     inside this popup the inspector is now opened from the Agent Library
    //     card's Info button ("View capabilities", AgentLibrary.tsx).
    //   • 08eb3833 (41-07) retitled Overview's "What this agent does" → "What it does".
    //   • 24332e0c replaced the Skills tab's "Suggested Skills" list with the
    //     shared per-agent AgentSkillsPicker ("Skills" + one row per compatible skill).
    // The mock skills/hooks libraries (fixtures/mockApi.ts) declare
    // `compatible_agents: []` (= compatible with every agent), so every agent's
    // Skills and Hooks tabs are populated.
    const page = dashboard.page;
    await page.getByRole("button", { name: "Browse agent library →" }).click();
    await expect(page.getByRole("heading", { name: "Add agent" })).toBeVisible();
    // The library opens on this workflow's own category, whose agents are all
    // already on the canvas (so hidden) — switch to "All" to reach a card.
    await page.getByRole("button", { name: "All", exact: true }).click();
    await page.getByRole("button", { name: "View capabilities", exact: true }).first().click();

    const inspector = page.getByRole("dialog", { name: / details$/ });
    await expect(inspector).toBeVisible();
    // Overview (default) — the "what it does" summary.
    await expect(inspector.getByText("What it does", { exact: true })).toBeVisible();
    // Skills tab — the agent's compatible skills, each attachable.
    await inspector.getByRole("tab", { name: "Skills" }).click();
    const skillsPanel = inspector.getByTestId(/^agent-skills-picker-/);
    await expect(skillsPanel).toBeVisible();
    await expect(skillsPanel.getByRole("button", { name: /^Add .+/ }).first()).toBeVisible();
    // Hooks tab — Suggested Hooks.
    await inspector.getByRole("tab", { name: "Hooks" }).click();
    await expect(inspector.getByText("Suggested Hooks", { exact: true })).toBeVisible();
  });

  // TS-D-04 (reorder): the canvas replaced the draggable card grid with each
  // node's "Move <name> earlier / later" controls (handleTreeChange →
  // onReorder). Moving the second optional agent earlier swaps the pair.
  test("TS-D-04 reorder of an unlocked agent", async ({ dashboard }) => {
    const page = dashboard.page;
    await openComposer(dashboard);

    const [first, second] = [APP_BUILDER_AGENTS[0], APP_BUILDER_AGENTS[1]];
    await addFromLibrary(page, APP_BUILDER, first);
    await addFromLibrary(page, APP_BUILDER, second);

    const optionalOrder = async () => (await rootOrder(page)).filter((n) => n === first || n === second);
    await expect.poll(optionalOrder).toEqual([first, second]);
    const before = await rootOrder(page);

    await page.locator(`button[aria-label="Move ${second} earlier"]`).click();

    // Same set, the two optional agents swapped; nothing added or lost.
    await expect.poll(optionalOrder).toEqual([second, first]);
    expect((await rootOrder(page)).slice().sort()).toEqual(before.slice().sort());
  });
});
