/**
 * TS-Z3 — Host capacity admission gate: the "service is busy" modal
 * (specs/014-host-capacity-monitoring §3.8).
 *
 * Proves the full frontend path for a real 503 `host_capacity_exhausted`
 * rejection: `POST /api/runs` fails → `RunConnectionProvider.sendCommand`'s
 * launch branch throws a typed `ApiError` (specs/014 §2.6.1's launch-branch
 * fix) → `lib/api.ts`'s `onCapacityRejected` pub/sub fires from inside the
 * `ApiError` constructor → `ServiceBusyProvider` renders the busy modal.
 *
 * Per the plan's own guidance, the override route is registered AFTER
 * `dashboard.goto()` (which installs the `mockSse` fixture's own
 * `**​/api/runs**` handler) — Playwright matches routes in REVERSE
 * registration order, so this test-local override wins for the launch POST
 * while every other `/api/runs*` request (GET history, etc.) still falls
 * through to the fixture's handler.
 */
import { test, expect } from "../fixtures/test";

const CAPACITY_REJECTION = {
  detail: {
    error: "The service is busy right now. Please try again in a few minutes.",
    code: "host_capacity_exhausted",
    recoverable: true,
    retry_after_seconds: 90,
    signals: [{ name: "cpu", value: 91.4, threshold: 75 }],
  },
};

test.describe("TS-Z3 — capacity admission gate busy modal", () => {
  test("TS-Z3-01 a 503 host_capacity_exhausted launch rejection shows the busy modal", async ({
    dashboard,
    page,
  }) => {
    await dashboard.goto();
    await dashboard.selectWorkflow("Generate product requirements");
    await expect(
      page.getByRole("heading", { name: /Provide the brief/i }),
    ).toBeVisible({ timeout: 15000 });
    await dashboard.fillIdea("Generate epics for a refunds workflow");

    // Registered AFTER goto() — wins over mockSse's own POST /api/runs handler
    // for this one request, per Playwright's LIFO route-matching order.
    await page.route("**/api/runs", async (route) => {
      if (route.request().method() !== "POST") return route.fallback();
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        headers: { "Retry-After": "90" },
        body: JSON.stringify(CAPACITY_REJECTION),
      });
    });

    await dashboard.runButton().click();

    // The busy modal is the RunConnectionProvider throw → onCapacityRejected →
    // ServiceBusyProvider chain — no mockSse frame is ever emitted here.
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Service is busy" }),
    ).toBeVisible();
    await expect(
      page.getByText(/service is busy right now/i),
    ).toBeVisible();
    await expect(page.getByText(/try again in about 90s/i)).toBeVisible();
    await expect(page.getByText(/CPU: 91%/)).toBeVisible();

    // Dismiss via the modal's own "Got it" affordance (Modal primitive, D-01:
    // dismissing the notice is not itself a gated action).
    await page.getByRole("button", { name: "Got it" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
  });

  test("TS-Z3-02 the launch UI recovers (no stuck 'launching' state) after the rejection", async ({
    dashboard,
    page,
  }) => {
    await dashboard.goto();
    await dashboard.selectWorkflow("Generate product requirements");
    await expect(
      page.getByRole("heading", { name: /Provide the brief/i }),
    ).toBeVisible({ timeout: 15000 });
    await dashboard.fillIdea("Generate epics for a refunds workflow");

    await page.route("**/api/runs", async (route) => {
      if (route.request().method() !== "POST") return route.fallback();
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        headers: { "Retry-After": "90" },
        body: JSON.stringify(CAPACITY_REJECTION),
      });
    });

    await dashboard.runButton().click();
    await expect(page.getByRole("dialog")).toBeVisible();

    // dashboard/page.tsx's launch .catch() clears launchPendingRef and calls
    // resetPipeline() — the Run button must be clickable again (not wedged on
    // an in-flight/disabled "launching" state) once the rejection lands.
    await expect(dashboard.runButton()).toBeEnabled();
  });
});
