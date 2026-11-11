/**
 * TS-CN — Connectors: the browser journeys (design section 4.3 and section 9).
 *
 * Mocked spec. `/api/connectors` and the provider's consent screen come from
 * `fixtures/connectorsMocks.ts` (no backend, no real provider); the shell comes
 * from the standard `mockApi` fixture.
 *
 *   01 the list shows each connector with its status, account and permissions
 *   02 connect through a popup: waiting state, status polling, connected banner
 *   03 cancel while waiting closes the popup and leaves the connector unchanged
 *   04 a blocked popup offers "Continue in this tab", which round-trips through the landing page
 *   05 disconnect: confirm dialog, provider revoke result, card back to "Not connected"
 *   06 disconnect: cancelling the dialog and a failed request both leave the connection alone
 *   07 not configured: the card says so and Connect is disabled
 *   08 expired: the card asks for a reconnect and the reconnect completes
 *   09 the landing page forwards an error to the page in a normal tab and rejects a bad link
 *   10 the header navigation opens the page
 *
 * Cards are found by role and name (`article` named by the connector heading).
 */
import { test, expect } from "../fixtures/test";
import type { Page } from "@playwright/test";
import { TEST_JWT, TOKEN_KEY } from "../fixtures/constants";
import {
  connectedJira,
  githubConnector,
  installConnectorsMocks,
  jiraConnector,
} from "../fixtures/connectorsMocks";

/** Seed the auth token and open the Connectors page. */
async function openConnectors(page: Page, path = "/connectors") {
  await page.addInitScript(([k, t]) => localStorage.setItem(k, t), [TOKEN_KEY, TEST_JWT]);
  await page.goto(path);
  await expect(page.getByRole("heading", { level: 1, name: "Connectors" })).toBeVisible({
    timeout: 15_000,
  });
}

function cardOf(page: Page, name: string) {
  return page.getByRole("article", { name });
}

