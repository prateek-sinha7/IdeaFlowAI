/**
 * The blank `custom-agent` is a TEMPLATE, reusable N times in one workflow
 * (spec 012 R-02/R-03). Each add must mint a fresh `instance_id` and compile to
 * its own `custom-agent:<instance_id>` step.
 *
 * REGRESSION THIS PINS: adding it once inserted the literal id `custom-agent`
 * into the pipeline, so (a) the Agent Library's "already added" filter hid the
 * template from then on, and (b) the add handler's own id-dedup rejected every
 * later add. One custom agent per workflow, silently.
 *
 * These drive the real UI — open the library, click Add, read the DOM — because
 * the bug lived in the click path, not in any function a unit test called.
 */
import { test, expect } from "../fixtures/test";
import type { DashboardPage } from "../fixtures/dashboard";

async function openComposer(dashboard: DashboardPage) {
  await dashboard.goto();
  await dashboard.page.getByRole("button", { name: /Compose a custom workflow/ }).first().click();
  // The Simple/Canvas segmented toggle is the composer-mounted signal.
  await expect(dashboard.page.getByRole("button", { name: "Canvas" })).toBeVisible();
}

/** Open the library, click Add on the named card, wait for the library to close. */
async function addFromLibrary(dashboard: DashboardPage, agentId: string) {
  const page = dashboard.page;
  await page.getByRole("button", { name: "Add agent" }).first().click();
  await expect(page.getByRole("heading", { name: "Add agent" })).toBeVisible();

  await page.getByTestId(`library-card-${agentId}`).locator('[title="Add agent"]').click();
  await expect(page.getByRole("heading", { name: "Add agent" })).toHaveCount(0);
}

/** How many agent rows the Simple view currently shows. */
async function rowCount(dashboard: DashboardPage): Promise<number> {
  return dashboard.page.locator('[data-testid^="agent-row-"]').count();
}

test.describe("custom-agent template is reusable N times", () => {
  test("CA-01 the template stays in the library after being added", async ({ dashboard }) => {
    const page = dashboard.page;
    await openComposer(dashboard);

    await addFromLibrary(dashboard, "custom-agent");

    // Reopen: the template must still be offered.
    await page.getByRole("button", { name: "Add agent" }).first().click();
    await expect(page.getByRole("heading", { name: "Add agent" })).toBeVisible();
    await expect(page.getByTestId("library-card-custom-agent")).toBeVisible();
  });

  test("CA-02 adding it three times yields three distinct rows", async ({ dashboard }) => {
    await openComposer(dashboard);

    await addFromLibrary(dashboard, "custom-agent");
    expect(await rowCount(dashboard)).toBe(1);

    await addFromLibrary(dashboard, "custom-agent");
    expect(await rowCount(dashboard)).toBe(2);

    await addFromLibrary(dashboard, "custom-agent");
    expect(await rowCount(dashboard)).toBe(3);
  });

  test("CA-03 a normal library agent is still de-duplicated", async ({ dashboard }) => {
    const page = dashboard.page;
    await openComposer(dashboard);

    await addFromLibrary(dashboard, "market-research-agent");
    expect(await rowCount(dashboard)).toBe(1);

    // The real agent is a single pipeline member — it must disappear from the
    // library once added. Only the blank template is exempt.
    await page.getByRole("button", { name: "Add agent" }).first().click();
    await expect(page.getByRole("heading", { name: "Add agent" })).toBeVisible();
    await expect(page.getByTestId("library-card-market-research-agent")).toHaveCount(0);
  });

  test("CA-04 each instance launches as its own step id", async ({ dashboard, mockSse, page }) => {
    await openComposer(dashboard);
    await addFromLibrary(dashboard, "custom-agent");
    await addFromLibrary(dashboard, "custom-agent");

    await page.getByRole("button", { name: "Run once now" }).click();

    const frame = await mockSse.waitForCommand("run_pipeline");
    const ids = frame.agent_ids as string[];
    expect(ids).toHaveLength(2);
    // Distinct, and never the raw template id.
    expect(new Set(ids).size).toBe(2);
    expect(ids).not.toContain("custom-agent");
  });
});
