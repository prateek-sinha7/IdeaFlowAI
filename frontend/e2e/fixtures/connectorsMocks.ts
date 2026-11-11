/**
 * Mocked Connectors backend for the Flowin E2E suite (mocked project).
 *
 * Serves the `/api/connectors` surface the Connectors page uses, with NO backend and
 * NO real identity provider:
 *
 *   REST  `page.route(/\/api\/connectors(\/|\?|$)/)`: GET list, POST /{key}/authorize,
 *         DELETE /{key}, GET /{key}/tools. Registered AFTER the `mockApi` fixture's
 *         catch-all, so it wins by Playwright's last-registered-first precedence.
 *   IdP   `context.route("https://auth.example.test/**")`: stands in for the provider's
 *         consent screen. When the sign-in window (or the tab) reaches it, the mock
 *         marks the connector connected, as the real callback would, and answers 302
 *         to the app's `/connectors/oauth-complete` landing page. A context-level route
 *         is needed because the sign-in window is a popup, a separate Page.
 *
 * The wire shapes mirror `frontend/src/types/connectors.ts` and
 * `backend/app/api/connectors.py`. They are restated here on purpose: a fixture that
 * imported the app's types would follow a wrong type change silently instead of
 * failing the journey. No response contains a token, code, state or verifier.
 */
import type { Page, Route } from "@playwright/test";
import { APP_ORIGIN } from "./constants";

export type MockConnectorStatus = "connected" | "not_connected" | "expired" | "not_configured";
export type MockProviderRevocation = "revoked" | "failed" | "not_attempted";

export interface MockConnectorSummary {
  key: string;
  display_name: string;
  description: string;
  icon: string;
  docs_url: string;
  mode: "remote_mcp" | "native_api";
  status: MockConnectorStatus;
  account: { id: string; display_name: string | null; login: string | null } | null;
  requested_scopes: string[];
  granted_scopes: string[];
  sites: Array<{ id: string; name: string; url: string }>;
  connected_at: string | null;
  last_refreshed_at: string | null;
}

/** The provider's consent screen. Never reachable from the mocked project. */
export const IDP_ORIGIN = "https://auth.example.test";
export const IDP_AUTHORIZE_URL = `${IDP_ORIGIN}/authorize?client_id=e2e-client`;
export const OAUTH_COMPLETE_PATH = "/connectors/oauth-complete";

const CONNECTED_AT = "2026-03-01T09:30:00Z";

export function jiraConnector(patch: Partial<MockConnectorSummary> = {}): MockConnectorSummary {
  return {
    key: "jira",
    display_name: "Jira",
    description: "Search and update Jira issues from your workflows.",
    icon: "jira",
    docs_url: "https://example.test/docs/jira",
    mode: "native_api",
    status: "not_connected",
    account: null,
    requested_scopes: ["read:jira-work", "write:jira-work"],
    granted_scopes: [],
    sites: [],
    connected_at: null,
    last_refreshed_at: null,
    ...patch,
  };
}

export function githubConnector(patch: Partial<MockConnectorSummary> = {}): MockConnectorSummary {
  return {
    key: "github",
    display_name: "GitHub",
    description: "Read repositories, issues and pull requests.",
    icon: "github",
    docs_url: "https://example.test/docs/github",
    mode: "remote_mcp",
    status: "not_connected",
    account: null,
    requested_scopes: ["repo", "read:user"],
    granted_scopes: [],
    sites: [],
    connected_at: null,
    last_refreshed_at: null,
    ...patch,
  };
}

/** A connected Jira row, the base for the disconnect and reconnect journeys. */
export function connectedJira(patch: Partial<MockConnectorSummary> = {}): MockConnectorSummary {
  return jiraConnector({
    status: "connected",
    account: { id: "acc-1", display_name: "Jane Doe", login: "jane" },
    granted_scopes: ["read:jira-work", "write:jira-work"],
    sites: [{ id: "site-1", name: "Acme Cloud", url: "https://acme.example.test" }],
    connected_at: CONNECTED_AT,
    last_refreshed_at: CONNECTED_AT,
    ...patch,
  });
}

export interface ConnectorsMockOptions {
  connectors?: MockConnectorSummary[];
  /** What DELETE /{key} reports for the provider-side revoke. */
  providerRevocation?: MockProviderRevocation;
  /** Make DELETE /{key} fail once with a 502 envelope. */
  failNextDisconnect?: boolean;
}

export interface RecordedConnectorRequest {
  method: string;
  path: string;
}

export interface ConnectorsMock {
  /** Current server-side state; mutate through the methods below. */
  readonly connectors: MockConnectorSummary[];
  /** Every request the mock answered, in order. */
  readonly requests: RecordedConnectorRequest[];
  /** Times the provider's consent screen was reached. */
  readonly idpVisits: () => number;
  /** Replace a connector's row (a change made elsewhere, seen on the next poll). */
  setConnector: (key: string, patch: Partial<MockConnectorSummary>) => void;
  /** Hold the provider back: reaching it does not complete the sign-in (the user is still on the consent screen). */
  holdProvider: () => void;
  /** Complete the held sign-in: the next request to the provider finishes it. */
  releaseProvider: () => void;
}

