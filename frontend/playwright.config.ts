import { defineConfig, devices } from "@playwright/test";

/**
 * Flowin E2E (Playwright) — TEST-REGISTER §3.
 *
 * Two projects:
 *   - "mocked"  : default. *.spec.ts (not *.live.spec.ts). No backend needed —
 *                 fixtures mock REST + WS in the browser. Fast, deterministic, CI.
 *   - "live"    : *.live.spec.ts only. Needs a real backend (:8000,
 *                 AWS_PROFILE=default) + seeded users. On demand and local only:
 *                 `npx playwright test --project=live` (or `npm run e2e:live`).
 *                 No workflow or schedule runs it; ci.yml runs `--project=mocked`
 *                 only, so the live project is not part of CI and nothing nightly
 *                 exists.
 *
 * Web server (selected by PLAYWRIGHT_WEB_SERVER, see WEB_SERVERS below):
 *   - unset / "dev" : local default. Playwright starts `npm run dev`.
 *   - "standalone"  : CI (ci.yml frontend-e2e, F-12). Serves the production
 *                     standalone bundle that the `frontend-build` job built, with
 *                     `node .next/standalone/server.js` — the same layout the
 *                     frontend/Dockerfile runner stage ships.
 *   Any other value throws when this config loads.
 *
 * Reproduce the CI server locally:
 *   1. `npm run build`
 *   2. copy `public` -> `.next/standalone/public` and
 *      `.next/static` -> `.next/standalone/.next/static`
 *   3. run with PLAYWRIGHT_WEB_SERVER=standalone, e.g. in PowerShell:
 *      `$env:PLAYWRIGHT_WEB_SERVER='standalone'; npx playwright test --project=mocked`
 *
 * The server is started fresh for the run (no reuse) and stopped cleanly after.
 */

type WebServerName = "dev" | "standalone";

interface WebServerChoice {
  command: string;
  url: string;
  env?: Record<string, string>;
}

const WEB_SERVERS: Record<WebServerName, WebServerChoice> = {
  dev: {
    command: "npm run dev",
    url: "http://localhost:3000",
  },
  standalone: {
    command: "node .next/standalone/server.js",
    url: "http://127.0.0.1:3000",
    env: { PORT: "3000", HOSTNAME: "127.0.0.1", NODE_ENV: "production" },
  },
};

function isWebServerName(value: string): value is WebServerName {
  return Object.prototype.hasOwnProperty.call(WEB_SERVERS, value);
}

const requestedWebServer = process.env.PLAYWRIGHT_WEB_SERVER ?? "dev";
if (!isWebServerName(requestedWebServer)) {
  throw new Error(
    `Unknown PLAYWRIGHT_WEB_SERVER '${requestedWebServer}'. Expected one of: ${Object.keys(WEB_SERVERS).join(", ")}.`,
  );
}
const webServer = WEB_SERVERS[requestedWebServer];

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
    // localhost either way: the mocks match `**/api/**`, independent of host.
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    // Deterministic network mocking support
    offline: false,
  },
  projects: [
    {
      name: "mocked",
      testIgnore: /\.live\.spec\.ts$/,
      use: {
        ...devices["Desktop Chrome"],
        channel: "chrome",
        // Ensure semantic locators and role-based queries
        actionTimeout: 10_000,
      },
    },
    {
      name: "live",
      testMatch: /\.live\.spec\.ts$/,
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    ...webServer,
    reuseExistingServer: false,
    timeout: 180_000,
    stdout: "ignore",
    stderr: "pipe",
  },
});
