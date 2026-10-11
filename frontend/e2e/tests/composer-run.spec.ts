/**
 * Composer Run-once (41-06 / CMPUI-04 · D-05 / D-CMP-RUN) — the ONE FUNCTIONAL
 * composer test. Proves the full-page Composer's "Run once" launches the COMPOSED
 * workflow through the EXISTING onStartPipeline → startPipeline seam: the outbound
 * `run_pipeline` frame carries the composed base_pipeline_type ("custom", fixed at
 * entry — ND-AH) + the composed agent ids, and the surface transitions to the
 * run/execution screen. Covers BOTH the Simple Summary-rail Run-once and (lightly)
 * the Canvas docked Run-once. Presentation/fidelity is owned by the fidelity gates
 * — this spec asserts ONLY the launch wiring (ND-AG: no fabricated cost, the run
 * routes through the real seam).
 *
 * Entry: HomeLaunchGrid's tier-independent "Create workflow" affordance
 * (onSelectFeature('custom') → mainView='composer'). The composer opens EMPTY for
 * 'custom' (the custom agents live in CUSTOM_AGENTS, outside LIBRARY_AGENTS), so
 * each case adds agents from the library (which defaults to the Custom category)
 * before running — that is what makes the composed agent ids observable on the wire.
 */
import { test, expect } from "../fixtures/test";
import type { DashboardPage } from "../fixtures/dashboard";

/** Open the full-page Composer (mainView='composer') from Home. The Simple
 *  Summary rail is the reliable "composer mounted" signal. */
async function openComposer(dashboard: DashboardPage) {
  // FIX-181 retired Home's "Create workflow" button; the composer is reached via
  // the "Compose a custom workflow" card.
  // It opens on Canvas; these flows start in the Simple view.
  await dashboard.openComposer({ view: "simple" });
}

/** Add one agent from the library (defaults to the Custom category for the custom
 *  composer). The library closes after each add, so callers re-invoke to add more. */
async function addOneAgent(dashboard: DashboardPage) {
  const page = dashboard.page;
  // The Agent-pipeline header's "Add agent" trigger (the only "Add agent" button
  // while the library is closed).
  await page.getByRole("button", { name: "Add agent" }).first().click();
  await expect(page.getByRole("heading", { name: "Add agent" })).toBeVisible();
  // A card's "+ Add" (title="Add agent") adds the agent AND closes the library.
  await page.locator('[title="Add agent"]').first().click();
  await expect(page.getByRole("heading", { name: "Add agent" })).toHaveCount(0);
}

test.describe("Composer Run-once — launch through the existing seam", () => {
  test("CR-01 Simple Run-once fires run_pipeline(custom, agent_ids) and lands on the run screen", async ({ dashboard, mockSse, page }) => {
    await openComposer(dashboard);

    // Compose a small pipeline (the composer opens empty for 'custom').
    await addOneAgent(dashboard);
    await addOneAgent(dashboard);

    // Run-once now lives in the shared ComposerPage header (SummaryRail is
    // read-only) and requires a brief of >= 3 chars before it launches.
    await page.getByRole("textbox", { name: "Brief description" }).fill("Compose a launch plan");
    await page.getByRole("button", { name: "Run once", exact: true }).click();

    // The composed run crosses the EXISTING onStartPipeline → startPipeline seam:
    // the outbound run_pipeline frame carries the composed base_pipeline_type +
    // agent ids (no new contract, no fabricated cost — ND-AG).
    const frame = await mockSse.waitForCommand("run_pipeline");
    expect(frame.pipeline_type).toBe("custom");
    expect(Array.isArray(frame.agent_ids)).toBe(true);
    expect((frame.agent_ids as string[]).length).toBe(2);
    for (const id of frame.agent_ids as unknown[]) {
      expect(typeof id).toBe("string");
      expect((id as string).length).toBeGreaterThan(0);
    }

    // The surface transitioned to the run/execution screen (startPipeline flipped
    // pipelineState.isRunning → mainView='execution'): the composer unmounts and
    // the execution chat lane mounts.
    await expect(page.getByTestId("composer-summary-rail")).toHaveCount(0);
    await expect(page.getByTestId("execution-chat-lane")).toBeVisible();
  });

  test("CR-02 Canvas docked Run-once also launches through the seam", async ({ dashboard, mockSse, page }) => {
    await openComposer(dashboard);

    // One node is enough for the Canvas launch (the composed id must reach the wire).
    await addOneAgent(dashboard);

    // Switch to the Canvas view; its docked Run summary hosts the "Run once" button.
    await page.getByRole("button", { name: "Canvas" }).click();
    await expect(page.getByTestId("canvas-view")).toBeVisible();

    // The Canvas Brief node feeds the same briefText the header Run-once reads.
    await page.getByRole("textbox", { name: "Brief description" }).fill("Compose a launch plan");
    await page.getByRole("button", { name: "Run once", exact: true }).click();

    const frame = await mockSse.waitForCommand("run_pipeline");
    expect(frame.pipeline_type).toBe("custom");
    expect(Array.isArray(frame.agent_ids)).toBe(true);
    expect((frame.agent_ids as string[]).length).toBe(1);

    // Transitioned to the run/execution screen.
    await expect(page.getByTestId("canvas-view")).toHaveCount(0);
    await expect(page.getByTestId("execution-chat-lane")).toBeVisible();
  });
});