function connectedFrom(summary: MockConnectorSummary, now: string): MockConnectorSummary {
  return {
    ...summary,
    status: "connected",
    account: { id: "acc-1", display_name: "Jane Doe", login: "jane" },
    granted_scopes: [...summary.requested_scopes],
    sites:
      summary.key === "jira"
        ? [{ id: "site-1", name: "Acme Cloud", url: "https://acme.example.test" }]
        : [],
    connected_at: now,
    last_refreshed_at: now,
  };
}

/**
 * Install the Connectors mock on a page and its context. Call it BEFORE the first
 * navigation, after the standard `mockApi` fixture has armed (fixtures do).
 */
export async function installConnectorsMocks(
  page: Page,
  opts: ConnectorsMockOptions = {},
): Promise<ConnectorsMock> {
  const connectors: MockConnectorSummary[] = (
    opts.connectors ?? [jiraConnector(), githubConnector()]
  ).map((c) => ({ ...c }));
  const requests: RecordedConnectorRequest[] = [];
  let visits = 0;
  let held = false;
  let failNext = opts.failNextDisconnect ?? false;
  const providerRevocation = opts.providerRevocation ?? "revoked";
  /** Key whose sign-in is in flight, set by POST /authorize. */
  let authorizing: string | null = null;

  const indexOf = (key: string) => connectors.findIndex((c) => c.key === key);

  const json = (route: Route, data: unknown, status = 200) =>
    route.fulfill({
      status,
      contentType: "application/json",
      headers: { "cache-control": "no-store" },
      body: JSON.stringify(data),
    });

  await page.route(/\/api\/connectors(\/|\?|$)/, async (route) => {
    const request = route.request();
    const method = request.method();
    const path = new URL(request.url()).pathname;
    const match = /\/api\/connectors\/([^/]+)(\/[a-z]+)?$/.exec(path);
    const key = match ? decodeURIComponent(match[1]) : null;
    const suffix = match?.[2] ?? "";
    requests.push({ method, path });

    if (method === "GET" && !key) return json(route, { connectors });

    if (key && indexOf(key) === -1) {
      return json(route, { error: "Unknown connector.", code: "unknown_connector", recoverable: false }, 404);
    }

    if (method === "POST" && key && suffix === "/authorize") {
      const row = connectors[indexOf(key)];
      if (row.status === "not_configured") {
        return json(
          route,
          { error: `${row.display_name} is not configured.`, code: "not_configured", recoverable: false },
          409,
        );
      }
      authorizing = key;
      return json(route, {
        authorization_url: IDP_AUTHORIZE_URL,
        expires_at: new Date(Date.now() + 10 * 60 * 1000).toISOString(),
      });
    }

    if (method === "DELETE" && key && suffix === "") {
      if (failNext) {
        failNext = false;
        return json(
          route,
          { error: "Could not disconnect.", code: "provider_unavailable", recoverable: true },
          502,
        );
      }
      const index = indexOf(key);
      connectors[index] = {
        ...connectors[index],
        status: "not_connected",
        account: null,
        granted_scopes: [],
        sites: [],
        connected_at: null,
        last_refreshed_at: null,
      };
      return json(route, { status: "disconnected", provider_revocation: providerRevocation });
    }

    if (method === "GET" && key && suffix === "/tools") {
      const row = connectors[indexOf(key)];
      return json(route, {
        connector: key,
        status: row.status === "connected" ? "connected" : "not_connected",
        tools: [],
        listed_at: null,
      });
    }

    return route.fallback();
  });

  // The provider's consent screen: finish the sign-in (as the backend callback
  // would) and send the browser to the landing page, as the callback's 303 does.
  let release: (() => void) | null = null;
  await page.context().route(`${IDP_ORIGIN}/**`, async (route) => {
    visits += 1;
    if (held) {
      await new Promise<void>((resolve) => {
        release = resolve;
      });
    }
    const key = authorizing;
    authorizing = null;
    if (key && indexOf(key) !== -1) {
      connectors[indexOf(key)] = connectedFrom(connectors[indexOf(key)], new Date().toISOString());
    }
    const query = key
      ? `connector=${key}&result=connected`
      : "connector=jira&result=error&reason=invalid_state";
    await route.fulfill({
      status: 302,
      headers: {
        location: `${APP_ORIGIN}${OAUTH_COMPLETE_PATH}?${query}`,
        "cache-control": "no-store",
      },
    });
  });

  return {
    connectors,
    requests,
    idpVisits: () => visits,
    setConnector: (key, patch) => {
      const index = indexOf(key);
      if (index !== -1) connectors[index] = { ...connectors[index], ...patch };
    },
    holdProvider: () => {
      held = true;
    },
    releaseProvider: () => {
      held = false;
      release?.();
      release = null;
    },
  };
}
