/**
 * Composer sub-agent wiring (Spec 012 R-35) + Simple/Canvas parity + a full
 * add→rename→prompt→skill→save→reload sweep with a hard fail on any runtime
 * error.
 *
 * BACKGROUND: `AgentLibrary` already had the "+ Sub-agent" per-card action
 * (`onAddAsSubAgent`/`subAgentParentName`) and `CanvasView` already accepted
 * `onRequestAddSubAgent`, but `ComposerPage` never wired the two together —
 * clicking a node's "+ Sub-agent" button fell back to CanvasView's own
 * "mint a blank custom node" path instead of opening the library. SUB-01/02
 * pin the now-wired path.
 *
 * DATA LOSS FOUND + FIXED: `DashboardLayout`'s edit-from-My-Workflows relaunch
 * (`handleLaunchSaved`) was passing `initialManifestSteps={savedComposition
 * ?.manifestSteps}` to `IdeaInputPage` — a component that doesn't even declare
 * that prop (a TS error) and is never mounted for a saved-workflow edit
 * (`handleLaunchSaved` always sets `mainView` to `"composer"`). `ComposerPage`,
 * the component that actually reads `initialManifestSteps`, never received it
 * at all — so reopening ANY saved workflow silently fell back to the flat
 * `agent_ids` list and dropped every sub-agent, custom prompt, and per-node
 * skill it carried. SUB-03/SWEEP-01 pin the fix (now wired to ComposerPage)
 * end-to-end through a real Save → reload.
 */
import { test, expect } from "../fixtures/test";
import type { DashboardPage } from "../fixtures/dashboard";
import type { Page } from "@playwright/test";

async function openComposer(dashboard: DashboardPage) {
  await dashboard.goto();
  await dashboard.page.getByRole("button", { name: /Compose a custom workflow/ }).first().click();
  await expect(dashboard.page.getByRole("button", { name: "Canvas" })).toBeVisible();
}

/** Open the library from the top-level "Add agent" affordance and click "+ Add"
 *  on the named card (a plain, non-nested add). */
async function addFromLibrary(page: Page, agentId: string) {
  await page.getByRole("button", { name: "Add agent" }).first().click();
  await expect(page.getByRole("heading", { name: "Add agent" })).toBeVisible();
  await page.getByTestId(`library-card-${agentId}`).locator('[title="Add agent"]').click();
  await expect(page.getByRole("heading", { name: "Add agent" })).toHaveCount(0);
}

/** From Canvas, click a node's "+ Sub-agent" affordance and pick `childId`
 *  from the library's "+ Sub-agent" per-card action. */
async function addSubAgentViaCanvas(page: Page, parentName: string, childId: string) {
  // The whole node card is itself `role="button"` (click-to-select), so its
  // accessible name absorbs every descendant's text/aria-label — a plain
  // getByRole name match resolves BOTH the card and the "+ Sub-agent" button.
  // The aria-label attribute selector is unambiguous.
  await page.locator(`button[aria-label="Add sub-agent to ${parentName}"]`).click();
  await expect(page.getByRole("heading", { name: "Add agent" })).toBeVisible();
  // The header no longer offers a plain "+ Add" as the ONLY action — the
  // sub-agent action is a per-card SECOND button, present only while a parent
  // is pending.
  await page.getByTestId(`library-add-sub-${childId}`).click();
  await expect(page.getByRole("heading", { name: "Add agent" })).toHaveCount(0);
}

/** Track pageerror + console.error for the duration of a test; call at the end
 *  to assert none fired. */
function trackErrors(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (err) => errors.push(`pageerror: ${err.message}`));
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(`console.error: ${msg.text()}`);
  });
  return errors;
}

test.describe("Composer sub-agents", () => {
  test("SUB-01 canvas '+ Sub-agent' nests the picked agent under the clicked node, not the root chain", async ({ dashboard }) => {
    const page = dashboard.page;
    await openComposer(dashboard);
    await addFromLibrary(page, "market-research-agent");
    await page.getByRole("button", { name: "Canvas" }).click();

    await addSubAgentViaCanvas(page, "Market Research Agent", "swot-analyst");

    // Nested under its parent's own children column — not a new root node.
    await expect(page.getByTestId("canvas-children-market-research-agent")).toBeVisible();
    await expect(page.getByTestId("canvas-node-swot-analyst")).toBeVisible();
    await expect(page.locator('[data-testid^="canvas-node-wrap-"]')).toHaveCount(1);
  });

  test("SUB-02 Simple view renders the sub-agent read-only and indented under its parent row", async ({ dashboard }) => {
    const page = dashboard.page;
    await openComposer(dashboard);
    await addFromLibrary(page, "market-research-agent");
    await page.getByRole("button", { name: "Canvas" }).click();
    await addSubAgentViaCanvas(page, "Market Research Agent", "swot-analyst");

    await page.getByRole("button", { name: "Simple" }).click();
    await expect(page.getByTestId("agent-row-market-research-agent")).toBeVisible();
    await expect(page.getByTestId("subagent-row-swot-analyst")).toBeVisible();
  });

  test("SUB-03 Save persists the sub-agent tree and reopening the saved workflow restores it (no data loss)", async ({ dashboard }) => {
    const errors = trackErrors(dashboard.page);
    const page = dashboard.page;
    await openComposer(dashboard);
    await addFromLibrary(page, "market-research-agent");
    await page.getByRole("button", { name: "Canvas" }).click();
    await addSubAgentViaCanvas(page, "Market Research Agent", "swot-analyst");
    await expect(page.getByTestId("canvas-children-market-research-agent")).toBeVisible();

    // Save to catalogue.
    await page.getByRole("button", { name: /^Save workflow$/ }).click();
    await expect(page.getByRole("heading", { name: "Save workflow" })).toBeVisible();
    await page.getByPlaceholder(/Competitive research/i).fill("Sub-agent round trip");
    await page.getByRole("button", { name: /^Save$/ }).click();
    await expect(page.getByRole("heading", { name: "Save workflow" })).toHaveCount(0);

    // Reopen from My Workflows (edit-from-My-Workflows re-enters the composer).
    // `getByText` is ambiguous here: the composer's own <h1> title (already
    // updated to the new name by handleSave) briefly coexists with the saved
    // row's <p> during the AnimatePresence exit transition — scope to the
    // card's paragraph, and wait for the page heading first so the exit has
    // settled.
    await page.getByRole("button", { name: "My Workflows" }).click();
    await expect(page.getByRole("heading", { name: "My Workflows" })).toBeVisible();
    await expect(page.locator("p", { hasText: /^Sub-agent round trip$/ })).toBeVisible();
    await page.getByRole("button", { name: /Run workflow/ }).click();

    // Simple view (the composer's default view) must still show the sub-agent —
    // this is the case that used to silently drop it.
    await expect(page.getByTestId("subagent-row-swot-analyst")).toBeVisible();

    // Canvas confirms it's still a genuine nested node, not a flattened root.
    await page.getByRole("button", { name: "Canvas" }).click();
    await expect(page.getByTestId("canvas-children-market-research-agent")).toBeVisible();
    await expect(page.getByTestId("canvas-node-swot-analyst")).toBeVisible();
    await expect(page.locator('[data-testid^="canvas-node-wrap-"]')).toHaveCount(1);

    expect(errors).toEqual([]);
  });
});

