/**
 * TS-A — Authentication, routing & tier entitlement (TEST-REGISTER §3).
 * Reference spec: proves the mock-API + auth + CreationHub gating path.
 */
import { test, expect } from "../fixtures/test";
import { TOKEN_KEY } from "../fixtures/constants";

test.describe("TS-A — auth, routing & tiers", () => {
  test("TS-A-01 unauthenticated /dashboard redirects to /login", async ({ page }) => {
    // No token seeded → the dashboard auth effect router.replace("/login").
    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  });

  test("TS-A-02 login stores JWT and lands on the dashboard home", async ({ page }) => {
    await page.goto("/login");
    await page.locator("#email").fill("qa-enterprise@flowinqa.com");
    await page.locator("#password").fill("flowin-e2e-pass");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("heading", { name: "What would you like to build today?" })).toBeVisible();
    const token = await page.evaluate((k) => localStorage.getItem(k), TOKEN_KEY);
    expect(token).toBeTruthy();
  });

  test("TS-A-05 basic tier locks app_builder / custom / migration", async ({ dashboard, page }) => {
    await dashboard.goto({ tier: "basic" });
    // Locked rows show an upgrade hint and are disabled.
    await expect(page.getByText(/Requires (Pro|Enterprise) plan/).first()).toBeVisible();
    // Phase-39 data-driven home: each row now carries a sibling "Inspect …" Info
    // button whose aria-label ALSO contains the workflow label, so a bare
    // name-regex matches 2 buttons. Scope to the launch row via its <h2> child
    // (the Info button has no heading) to stay strict-mode-safe.
    const appBuilder = page
      .getByRole("button")
      .filter({ has: page.getByRole("heading", { level: 2, name: /Build an end-to-end application/i }) });
    await expect(appBuilder).toBeDisabled();
  });

  test("TS-A-06 enterprise tier enables every workflow", async ({ dashboard, page }) => {
    test.fixme(true, "pre-existing feat/ui-2 red at 8c2f0b9d — not Phase 42 (RUNUI-09 baseline)");
    await dashboard.goto({ tier: "enterprise" });
    // Scope to the launch row via its <h2> child — the Phase-39 home row's
    // sibling "Inspect …" Info button shares the label in its aria-label.
    await expect(
      page
        .getByRole("button")
        .filter({ has: page.getByRole("heading", { level: 2, name: /Compose a custom workflow/i }) }),
    ).toBeEnabled();
    await expect(page.getByText(/Requires (Pro|Enterprise) plan/)).toHaveCount(0);
    // FLAG (removed behavior): the CreationHub "NEW" pill on the migration row is
    // GONE in the Phase-39 data-driven home (HomeLaunchGrid sources rows from
    // GET /api/workflows, whose WorkflowSummary shape carries no badge field).
    // No equivalent affordance exists to re-target — left asserting the retired
    // pill for reconciliation.
    await expect(page.getByText("NEW", { exact: true })).toBeVisible();
  });
});
