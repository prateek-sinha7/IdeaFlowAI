/**
 * TS-CA — Connected apps on the Canvas Tools tab (design sections 4.4, 4.5 and 7.4).
 *
 * Mocked spec. `/api/connectors` comes from `fixtures/connectorsMocks.ts`; the
 * tool list of a connector and the 422 refusal are spec-local routes; the shell,
 * the agent library and the saved-workflow store come from the standard `mockApi`
 * fixture. No backend and no real provider.
 *
 *   01 the Tools tab lists each connected app with its state; tools start off
 *   02 a Jira tool switched on is saved as the step's `tools.connectors`, and is
 *      still on after reopening the saved workflow and after a reload
 *   03 an app that is not connected or not configured offers no switch, only a link
 *   04 an expired app asks for a reconnect and offers no switch
 *   05 a 422 refusal shows the server's `detail.error` text, not the raw JSON
 *   06 a built-in (predefined) canvas shows the save-a-copy note and cannot switch tools on
 *
 * The composer hosts the AI builder, so every test installs the workflow-builder mock
 * (without it GET /api/workflow-builder/models answers `{}` and the page shows its error screen).
 *
 * Controls are found by role and name: the section is the region "Connected apps",
 * each app a group named after it, each tool a switch named after its title.
 */
import { test, expect } from "../fixtures/test";
import type { DashboardPage } from "../fixtures/dashboard";
import type { Page } from "@playwright/test";
import { TEST_JWT, TOKEN_KEY } from "../fixtures/constants";
import {
  connectedJira,
  githubConnector,
  installConnectorsMocks,
  jiraConnector,
} from "../fixtures/connectorsMocks";
import { installWorkflowBuilderMocks } from "../fixtures/workflowBuilderMocks";

const AGENT_ID = "market-research-agent";
const SEARCH = "jira__search_issues";
const CREATE = "jira__create_issue";

const NOT_AVAILABLE_NOTE = "Connected apps work in your own workflows. Save a copy to use them.";

/** The wire shape of GET /api/connectors/{key}/tools (restated on purpose, as in connectorsMocks.ts). */
const JIRA_TOOLS = [
  {
    name: SEARCH,
    source_name: "search_issues",
    title: "Search issues",
    description: "Find issues with a JQL query.",
    write_capable: false,
  },
  {
    name: CREATE,
    source_name: "create_issue",
    title: "Create issue",
    description: "Create a new issue in a project.",
    write_capable: true,
  },
];

/** Answer GET /api/connectors/jira/tools with the two tools above. Registered after
 *  `installConnectorsMocks`, so it wins over that mock's empty tool list. */
async function installJiraTools(page: Page) {
  await page.route(/\/api\/connectors\/jira\/tools(\?|$)/, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      headers: { "cache-control": "no-store" },
      body: JSON.stringify({
        connector: "jira",
        status: "connected",
        tools: JIRA_TOOLS,
        listed_at: "2026-03-01T09:30:00Z",
      }),
    }),
  );
}

/** Open the composer on its Canvas, add the Market Research agent, and open its Tools tab. */
async function openToolsTab(dashboard: DashboardPage) {
  const page = dashboard.page;
  await dashboard.openComposer();
  await page.getByRole("button", { name: "Add agent at end" }).click();
  await expect(page.getByRole("heading", { name: "Add agent" })).toBeVisible();
  await page.getByTestId(`library-card-${AGENT_ID}`).locator('[title="Add agent"]').click();
  await expect(page.getByRole("heading", { name: "Add agent" })).toHaveCount(0);
  await selectNodeToolsTab(page);
}

/** Select the agent's node and open the rail's Tools tab. */
async function selectNodeToolsTab(page: Page, agentId = AGENT_ID) {
  await page.getByTestId(`canvas-node-${agentId}`).click();
  await page.getByRole("tab", { name: "Tools" }).click();
}

function connectedApps(page: Page) {
  return page.getByRole("region", { name: "Connected apps" });
}

/** Expand an app's tool list (the disclosure button is named "Show {app} tools"). */
async function expandApp(page: Page, app: string) {
  const group = connectedApps(page).getByRole("group", { name: new RegExp(app) });
  await group.getByRole("button", { name: `Show ${app} tools` }).click();
  await expect(group.getByRole("button", { name: `Hide ${app} tools` })).toHaveAttribute("aria-expanded", "true");
  return group;
}

/** Name the workflow in the header field and press Save workflow. */
async function saveWorkflow(page: Page, name: string) {
  await page.getByRole("textbox", { name: "Workflow name" }).fill(name);
  await page.getByRole("button", { name: /^Save workflow$/ }).click();
}

