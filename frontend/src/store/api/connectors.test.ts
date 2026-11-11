import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("./http", () => ({
  http: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}));

import { http } from "./http";
import { ConnectorsContractError, connectorsApi } from "./connectors";

const listBody = {
  connectors: [
    {
      key: "github",
      display_name: "GitHub",
      description: "Code",
      icon: "github",
      docs_url: "https://example.test",
      mode: "remote_mcp",
      status: "not_connected",
      account: null,
      requested_scopes: ["repo"],
      granted_scopes: [],
      sites: [],
      connected_at: null,
      last_refreshed_at: null,
    },
  ],
};

describe("connectorsApi", () => {
  beforeEach(() => {
    vi.mocked(http.get).mockReset();
    vi.mocked(http.post).mockReset();
    vi.mocked(http.delete).mockReset();
  });

  it("list returns the validated body from GET /api/connectors", async () => {
    vi.mocked(http.get).mockResolvedValue({ data: listBody });
    await expect(connectorsApi.list()).resolves.toEqual(listBody);
    expect(http.get).toHaveBeenCalledWith("/api/connectors");
  });

  it("list throws a contract error when the body is malformed", async () => {
    vi.mocked(http.get).mockResolvedValue({ data: { connectors: [{ key: "github" }] } });
    await expect(connectorsApi.list()).rejects.toBeInstanceOf(ConnectorsContractError);
  });

  it("list passes an HTTP error through unchanged", async () => {
    const failure = new Error("boom");
    vi.mocked(http.get).mockRejectedValue(failure);
    await expect(connectorsApi.list()).rejects.toBe(failure);
  });

  it("authorize posts to the key's authorize path with no body", async () => {
    const body = { authorization_url: "https://github.com/login/oauth/authorize", expires_at: "2026-09-01T10:10:00Z" };
    vi.mocked(http.post).mockResolvedValue({ data: body });
    await expect(connectorsApi.authorize("github")).resolves.toEqual(body);
    expect(http.post).toHaveBeenCalledWith("/api/connectors/github/authorize");
  });

  it("authorize encodes the key as one path segment", async () => {
    vi.mocked(http.post).mockResolvedValue({
      data: { authorization_url: "https://x.test", expires_at: "2026-09-01T10:10:00Z" },
    });
    await connectorsApi.authorize("a/../b");
    expect(http.post).toHaveBeenCalledWith("/api/connectors/a%2F..%2Fb/authorize");
  });

  it("authorize throws a contract error when authorization_url is missing", async () => {
    vi.mocked(http.post).mockResolvedValue({ data: { expires_at: "x" } });
    await expect(connectorsApi.authorize("github")).rejects.toBeInstanceOf(ConnectorsContractError);
  });

  it("disconnect sends DELETE and returns the provider revocation result", async () => {
    vi.mocked(http.delete).mockResolvedValue({
      data: { status: "disconnected", provider_revocation: "revoked" },
    });
    await expect(connectorsApi.disconnect("jira")).resolves.toEqual({
      status: "disconnected",
      provider_revocation: "revoked",
    });
    expect(http.delete).toHaveBeenCalledWith("/api/connectors/jira");
  });

  it("tools requests the key's tools path and validates the body", async () => {
    const body = { connector: "jira", status: "not_connected", tools: [], listed_at: null };
    vi.mocked(http.get).mockResolvedValue({ data: body });
    await expect(connectorsApi.tools("jira")).resolves.toEqual(body);
    expect(http.get).toHaveBeenCalledWith("/api/connectors/jira/tools");
  });

  it("tools throws a contract error for an unexpected status", async () => {
    vi.mocked(http.get).mockResolvedValue({
      data: { connector: "jira", status: "weird", tools: [], listed_at: null },
    });
    await expect(connectorsApi.tools("jira")).rejects.toBeInstanceOf(ConnectorsContractError);
  });
});
