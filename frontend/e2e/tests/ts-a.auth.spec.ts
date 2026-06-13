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
    await page.locator("#email").fill("qa-enterprise@flowin.test");
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
    const appBuilder = page.getByRole("button", { name: /Build an end-to-end application/i });
    await expect(appBuilder).toBeDisabled();
  });

  test("TS-A-06 enterprise tier enables every workflow", async ({ dashboard, page }) => {
    await dashboard.goto({ tier: "enterprise" });
    await expect(page.getByRole("button", { name: /Compose a custom workflow/i })).toBeEnabled();
    await expect(page.getByText(/Requires (Pro|Enterprise) plan/)).toHaveCount(0);
    // The migration row carries the NEW pill at enterprise.
    await expect(page.getByText("NEW", { exact: true })).toBeVisible();
  });
});
