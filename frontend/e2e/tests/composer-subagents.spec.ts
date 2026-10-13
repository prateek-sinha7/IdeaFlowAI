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
  // The composer opens on Canvas (ComposerPage default); these walks start from
  // the Simple view's top-level "Add agent" library trigger.
  await dashboard.openComposer({ view: "simple" });
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

/** The canvas now lays the tree out as free-positioned node cards (one
 *  `canvas-node-wrap-*` per node, children included) joined by edges; the old
 *  per-parent `canvas-children-*` column is gone. A drawn parent→child edge is
 *  the only edge with a grab path (`canvas-edge-grab`, root-chain edges have
 *  none), so exactly one grab path ⇔ exactly one nested child. */
async function expectNestedUnderParent(page: Page, childId: string) {
  await expect(page.getByTestId(`canvas-node-${childId}`)).toBeVisible();
  await expect(page.locator('[data-testid^="canvas-node-wrap-"]')).toHaveCount(2);
  await expect(page.getByTestId("canvas-edge-grab")).toHaveCount(1);
}

/** The Canvas node id of the only root agent. Custom-agent instances get a
 *  random `generateInstanceId()` id (no longer a sequential `agent-1`). */
async function soleNodeId(page: Page): Promise<string> {
  const wrap = page.locator('[data-testid^="canvas-node-wrap-"]');
  await expect(wrap).toHaveCount(1);
  const testId = await wrap.getAttribute("data-testid");
  return (testId ?? "").replace("canvas-node-wrap-", "");
}

/** Save inline from the ComposerPage header: the "Save to catalogue" dialog is
 *  gone — Save reads the header "Workflow name" field and confirms with "Saved". */
async function saveWorkflow(page: Page, name: string) {
  await page.getByRole("textbox", { name: "Workflow name" }).fill(name);
  await page.getByRole("button", { name: /^Save workflow$/ }).click();
  await expect(page.getByRole("button", { name: /Saved/ })).toBeVisible();
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

    // Nested under its parent (a parent→child edge) — not a new root node.
    await expectNestedUnderParent(page, "swot-analyst");
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
    await expectNestedUnderParent(page, "swot-analyst");

    // Save to catalogue.
    await saveWorkflow(page, "Sub-agent round trip");

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

    // The Simple view must still show the sub-agent — this is the case that used
    // to silently drop it. (The composer reopens on Canvas, its default view.)
    await page.getByRole("button", { name: "Simple", exact: true }).click();
    await expect(page.getByTestId("subagent-row-swot-analyst")).toBeVisible();

    // Canvas confirms it's still a genuine nested node, not a flattened root.
    await page.getByRole("button", { name: "Canvas" }).click();
    await expectNestedUnderParent(page, "swot-analyst");

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
    const id = await soleNodeId(page);
    await page.getByTestId(`canvas-rename-${id}`).click();
    await page.getByLabel("Rename New agent").fill("Renamed Agent");
    await page.getByLabel("Confirm rename").click();


    // Custom prompt (only a custom-agent instance gets the editable textarea).
    // The config rail reads "Click a node to configure" until a node is selected.
    await page.getByTestId(`canvas-node-${id}`).click();
    await page.getByLabel("Custom agent prompt").fill("Summarize the brief in one paragraph.");

    // Attach a skill via the shared AgentSkillsPicker (the rail's "Skills" tab).
    await page.getByRole("tab", { name: "Skills" }).click();
    // The picker is now an Add/Remove toggle list (no checkboxes).
    const picker = page.getByTestId(`agent-skills-picker-${id}`);
    await picker.getByRole("button", { name: "Add Emoji" }).click();
    await expect(picker.getByRole("button", { name: "Remove Emoji" })).toBeVisible();

    // Add a sub-agent under it.
    await addSubAgentViaCanvas(page, "Renamed Agent", "roadmap-planner");
    await expect(page.getByTestId("canvas-node-roadmap-planner")).toBeVisible();

    // Toggle to Simple and back — the tree + skill must round-trip through the
    // shared `pipelineAgents` state, not a view-local copy.
    await page.getByRole("button", { name: "Simple" }).click();
    await expect(page.getByTestId(`agent-row-${id}`)).toBeVisible();
    await expect(page.getByTestId("subagent-row-roadmap-planner")).toBeVisible();
    await page.getByRole("button", { name: "Canvas" }).click();
    await expect(page.getByTestId("canvas-node-roadmap-planner")).toBeVisible();

    // Remove the sub-agent (its own remove control, not the parent's). The
    // node card is itself role="button", so an unscoped role/name match is
    // ambiguous — the aria-label attribute selector isn't.
    await page.locator('button[aria-label="Remove Roadmap Planning Agent"]').click();
    await expect(page.getByTestId("canvas-node-roadmap-planner")).toHaveCount(0);
    await expect(page.getByTestId("canvas-edge-grab")).toHaveCount(0);

    // Save.
    await saveWorkflow(page, "Sweep workflow");

    // Reload from My Workflows and verify the rename, prompt, and skill —
    // everything that forced full-manifest persistence — survived.
    await page.getByRole("button", { name: "My Workflows" }).click();
    await expect(page.getByRole("heading", { name: "My Workflows" })).toBeVisible();
    await expect(page.locator("p", { hasText: /^Sweep workflow$/ })).toBeVisible();
    await page.getByRole("button", { name: /Run workflow/ }).click();

    // The composer reopens on Canvas (its default view); rows live in Simple.
    await page.getByRole("button", { name: "Simple", exact: true }).click();
    await expect(page.getByTestId(`agent-row-${id}`)).toContainText("Renamed Agent");
    // The removed sub-agent must STAY gone (no resurrection from a stale manifest).
    await expect(page.getByTestId("subagent-row-roadmap-planner")).toHaveCount(0);

    await page.getByRole("button", { name: "Canvas" }).click();
    await page.getByTestId(`canvas-node-${id}`).click();
    // A saved (non-empty) custom prompt opens as rendered markdown; Edit swaps in the textarea.
    await expect(page.getByTestId("agent-prompt-rendered")).toContainText(
      "Summarize the brief in one paragraph.",
    );
    await page.getByRole("button", { name: "Edit", exact: true }).click();
    await expect(page.getByLabel("Custom agent prompt")).toHaveValue(
      "Summarize the brief in one paragraph.",
    );
    await page.getByRole("tab", { name: "Skills" }).click();
    await expect(
      page.getByTestId(`agent-skills-picker-${id}`).getByRole("button", { name: "Remove Emoji" }),
    ).toBeVisible();

    expect(errors).toEqual([]);
  });
});
