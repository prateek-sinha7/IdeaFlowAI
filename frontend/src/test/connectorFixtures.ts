import type { ConnectorSummary } from "@/types/connectors";

/** A typed minimal connector. Override only what the test is about. */
export function buildConnector(overrides: Partial<ConnectorSummary> = {}): ConnectorSummary {
  return {
    key: "github",
    display_name: "GitHub",
    description: "Read and change repositories, issues and pull requests.",
    icon: "github",
    docs_url: "https://docs.example.test/github",
    mode: "remote_mcp",
    status: "not_connected",
    account: null,
    requested_scopes: ["repo", "read:user"],
    granted_scopes: [],
    sites: [],
    connected_at: null,
    last_refreshed_at: null,
    ...overrides,
  };
}

/** A connected connector with an account, for tests of the connected card. */
export function buildConnectedConnector(overrides: Partial<ConnectorSummary> = {}): ConnectorSummary {
  return buildConnector({
    status: "connected",
    account: { id: "42", display_name: "Jane Doe", login: "jane" },
    granted_scopes: ["repo"],
    connected_at: "2026-09-01T12:00:00Z",
    last_refreshed_at: "2026-09-01T12:00:00Z",
    ...overrides,
  });
}