test.describe("TS-CA — connected apps on the Canvas", () => {
  // A cold `next dev` compiles each route on first use and the workers share one server,
  // so the first page load can take 30 s or more. The default 45 s budget is too tight.
  test.beforeEach(async ({ page }) => {
    test.setTimeout(120_000);
    // The composer hosts the AI builder, which loads GET /api/workflow-builder/models on mount;
    // the base mock answers it with `{}` and the page crashes. This fixture serves the model list.
    await installWorkflowBuilderMocks(page);
  });

  test("TS-CA-01 the Tools tab lists each connected app, and every tool starts off", async ({ dashboard, page }) => {
    const connectors = await installConnectorsMocks(page, {
      connectors: [connectedJira(), githubConnector()],
    });
    await installJiraTools(page);
    await openToolsTab(dashboard);

    const section = connectedApps(page);
    await expect(section.getByRole("heading", { name: "Connected apps" })).toBeVisible();
    const jira = section.getByRole("group", { name: /Jira/ });
    await expect(jira).toBeVisible();
    await expect(jira.getByText("0 on")).toBeVisible();
    const github = section.getByRole("group", { name: /GitHub/ });
    await expect(github.getByText("GitHub is not connected.")).toBeVisible();
    // Connected apps are for the user's own workflow: no save-a-copy note here.
    await expect(page.getByText(NOT_AVAILABLE_NOTE)).toHaveCount(0);

    await expandApp(page, "Jira");
    await expect(jira.getByText("0 of 2 on")).toBeVisible();
    await expect(jira.getByRole("switch", { name: "Search issues" })).toHaveAttribute("aria-checked", "false");
    await expect(jira.getByRole("switch", { name: "Create issue" })).toHaveAttribute("aria-checked", "false");
    // The tool that can change data says so in text, not only by colour.
    await expect(jira.getByText("Can change data")).toHaveCount(1);
    await expect(jira.getByText("Find issues with a JQL query.")).toBeVisible();

    expect(connectors.requests).toContainEqual({ method: "GET", path: "/api/connectors" });
    expect(connectors.requests.some((r) => r.method !== "GET")).toBe(false);
  });

  test("TS-CA-02 a Jira tool switched on is saved and is still on after reopening and a reload", async ({
    dashboard,
    page,
    mockApi,
  }) => {
    await installConnectorsMocks(page, { connectors: [connectedJira(), githubConnector()] });
    await installJiraTools(page);
    await openToolsTab(dashboard);

    const jira = await expandApp(page, "Jira");
    await jira.getByRole("switch", { name: "Search issues" }).click();
    await expect(jira.getByRole("switch", { name: "Search issues" })).toHaveAttribute("aria-checked", "true");
    await expect(jira.getByRole("switch", { name: "Create issue" })).toHaveAttribute("aria-checked", "false");
    await expect(jira.getByText("1 of 2 on")).toBeVisible();

    // Save: a grant is refused on the flat `selections` map, so the create request
    // sends the full `manifest`, and the step's `tools.connectors` carries the grant.
    const created = page.waitForRequest(
      (r) => r.method() === "POST" && new URL(r.url()).pathname === "/api/user-workflows",
    );
    await saveWorkflow(page, "Jira round trip");
    const body = (await created).postDataJSON() as {
      selections?: Record<string, unknown> | null;
      manifest?: { steps?: Array<{ agent?: string; tools?: { connectors?: string[] } }> };
    };
    expect(body.selections).toBeUndefined();
    expect(body.manifest?.steps?.find((step) => step.agent === AGENT_ID)?.tools?.connectors).toEqual([SEARCH]);
    await expect(page.getByRole("button", { name: /Saved/ })).toBeVisible();
    expect(mockApi.userWorkflows).toHaveLength(1);

    // Reopen from My Workflows: the choice came back from the stored row.
    await page.getByRole("button", { name: "My Workflows" }).click();
    await expect(page.getByRole("heading", { name: "My Workflows" })).toBeVisible();
    await expect(page.locator("p", { hasText: /^Jira round trip$/ })).toBeVisible();
    await page.getByRole("button", { name: /Run workflow/ }).click();
    await page.waitForURL(/\/workflows\/[^/]+\/run$/);
    await selectNodeToolsTab(page);
    let reopened = await expandApp(page, "Jira");
    await expect(reopened.getByRole("switch", { name: "Search issues" })).toHaveAttribute("aria-checked", "true");
    await expect(reopened.getByRole("switch", { name: "Create issue" })).toHaveAttribute("aria-checked", "false");

    // A full reload rebuilds the page from the stored row alone.
    await page.reload();
    await selectNodeToolsTab(page);
    reopened = await expandApp(page, "Jira");
    await expect(reopened.getByRole("switch", { name: "Search issues" })).toHaveAttribute("aria-checked", "true");
    await expect(reopened.getByRole("switch", { name: "Create issue" })).toHaveAttribute("aria-checked", "false");
  });

  test("TS-CA-03 an app that is not connected or not configured offers no switch", async ({
    dashboard,
    page,
  }) => {
    await installConnectorsMocks(page, {
      connectors: [jiraConnector(), githubConnector({ status: "not_configured" })],
    });
    await openToolsTab(dashboard);

    const section = connectedApps(page);
    const jira = section.getByRole("group", { name: /Jira/ });
    await expect(jira.getByText("Jira is not connected.")).toBeVisible();
    const connect = jira.getByRole("link", { name: "Connect in Connectors" });
    await expect(connect).toHaveAttribute("href", "/connectors?connector=jira");
    await expect(connect).toHaveAttribute("target", "_blank");
    await expect(connect).toHaveAttribute("rel", "noopener noreferrer");

    const github = section.getByRole("group", { name: /GitHub/ });
    await expect(github.getByText("Not configured on this server")).toBeVisible();
    await expect(github.getByRole("link")).toHaveCount(0);

    await expect(section.getByRole("switch")).toHaveCount(0);
    await expect(section.getByRole("button", { name: /^Show / })).toHaveCount(0);
  });

  test("TS-CA-04 an expired app asks for a reconnect and offers no switch", async ({ dashboard, page }) => {
    await installConnectorsMocks(page, {
      connectors: [connectedJira({ status: "expired" }), githubConnector()],
    });
    await openToolsTab(dashboard);

    const jira = connectedApps(page).getByRole("group", { name: /Jira/ });
    await expect(jira.getByText("Your Jira connection expired.")).toBeVisible();
    await expect(jira.getByRole("link", { name: "Reconnect in Connectors" })).toHaveAttribute(
      "href",
      "/connectors?connector=jira",
    );
    await expect(jira.getByRole("switch")).toHaveCount(0);
  });

  test("TS-CA-05 a 422 refusal shows the server's text, not the raw JSON", async ({ dashboard, page }) => {
    await installConnectorsMocks(page, { connectors: [connectedJira(), githubConnector()] });
    await installJiraTools(page);
    const refusal = {
      error: NOT_AVAILABLE_NOTE,
      code: "connector_grants_not_allowed",
      recoverable: true,
    };
    await page.route(/\/api\/user-workflows(\?|$)/, (route) =>
      route.request().method() === "POST"
        ? route.fulfill({
            status: 422,
            contentType: "application/json",
            body: JSON.stringify({ detail: refusal }),
          })
        : route.fallback(),
    );
    await openToolsTab(dashboard);

    const jira = await expandApp(page, "Jira");
    await jira.getByRole("switch", { name: "Search issues" }).click();
    await saveWorkflow(page, "Refused workflow");

    await expect(page.getByText(NOT_AVAILABLE_NOTE).first()).toBeVisible();
    await expect(page.getByText(/connector_grants_not_allowed/)).toHaveCount(0);
    await expect(page.getByText(/"recoverable"/)).toHaveCount(0);
    // Nothing was saved, and the author's choice is still on screen.
    await expect(page.getByRole("button", { name: /Saved/ })).toHaveCount(0);
    await expect(jira.getByRole("switch", { name: "Search issues" })).toHaveAttribute("aria-checked", "true");
  });

  test("TS-CA-06 a predefined workflow shows the save-a-copy note and cannot switch tools on", async ({
    page,
  }) => {
    const connectors = await installConnectorsMocks(page, {
      connectors: [connectedJira(), githubConnector()],
    });
    await installJiraTools(page);
    // The built-in's compiled definition (GET /api/workflows/{id}); its agents are in the mock library.
    await page.route(/\/api\/workflows\/user_stories(\?|$)/, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "user_stories",
          name: "User Stories",
          description: "Turn a brief into a backlog.",
          planner: "skip",
          clarify_mode: "skip",
          clarify_defaults: [],
          context_providers: [],
          deliverable: { strategy: "streamed_text", name: "output.md" },
          steps: [
            {
              agent_id: "domain-analyst",
              name: "Domain Discovery Agent",
              role: "Market & Persona Research",
              order: 1,
              strategy: "sequential",
              gates: [],
              validators: [],
            },
            {
              agent_id: "epic-architect",
              name: "Backlog Architecture Agent",
              role: "Epic & Story Composition",
              order: 2,
              strategy: "sequential",
              gates: [],
              validators: [],
            },
          ],
          // The canvas is drawn from the authored steps (`manifest_steps`), as the live payload sends them.
          manifest_steps: [{ agent: "domain-analyst" }, { agent: "epic-architect" }],
          has_override: false,
          is_overridden: false,
        }),
      }),
    );
    await page.addInitScript(([k, t]) => localStorage.setItem(k, t), [TOKEN_KEY, TEST_JWT]);
    await page.goto("/workflows/user_stories/canvas");
    await expect(page.getByTestId("canvas-node-domain-analyst")).toBeVisible({ timeout: 45_000 });
    await selectNodeToolsTab(page, "domain-analyst");

    const section = connectedApps(page);
    await expect(section.getByText(NOT_AVAILABLE_NOTE)).toBeVisible();
    const jira = await expandApp(page, "Jira");
    await expect(jira.getByRole("switch", { name: "Search issues" })).toBeDisabled();
    await expect(jira.getByRole("switch", { name: "Create issue" })).toBeDisabled();
    await expect(jira.getByRole("switch", { name: "Search issues" })).toHaveAttribute("aria-checked", "false");
    // Reading is allowed; nothing is written.
    expect(connectors.requests.some((r) => r.method !== "GET")).toBe(false);
  });
});
