/**
 * Live-mode harness. Import { liveTest, expect } from here in *.live.spec.ts.
 * Requires a REAL backend (:8000, AWS_PROFILE=default for Bedrock) + a seeded
 * user (backend/scripts/seed_test_users.py). NO mocks — exercises real Bedrock.
 *
 * Creds come from env (falling back to the seed-script defaults):
 *   E2E_BASE_PASSWORD (default "flowin-e2e-pass")
 *   E2E_<TIER>_EMAIL  (default qa-<tier>@flowinqa.com)
 */
import { test as base, expect, type Page } from "@playwright/test";
import { TOKEN_KEY } from "./constants";

const API = process.env.E2E_API_URL || "http://localhost:8000";
const PASSWORD = process.env.E2E_BASE_PASSWORD || "flowin-e2e-pass";

function emailFor(tier: "basic" | "pro" | "enterprise") {
  return process.env[`E2E_${tier.toUpperCase()}_EMAIL`] || `qa-${tier}@flowinqa.com`;
}

export async function loginLive(page: Page, tier: "basic" | "pro" | "enterprise" = "enterprise") {
  const res = await page.request.post(`${API}/api/auth/login`, {
    data: { email: emailFor(tier), password: PASSWORD },
  });
  if (!res.ok()) throw new Error(`Live login failed (${res.status()}) for ${emailFor(tier)} — is the backend up and the user seeded?`);
  const { token } = (await res.json()) as { token: string };
  await page.addInitScript(([k, t]) => localStorage.setItem(k, t), [TOKEN_KEY, token]);
  return token;
}

type LiveFixtures = { authedPage: Page; tier: "basic" | "pro" | "enterprise" };

export const liveTest = base.extend<LiveFixtures>({
  tier: ["enterprise", { option: true }],
  // `provide` (not `use`) avoids eslint react-hooks/rules-of-hooks false-positive.
  authedPage: async ({ page, tier }, provide) => {
    await loginLive(page, tier);
    await page.goto("/dashboard");
    await expect(page.getByRole("heading", { name: "What would you like to build today?" })).toBeVisible({ timeout: 20000 });
    await provide(page);
  },
});

export { expect };
