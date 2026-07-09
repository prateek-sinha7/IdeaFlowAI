/**
 * TS-B — Workflow selection / CreationHub (TEST-REGISTER §3).
 * Proves the 6 CreationHub rows route correctly: four open the in-page
 * IdeaInputPage (assert its <h1> heading per TYPE_CONFIG), while prototype/ppt
 * HARD-NAVIGATE via router.push to their template wizards (assert the URL).
 *
 * All rows are exercised at the `enterprise` tier so every workflow is enabled
 * (see entitlements.ts: only enterprise unlocks custom + migration).
 */
import { test, expect } from "../fixtures/test";

test.describe("TS-B — workflow selection", () => {
  test.beforeEach(async ({ dashboard }) => {
    // enterprise → every row enabled (custom/migration require enterprise).
    await dashboard.goto({ tier: "enterprise" });
  });

  test("TS-B-01 'Generate product requirements' opens the brief input view", async ({ dashboard, page }) => {
    await dashboard.selectWorkflow("Generate product requirements");
    // IdeaInputPage heading for user_stories (TYPE_CONFIG.user_stories.heading).
    await expect(page.getByRole("heading", { name: "Provide the brief" })).toBeVisible();
  });

  test("TS-B-02 'Pitch an idea' hard-navigates to the PPT template wizard", async ({ dashboard, page }) => {
    // ppt routes via router.push("/workflow/create?mode=ppt") — NOT an input view.
    await dashboard.selectWorkflow("Pitch an idea");
    await page.waitForURL(/\/workflow\/create\?mode=ppt/);
  });

  test("TS-B-03 'Build an interactive prototype' hard-navigates to the prototype template wizard", async ({ dashboard, page }) => {
    // prototype routes via router.push("/workflow/create?mode=prototype") — NOT an input view.
    await dashboard.selectWorkflow("Build an interactive prototype");
    await page.waitForURL(/\/workflow\/create\?mode=prototype/);
  });

  test("TS-B-04 'Build an end-to-end application' opens the application input view", async ({ dashboard, page }) => {
    await dashboard.selectWorkflow("Build an end-to-end application");
    // IdeaInputPage heading for app_builder (TYPE_CONFIG.app_builder.heading).
    await expect(page.getByRole("heading", { name: "Describe the application" })).toBeVisible();
  });

  test("TS-B-05 'Platform workflows' opens the migration input view with two path tiles", async ({ dashboard, page }) => {
    // The migration row carries the NEW pill on the (enterprise) home screen.
    await expect(page.getByText("NEW", { exact: true })).toBeVisible();

    await dashboard.selectWorkflow("Platform workflows");

    // IdeaInputPage heading for the migration meta-pipeline.
    await expect(page.getByRole("heading", { name: "Modernise a legacy estate" })).toBeVisible();

    // The migration sub-pipeline selector renders exactly two tiles (MIGRATION_OPTIONS).
    await expect(page.getByText("Choose your migration path")).toBeVisible();
    await expect(page.getByRole("button", { name: /Mulesoft → Spring Boot microservices on AWS/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /\.NET → Azure \(AI-augmented\)/i })).toBeVisible();
  });

  test("TS-B-06 'Compose a custom workflow' opens the custom task input view", async ({ dashboard, page }) => {
    await dashboard.selectWorkflow("Compose a custom workflow");
    // IdeaInputPage heading for custom (TYPE_CONFIG.custom.heading).
    await expect(page.getByRole("heading", { name: "Describe the task" })).toBeVisible();
  });

  test("TS-B-07 workflow rows are focusable, enabled buttons (hover affordance proxy)", async ({ page }) => {
    // The hover highlight is a CSS-only affordance that can't be asserted
    // deterministically; instead assert the row is a real enabled, focusable
    // <button> the user can activate.
    const row = page.getByRole("button", { name: /Generate product requirements/i });
    await expect(row).toBeEnabled();
    await row.focus();
    await expect(row).toBeFocused();
  });
});
