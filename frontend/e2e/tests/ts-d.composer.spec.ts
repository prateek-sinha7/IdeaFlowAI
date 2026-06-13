/**
 * TS-D — Agent composer (AgentsPopup + AgentLibrary). Opened from the
 * IdeaInputPage "Advanced" affordance. Drives the workflow-configuration modal:
 * tabs, role pills/locks, optional-agent removal, the add-agent cap, the Agent
 * Library, and the per-agent capabilities modal.
 *
 * Seeded via `user_stories` (CreationHub row "Generate product requirements"):
 * its 6 default agents are domain-analyst (Core/locked) → epic-architect …
 * backlog-reviewer (Required) → backlog-compiler (Core/locked). NONE are
 * optional out of the box, so optional-agent cases add one from the library
 * first (an agent from another category is "optional" relative to user_stories).
 */
import { test, expect } from "../fixtures/test";
import type { Locator } from "@playwright/test";

/** Select user_stories + type a brief so the IdeaInputPage seeds agents, then
 *  open the composer. Stays on the input view (no Run) — the popup lives there. */
async function openComposer(dashboard: import("../fixtures/dashboard").DashboardPage) {
  await dashboard.goto();
  await dashboard.selectWorkflow("Generate product requirements");
  await dashboard.fillIdea("Generate epics and stories for a refunds workflow");
  await dashboard.openAdvanced();
}

/** The open AgentsPopup panel — scoped by its heading so we never collide with
 *  the IdeaInputPage "Advanced" trigger or other page chrome. */
function popup(dashboard: import("../fixtures/dashboard").DashboardPage): Locator {
  return dashboard.page
    .locator("div")
    .filter({ has: dashboard.page.getByRole("heading", { name: "Workflow configuration" }) })
    .last();
}

/** The Agents tab button, e.g. "Agents (6)". Reads the live count off its label. */
function agentsTab(dashboard: import("../fixtures/dashboard").DashboardPage): Locator {
  return dashboard.page.getByRole("button", { name: /^Agents \(\d+\)$/ });
}

async function agentsTabCount(dashboard: import("../fixtures/dashboard").DashboardPage): Promise<number> {
  const label = await agentsTab(dashboard).textContent();
  const m = label?.match(/\((\d+)\)/);
  return m ? Number(m[1]) : NaN;
}