test.describe("TS-CN — Connectors journeys", () => {
  // A cold `next dev` compiles each route on first use and the workers share one server,
  // so the first page load can take 30 s or more. The default 45 s budget is too tight.
  test.beforeEach(() => {
    test.setTimeout(120_000);
  });

  test("TS-CN-01 the list shows status, account and permissions per connector", async ({ page }) => {
    await installConnectorsMocks(page, { connectors: [connectedJira(), githubConnector()] });
    await openConnectors(page);

    const jira = cardOf(page, "Jira");
    await expect(jira).toBeVisible();
    await expect(jira.getByText("Connected", { exact: true }).first()).toBeVisible();
    await expect(jira.getByText("Connected as Jane Doe (jane)")).toBeVisible();
    await expect(jira.getByText("Acme Cloud")).toBeVisible();
    await expect(jira.getByText("write:jira-work")).toBeVisible();
    await expect(jira.getByRole("button", { name: "Disconnect Jira" })).toBeEnabled();
    const docs = jira.getByRole("link", { name: "Jira documentation (opens in a new tab)" });
    await expect(docs).toHaveAttribute("rel", "noopener noreferrer");

    const github = cardOf(page, "GitHub");
    await expect(github.getByText("Not connected", { exact: true })).toBeVisible();
    await expect(github.getByText("Permissions requested")).toBeVisible();
    await expect(github.getByRole("button", { name: "Connect GitHub" })).toBeEnabled();
  });

  test("TS-CN-02 connect through a popup: waiting, polling, then connected", async ({ page }) => {
    const connectors = await installConnectorsMocks(page, {
      connectors: [jiraConnector(), githubConnector()],
    });
    await openConnectors(page);
    // The provider keeps the user on its consent screen until released.
    connectors.holdProvider();

    const jira = cardOf(page, "Jira");
    const [popup] = await Promise.all([
      page.waitForEvent("popup"),
      jira.getByRole("button", { name: "Connect Jira" }).click(),
    ]);

    await expect(
      jira.getByText("Waiting for you to finish signing in to Jira in the pop-up window."),
    ).toBeVisible();
    await expect(jira.getByRole("button", { name: "Cancel sign-in to Jira" })).toBeVisible();
    await expect.poll(() => connectors.idpVisits()).toBe(1);
    expect(connectors.requests).toContainEqual({ method: "POST", path: "/api/connectors/jira/authorize" });

    // The user approves; the page finds out by polling the list (and the landing page's message).
    connectors.releaseProvider();
    await expect(jira.getByText("Connected as Jane Doe (jane)")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("status").filter({ hasText: "Jira is connected." })).toBeVisible();
    await expect(jira.getByRole("button", { name: "Disconnect Jira" })).toBeEnabled();
    await expect.poll(() => popup.isClosed()).toBe(true);
  });

  test("TS-CN-03 cancelling while waiting closes the popup and keeps the connector unchanged", async ({
    page,
  }) => {
    const connectors = await installConnectorsMocks(page);
    await openConnectors(page);
    connectors.holdProvider();

    const jira = cardOf(page, "Jira");
    const [popup] = await Promise.all([
      page.waitForEvent("popup"),
      jira.getByRole("button", { name: "Connect Jira" }).click(),
    ]);
    await jira.getByRole("button", { name: "Cancel sign-in to Jira" }).click();

    await expect(page.getByText("Sign-in to Jira was cancelled.")).toBeVisible();
    await expect(jira.getByText("Not connected", { exact: true })).toBeVisible();
    await expect(jira.getByRole("button", { name: "Connect Jira" })).toBeEnabled();
    await expect.poll(() => popup.isClosed()).toBe(true);
    connectors.releaseProvider();
  });

  test("TS-CN-04 a blocked popup offers Continue in this tab and finishes on return", async ({ page }) => {
    const connectors = await installConnectorsMocks(page);
    // A browser that refuses every window.open.
    await page.addInitScript(() => {
      window.open = () => null;
    });
    await openConnectors(page);

    await cardOf(page, "Jira").getByRole("button", { name: "Connect Jira" }).click();
    await expect(page.getByText("Your browser blocked the sign-in window.")).toBeVisible();
    expect(connectors.idpVisits()).toBe(0);

    // Same tab: provider, then the landing page, then back on /connectors with the hint removed.
    // The click starts a cross-origin navigation chain; do not make the click wait for it.
    await page.getByRole("button", { name: "Continue in this tab" }).click({ noWaitAfter: true });
    await expect(page.getByText("Jira is connected.")).toBeVisible({ timeout: 30_000 });
    await expect(page).toHaveURL(/\/connectors$/);
    await expect(cardOf(page, "Jira").getByText("Connected as Jane Doe (jane)")).toBeVisible();
    expect(connectors.idpVisits()).toBe(1);
  });

  test("TS-CN-05 disconnect asks first, reports the provider revoke, and the card resets", async ({
    page,
  }) => {
    const connectors = await installConnectorsMocks(page, {
      connectors: [connectedJira(), githubConnector()],
      providerRevocation: "revoked",
    });
    await openConnectors(page);

    const jira = cardOf(page, "Jira");
    await jira.getByRole("button", { name: "Disconnect Jira" }).click();
    const dialog = page.getByRole("dialog", { name: "Disconnect Jira?" });
    await expect(dialog).toContainText("ask Jira to revoke the access it granted");
    expect(connectors.requests.some((r) => r.method === "DELETE")).toBe(false);

    await dialog.getByRole("button", { name: "Disconnect", exact: true }).click();
    await expect(
      dialog.getByText("Jira is disconnected, and its access grant was revoked at the provider."),
    ).toBeVisible();
    expect(connectors.requests).toContainEqual({ method: "DELETE", path: "/api/connectors/jira" });

    await dialog.getByRole("button", { name: "Close" }).click();
    await expect(dialog).toBeHidden();
    await expect(jira.getByText("Not connected", { exact: true })).toBeVisible();
    await expect(jira.getByRole("button", { name: "Connect Jira" })).toBeEnabled();
    await expect(jira.getByText("Connected as Jane Doe (jane)")).toHaveCount(0);
  });

  test("TS-CN-06 cancelling the dialog or a failed request keeps the connection", async ({ page }) => {
    const connectors = await installConnectorsMocks(page, {
      connectors: [connectedJira(), githubConnector()],
      failNextDisconnect: true,
    });
    await openConnectors(page);

    const jira = cardOf(page, "Jira");
    await jira.getByRole("button", { name: "Disconnect Jira" }).click();
    const dialog = page.getByRole("dialog", { name: "Disconnect Jira?" });
    await dialog.getByRole("button", { name: "Cancel" }).click();
    await expect(dialog).toBeHidden();
    expect(connectors.requests.some((r) => r.method === "DELETE")).toBe(false);

    // The first request fails: the dialog stays open with an alert and nothing changed.
    await jira.getByRole("button", { name: "Disconnect Jira" }).click();
    await dialog.getByRole("button", { name: "Disconnect", exact: true }).click();
    await expect(dialog.getByRole("alert")).toContainText("Could not disconnect Jira. Try again.");
    await expect(jira.getByText("Connected as Jane Doe (jane)")).toBeVisible();

    // Trying again works.
    await dialog.getByRole("button", { name: "Disconnect", exact: true }).click();
    await expect(dialog.getByRole("button", { name: "Close" })).toBeVisible();
    await dialog.getByRole("button", { name: "Close" }).click();
    await expect(jira.getByText("Not connected", { exact: true })).toBeVisible();
  });

  test("TS-CN-07 a connector the server has no credentials for shows Not configured", async ({ page }) => {
    const connectors = await installConnectorsMocks(page, {
      connectors: [jiraConnector(), githubConnector({ status: "not_configured" })],
    });
    await openConnectors(page);

    const github = cardOf(page, "GitHub");
    await expect(github.getByText("Not configured", { exact: true })).toBeVisible();
    await expect(github.getByText("GitHub is not configured on this server.")).toBeVisible();
    await expect(github.getByRole("button", { name: "Connect GitHub" })).toBeDisabled();
    await expect(github.getByRole("button", { name: /Disconnect|Reconnect/ })).toHaveCount(0);
    // The other connector is unaffected.
    await expect(cardOf(page, "Jira").getByRole("button", { name: "Connect Jira" })).toBeEnabled();
    expect(connectors.requests.some((r) => r.method === "POST")).toBe(false);
  });

  test("TS-CN-08 an expired connection asks for a reconnect, and the reconnect completes", async ({
    page,
  }) => {
    const connectors = await installConnectorsMocks(page, {
      connectors: [
        connectedJira({ status: "expired", connected_at: "2026-02-01T08:00:00Z" }),
        githubConnector(),
      ],
    });
    await openConnectors(page);

    const jira = cardOf(page, "Jira");
    await expect(jira.getByText("Expired", { exact: true })).toBeVisible();
    await expect(
      jira.getByText("Your Jira connection expired. Reconnect to keep using its tools."),
    ).toBeVisible();
    await expect(jira.getByRole("button", { name: "Disconnect Jira" })).toBeEnabled();

    const [popup] = await Promise.all([
      page.waitForEvent("popup"),
      jira.getByRole("button", { name: "Reconnect Jira" }).click(),
    ]);
    await expect(jira.getByText("Connected as Jane Doe (jane)")).toBeVisible({ timeout: 15_000 });
    await expect(jira.getByText("Expired", { exact: true })).toHaveCount(0);
    await expect.poll(() => popup.isClosed()).toBe(true);
    expect(connectors.requests).toContainEqual({ method: "POST", path: "/api/connectors/jira/authorize" });
  });

  test("TS-CN-09 the landing page forwards an error to the page and rejects a bad link", async ({
    page,
  }) => {
    const connectors = await installConnectorsMocks(page);

    // A refused consent comes back to a normal tab: the page shows it, then clears the address.
    await page.addInitScript(([k, t]) => localStorage.setItem(k, t), [TOKEN_KEY, TEST_JWT]);
    await page.goto("/connectors/oauth-complete?connector=jira&result=error&reason=access_denied");
    await expect(page.getByText("Access was declined, so nothing was connected.")).toBeVisible({
      timeout: 15_000,
    });
    await page.waitForURL((url) => url.pathname === "/connectors" && url.search === "");
    await expect(cardOf(page, "Jira").getByText("Not connected", { exact: true })).toBeVisible();

    // A success hint is not believed until the server list agrees.
    await page.goto("/connectors/oauth-complete?connector=jira&result=connected");
    await expect(cardOf(page, "Jira")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("Jira is connected.")).toHaveCount(0);

    // A link that does not parse is shown as invalid and goes nowhere.
    await page.goto("/connectors/oauth-complete?connector=NOT%20A%20KEY&result=connected");
    await expect(page.getByText("This link is not valid")).toBeVisible();
    expect(new URL(page.url()).pathname).toBe("/connectors/oauth-complete");
    expect(connectors.requests.some((r) => r.method !== "GET")).toBe(false);
  });

  test("TS-CN-10 the account menu opens the Connectors page", async ({ dashboard, page }) => {
    await installConnectorsMocks(page, { connectors: [connectedJira(), githubConnector()] });
    await dashboard.goto();

    await page.getByRole("button", { name: "Account menu" }).click();
    await page.getByRole("menuitem", { name: "Connectors" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Connectors" })).toBeVisible();
    await expect(page).toHaveURL(/\/connectors$/);
    await expect(cardOf(page, "Jira")).toBeVisible();
  });
});
