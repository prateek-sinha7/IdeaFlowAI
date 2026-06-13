/**
 * The mocked-mode test fixture. Import { test, expect } from here in every
 * mocked spec. Provides:
 *   - mockApi   : the REST backend stub (MockApi) — mutate mid-test if needed
 *   - mockWs    : the WS server stub (MockWs) — drive inbound events / assert outbound
 *   - dashboard : the DashboardPage page object (navigation + locators)
 *   - tier      : test-option (default 'enterprise'); set via test.use({ tier: 'basic' })
 *
 * Fixtures install BEFORE navigation, so the mocks are armed when the dashboard
 * mounts and opens its WS / hits its REST endpoints.
 */
import { test as base, expect } from "@playwright/test";
import { installMockApi, type MockApi, type Tier } from "./mockApi";
import { installMockWs, type MockWs } from "./mockWs";
import { DashboardPage } from "./dashboard";

type Fixtures = {
  mockApi: MockApi;
  mockWs: MockWs;
  dashboard: DashboardPage;
  tier: Tier;
};

export const test = base.extend<Fixtures>({
  tier: ["enterprise", { option: true }],
  // auto:true → the mocked REST + WS backend is installed for EVERY spec, even
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
  mockWs: [
    async ({ page }, provide) => {
      const ws = await installMockWs(page);
      await provide(ws);
    },
    { auto: true },
  ],
  dashboard: async ({ page, mockWs, mockApi }, provide) => {
    await provide(new DashboardPage(page, mockWs, mockApi));
  },
});

export { expect };
export type { MockApi, MockWs, Tier };
export { DashboardPage };