test.describe("TS-D — agent composer", () => {
  test("TS-D-01 open via Advanced, tabs present, close via Cancel and Save changes", async ({ dashboard }) => {
    await openComposer(dashboard);

    // Eyebrow + title (openAdvanced already asserted the title; pin the eyebrow
    // to the modal so it isn't the IdeaInputPage trigger's "Advanced" span).
    await expect(popup(dashboard).getByText("Advanced", { exact: true })).toBeVisible();
    await expect(dashboard.page.getByRole("heading", { name: "Workflow configuration" })).toBeVisible();

    // Both tabs exist.
    await expect(agentsTab(dashboard)).toBeVisible();
    await expect(dashboard.page.getByRole("button", { name: "Skills & Hooks" })).toBeVisible();

    // Close via Cancel → modal gone.
    await dashboard.page.getByRole("button", { name: "Cancel" }).click();
    await expect(dashboard.page.getByRole("heading", { name: "Workflow configuration" })).toHaveCount(0);

    // Reopen, then close via Save changes (Save ≡ Cancel — both just onClose).
    await dashboard.openAdvanced();
    await dashboard.page.getByRole("button", { name: "Save changes" }).click();
    await expect(dashboard.page.getByRole("heading", { name: "Workflow configuration" })).toHaveCount(0);
  });

  test("TS-D-02 roles & locks: Core/Required pills, optional shows a remove button", async ({ dashboard }) => {
    await openComposer(dashboard);

    // The default user_stories lineup has both locked (Core) and required cards.
    await expect(dashboard.page.getByText("Core", { exact: true }).first()).toBeVisible();
    await expect(dashboard.page.getByText("Required", { exact: true }).first()).toBeVisible();

    // No optional agents in the default seed ⇒ no remove button yet.
    await expect(dashboard.page.locator('[title="Remove agent"]')).toHaveCount(0);

    // Add one optional agent (from another category) → it gains a remove button.
    await dashboard.page.getByRole("button", { name: "Browse agent library →" }).click();
    await expect(dashboard.page.getByRole("heading", { name: "Add agent" })).toBeVisible();
    await dashboard.page.getByRole("button", { name: ".NET → Azure" }).click();
    await dashboard.page.locator('[title="Add agent"]').first().click();

    // Library closed; we're back in the popup with an optional card.
    await expect(dashboard.page.getByRole("heading", { name: "Add agent" })).toHaveCount(0);
    await expect(dashboard.page.locator('[title="Remove agent"]').first()).toBeVisible();
  });

  test("TS-D-03 remove optional agent decrements the Agents (N) tab count", async ({ dashboard }) => {
    await openComposer(dashboard);

    // Add an optional agent so there is something removable.
    await dashboard.page.getByRole("button", { name: "Browse agent library →" }).click();
    await dashboard.page.getByRole("button", { name: ".NET → Azure" }).click();
    await dashboard.page.locator('[title="Add agent"]').first().click();
    await expect(dashboard.page.getByRole("heading", { name: "Add agent" })).toHaveCount(0);

    const before = await agentsTabCount(dashboard);
    expect(before).toBeGreaterThan(6); // 6 defaults + the one we added

    // Remove the optional agent → count drops by one. (Raw textContent has no
    // space before the count span — "Agents(6)" — so match without a space.)
    await dashboard.page.locator('[title="Remove agent"]').first().click();
    await expect(agentsTab(dashboard)).toHaveText(new RegExp(`Agents\\s*\\(${before - 1}\\)`));
  });

  test("TS-D-05 add cell shows the cap and opens the Agent Library", async ({ dashboard }) => {
    await openComposer(dashboard);

    // Default user_stories has 0 optional of 5 ⇒ "+ Add agent (5 left)".
    const addCell = dashboard.page.getByRole("button", { name: /^\+ Add agent \(\d+ left\)$/ });
    await expect(addCell).toBeVisible();
    await expect(addCell).toHaveText("+ Add agent (5 left)");

    // Clicking it opens the AgentLibrary.
    await addCell.click();
    await expect(dashboard.page.getByRole("heading", { name: "Add agent" })).toBeVisible();
    await expect(dashboard.page.getByPlaceholder("Search agents...")).toBeVisible();
  });

  test("TS-D-06 Agent Library category nav, and +Add adds the agent and closes the library", async ({ dashboard }) => {
    await openComposer(dashboard);

    await dashboard.page.getByRole("button", { name: "Browse agent library →" }).click();
    await expect(dashboard.page.getByRole("heading", { name: "Add agent" })).toBeVisible();

    // Category nav — every expected pipeline label is present.
    for (const cat of [
      "All", "User Stories", "Presentation", "Prototype",
      "App Builder", "Mulesoft → Spring Boot", ".NET → Azure", "Custom",
    ]) {
      await expect(dashboard.page.getByRole("button", { name: cat, exact: true })).toBeVisible();
    }

    const countBefore = await agentsTabCount(dashboard);

    // A card's "+ Add" (title="Add agent") adds the agent AND closes the library.
    await dashboard.page.getByRole("button", { name: "App Builder", exact: true }).click();
    await dashboard.page.locator('[title="Add agent"]').first().click();

    await expect(dashboard.page.getByRole("heading", { name: "Add agent" })).toHaveCount(0);
    await expect(agentsTab(dashboard)).toHaveText(new RegExp(`Agents\\s*\\(${countBefore + 1}\\)`));
  });

  test("TS-D-08 capabilities modal shows the three sections", async ({ dashboard }) => {
    await openComposer(dashboard);

    // Open the capabilities modal from a card's Info button (View capabilities).
    // The first card is domain-analyst (Domain Discovery Agent), which has both a
    // suggested skill AND a suggested hook, so all three sections render.
    await dashboard.page.locator('[title="View capabilities"]').first().click();

    await expect(dashboard.page.getByText("What this agent does")).toBeVisible();
    await expect(dashboard.page.getByText("Suggested Skills")).toBeVisible();
    await expect(dashboard.page.getByText("Suggested Hooks")).toBeVisible();
  });

  // TS-D-04 (drag-reorder): HTML5 drag-and-drop reorder is non-deterministic to
  // assert in Playwright (dragTo rarely fires the native dragover/drop sequence
  // motion/react needs, and there is no stable post-reorder signal to assert on).
  test.fixme("TS-D-04 drag-reorder of an unlocked agent card", async ({ dashboard }) => {
    await openComposer(dashboard);
    // Intentionally unimplemented — HTML5 drag-reorder is flaky to assert.
  });
});
