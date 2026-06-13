import { defineConfig, devices } from "@playwright/test";

/**
 * Flowin E2E (Playwright) — TEST-REGISTER §3.
 *
 * Two projects:
 *   - "mocked"  : default. *.spec.ts (not *.live.spec.ts). No backend needed —
 *                 fixtures mock REST + WS in the browser. Fast, deterministic, CI.
 *   - "live"    : *.live.spec.ts only. Needs a real backend (:8000,
 *                 AWS_PROFILE=default) + seeded users. Run nightly / on demand:
 *                 `npx playwright test --project=live`.
 *
 * The Next dev server is auto-started (reused if already running).
 */
export default defineConfig({
  testDir: "./e2e/tests",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 4 : undefined,
  reporter: [["list"], ["html", { outputFolder: "e2e/.report", open: "never" }]],
  timeout: 45_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "mocked",
      testIgnore: /\.live\.spec\.ts$/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "live",
      testMatch: /\.live\.spec\.ts$/,
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: true,
    timeout: 180_000,
    stdout: "ignore",
    stderr: "pipe",
  },
});