test.describe("Composer sweep — add, rename, prompt, skill, sub-agent, remove, save, reload", () => {
  test("SWEEP-01 a full composer walk fires no page errors and round-trips through Save", async ({ dashboard }) => {
    const errors = trackErrors(dashboard.page);
    const page = dashboard.page;
    await openComposer(dashboard);

    // Add + rename a custom agent (Canvas — the inline pencil rename).
    await addFromLibrary(page, "custom-agent");
    await page.getByRole("button", { name: "Canvas" }).click();
    await page.getByTestId("canvas-rename-agent-1").click();
    await page.getByLabel("Rename New agent").fill("Renamed Agent");
    await page.getByLabel("Confirm rename").click();
    await expect(page.getByTestId("canvas-node-agent-1")).toContainText("Renamed Agent");

    // Custom prompt (only a custom-agent instance gets the editable textarea).
    await page.getByLabel("Custom agent prompt").fill("Summarize the brief in one paragraph.");

    // Attach a skill via the shared AgentSkillsPicker.
    await page.getByTestId("agent-skills-picker-agent-1").getByRole("checkbox", { name: "emoji" }).check();

    // Add a sub-agent under it.
    await addSubAgentViaCanvas(page, "Renamed Agent", "roadmap-planner");
    await expect(page.getByTestId("canvas-node-roadmap-planner")).toBeVisible();

    // Toggle to Simple and back — the tree + skill must round-trip through the
    // shared `pipelineAgents` state, not a view-local copy.
    await page.getByRole("button", { name: "Simple" }).click();
    await expect(page.getByTestId("agent-row-agent-1")).toBeVisible();
    await expect(page.getByTestId("subagent-row-roadmap-planner")).toBeVisible();
    await page.getByRole("button", { name: "Canvas" }).click();
    await expect(page.getByTestId("canvas-node-roadmap-planner")).toBeVisible();

    // Remove the sub-agent (its own remove control, not the parent's). The
    // node card is itself role="button", so an unscoped role/name match is
    // ambiguous — the aria-label attribute selector isn't.
    await page.locator('button[aria-label="Remove Roadmap Planning Agent"]').click();
    await expect(page.getByTestId("canvas-node-roadmap-planner")).toHaveCount(0);
    await expect(page.getByTestId("canvas-children-agent-1")).toHaveCount(0);

    // Save.
    await page.getByRole("button", { name: /^Save workflow$/ }).click();
    await page.getByPlaceholder(/Competitive research/i).fill("Sweep workflow");
    await page.getByRole("button", { name: /^Save$/ }).click();
    await expect(page.getByRole("heading", { name: "Save workflow" })).toHaveCount(0);

    // Reload from My Workflows and verify the rename, prompt, and skill —
    // everything that forced full-manifest persistence — survived.
    await page.getByRole("button", { name: "My Workflows" }).click();
    await expect(page.getByRole("heading", { name: "My Workflows" })).toBeVisible();
    await expect(page.locator("p", { hasText: /^Sweep workflow$/ })).toBeVisible();
    await page.getByRole("button", { name: /Run workflow/ }).click();

    await expect(page.getByTestId("agent-row-agent-1")).toContainText("Renamed Agent");
    // The removed sub-agent must STAY gone (no resurrection from a stale manifest).
    await expect(page.getByTestId("subagent-row-roadmap-planner")).toHaveCount(0);

    await page.getByRole("button", { name: "Canvas" }).click();
    await page.getByTestId("canvas-node-agent-1").click();
    await expect(page.getByLabel("Custom agent prompt")).toHaveValue(
      "Summarize the brief in one paragraph.",
    );
    await expect(
      page.getByTestId("agent-skills-picker-agent-1").getByRole("checkbox", { name: "emoji" }),
    ).toBeChecked();

    expect(errors).toEqual([]);
  });
});
