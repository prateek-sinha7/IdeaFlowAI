/**
 * The mocked-mode test fixture. Import { test, expect } from here in every
 * mocked spec. Provides:
 *   - mockApi   : the REST backend stub (MockApi) — mutate mid-test if needed
 *   - mockSse   : the SSE + REST run harness (MockSse) — drive inbound events /
 *                 assert outbound REST commands (the sole transport, 44-06)
 *   - dashboard : the DashboardPage page object (navigation + locators)
 *   - tier      : test-option (default 'enterprise'); set via test.use({ tier: 'basic' })
 *
 * Fixtures install BEFORE navigation, so the mocks are armed when the dashboard
 * mounts and opens its SSE stream / hits its REST endpoints. `mockSse` lists
 * `mockApi` as a dependency so its `**​/api/runs**` route registers AFTER the
 * `**​/api/**` backend route and wins by Playwright's last-registered-first
 * precedence (anything it does not own falls back to mockApi).
 */
import { test as base, expect } from "@playwright/test";
import { installMockApi, type MockApi, type Tier } from "./mockApi";
import { installMockSse, type MockSse } from "./mockSse";
import { DashboardPage } from "./dashboard";

type Fixtures = {
  mockApi: MockApi;
  mockSse: MockSse;
  dashboard: DashboardPage;
  tier: Tier;
};

export const test = base.extend<Fixtures>({
  tier: ["enterprise", { option: true }],
  // auto:true → the mocked REST + SSE backend is installed for EVERY spec, even
  // ones that only reference `page` (e.g. the login flow). This guarantees no
  // test ever hits a real backend and removes a footgun for spec authors.
  // NOTE: the fixture-callback's 2nd arg is renamed `provide` (not the conventional
  // `use`) so eslint's react-hooks/rules-of-hooks doesn't false-flag it as a hook.
  mockApi: [
    async ({ page, tier }, provide) => {
      const api = await installMockApi(page, { user: { tier } });
      await provide(api);
    },
    { auto: true },
  ],
  mockSse: [
    async ({ page, mockApi }, provide) => {
      const sse = await installMockSse(page, mockApi);
      await provide(sse);
    },
    { auto: true },
  ],
  dashboard: async ({ page, mockSse, mockApi }, provide) => {
    await provide(new DashboardPage(page, mockSse, mockApi));
  },
});

export { expect };
export type { MockApi, MockSse, Tier };
export { DashboardPage };
export type { StubRunEventRow } from "./dashboard";
