import { describe, it, expect } from "vitest";
import {
  isAuthorizeResponse,
  isConnectorListResponse,
  isConnectorSummary,
  isConnectorToolsResponse,
  isDisconnectResponse,
  type ConnectorSummary,
} from "./connectors";

function summary(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  const base: ConnectorSummary = {
    key: "jira",
    display_name: "Jira",
    description: "Issues",
    icon: "jira",
    docs_url: "https://example.test/docs",
    mode: "native_api",
    status: "connected",
    account: { id: "a1", display_name: "Ada", login: null },
    requested_scopes: ["read:jira-work"],
    granted_scopes: ["read:jira-work"],
    sites: [{ id: "s1", name: "Acme", url: "https://acme.atlassian.net" }],
    connected_at: "2026-09-01T10:00:00Z",
    last_refreshed_at: null,
  };
  return { ...base, ...overrides };
}

describe("isConnectorSummary", () => {
  it("accepts a connected Jira summary", () => {
    expect(isConnectorSummary(summary())).toBe(true);
  });

  it("accepts a not_connected summary with no account, sites or dates", () => {
    expect(
      isConnectorSummary(
        summary({ status: "not_connected", account: null, sites: [], granted_scopes: [], connected_at: null }),
      ),
    ).toBe(true);
  });

  it("tolerates fields the backend adds later", () => {
    expect(isConnectorSummary(summary({ future_field: { a: 1 } }))).toBe(true);
  });

  it.each([
    ["an unknown status", { status: "pending" }],
    ["an unknown mode", { mode: "soap" }],
    ["a key that breaks the path rule", { key: "Jira!" }],
    ["scopes that are not strings", { granted_scopes: [1, 2] }],
    ["a site without a url", { sites: [{ id: "s", name: "n" }] }],
    ["an account with a numeric id", { account: { id: 1, display_name: null, login: null } }],
    ["a missing connected_at", { connected_at: undefined }],
  ])("rejects %s", (_label, overrides) => {
    expect(isConnectorSummary(summary(overrides))).toBe(false);
  });

  it("rejects values that are not objects", () => {
    expect(isConnectorSummary(null)).toBe(false);
    expect(isConnectorSummary([])).toBe(false);
    expect(isConnectorSummary("jira")).toBe(false);
  });
});

describe("isConnectorListResponse", () => {
  it("accepts an empty list", () => {
    expect(isConnectorListResponse({ connectors: [] })).toBe(true);
  });

  it("rejects the list when one entry is malformed", () => {
    expect(isConnectorListResponse({ connectors: [summary(), summary({ status: "x" })] })).toBe(false);
  });

  it("rejects a bare array", () => {
    expect(isConnectorListResponse([summary()])).toBe(false);
  });
});

describe("isAuthorizeResponse", () => {
  it("requires both fields", () => {
    expect(isAuthorizeResponse({ authorization_url: "https://x.test", expires_at: "2026-09-01T10:10:00Z" })).toBe(true);
    expect(isAuthorizeResponse({ authorization_url: "https://x.test" })).toBe(false);
  });
});

describe("isDisconnectResponse", () => {
  it.each(["revoked", "failed", "not_attempted"])("accepts provider_revocation %s", (value) => {
    expect(isDisconnectResponse({ status: "disconnected", provider_revocation: value })).toBe(true);
  });

  it("rejects another status or revocation value", () => {
    expect(isDisconnectResponse({ status: "ok", provider_revocation: "revoked" })).toBe(false);
    expect(isDisconnectResponse({ status: "disconnected", provider_revocation: "maybe" })).toBe(false);
  });
});

describe("isConnectorToolsResponse", () => {
  const tool = {
    name: "github__create_issue",
    source_name: "create_issue",
    title: "Create issue",
    description: "Creates an issue",
    write_capable: true,
  };

  it("accepts a list with tools", () => {
    expect(
      isConnectorToolsResponse({ connector: "github", status: "connected", tools: [tool], listed_at: null }),
    ).toBe(true);
  });

  it("rejects a tool whose write_capable is not a boolean", () => {
    expect(
      isConnectorToolsResponse({
        connector: "github",
        status: "connected",
        tools: [{ ...tool, write_capable: "yes" }],
        listed_at: null,
      }),
    ).toBe(false);
  });

  it("rejects not_configured, which this endpoint never returns as a status", () => {
    expect(
      isConnectorToolsResponse({ connector: "github", status: "not_configured", tools: [], listed_at: null }),
    ).toBe(false);
  });
});
