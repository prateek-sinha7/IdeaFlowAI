import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  getHandoff,
  startHandoff,
  getGithubPatStatus,
  saveGithubPat,
  deleteGithubPat,
  listApiKeys,
  createApiKey,
  revokeApiKey,
} from "./api-handoff";

const mockFetch = vi.fn();
global.fetch = mockFetch;

describe("api-handoff", () => {
  beforeEach(() => {
    mockFetch.mockClear();
  });

  afterEach(() => {
    mockFetch.mockClear();
  });

  const mockResponse = (body: unknown, status = 200) =>
    Promise.resolve({
      status,
      ok: status >= 200 && status < 300,
      json: () => Promise.resolve(body),
      statusText: "OK",
    } as Response);

  describe("getHandoff", () => {
    it("should fetch handoff session by token", async () => {
      const handoffData = {
        id: "handoff-123",
        token: "token-xyz",
        task_description: "Build a feature",
        repo_url: "https://github.com/repo",
        mode: "auto" as const,
        resolved_mode: null,
        status: "pending" as const,
        source_client: null,
        source_branch: null,
        created_at: "2024-01-01",
        started_at: null,
        completed_at: null,
        expires_at: "2024-01-08",
        pr_url: null,
        pr_number: null,
        branch_name: null,
        pipeline_output: null,
        error: null,
        issuer_email: "user@example.com",
        has_github_pat: false,
      };

      mockFetch.mockResolvedValue(mockResponse(handoffData));

      const result = await getHandoff("auth-token", "handoff-token");

      expect(result).toEqual(handoffData);
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/handoff/handoff-token"),
        expect.objectContaining({
          method: "GET",
          headers: expect.objectContaining({
            Authorization: "Bearer auth-token",
          }),
        })
      );
    });

    it("should URL-encode handoff token", async () => {
      mockFetch.mockResolvedValue(mockResponse({}));

      await getHandoff("token", "token/with/slashes");

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("token%2Fwith%2Fslashes"),
        expect.anything()
      );
    });

    it("should throw on failed response", async () => {
      mockFetch.mockResolvedValue(
        Promise.resolve({
          status: 404,
          ok: false,
          json: () => Promise.resolve({ detail: "Not found" }),
        } as Response)
      );

      await expect(getHandoff("token", "invalid")).rejects.toThrow("Not found");
    });
  });

  describe("startHandoff", () => {
    it("should POST to start handoff", async () => {
      const response = { status: "started", started_at: "2024-01-01T00:00:00Z" };
      mockFetch.mockResolvedValue(mockResponse(response));

      const result = await startHandoff("auth-token", "handoff-id");

      expect(result).toEqual(response);
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/handoff/handoff-id/start"),
        expect.objectContaining({ method: "POST" })
      );
    });
  });

  describe("GitHub PAT management", () => {
    it("should get GitHub PAT status", async () => {
      const patStatus = {
        github_username: "octocat",
        scopes: "repo,gist",
        last_4: "abcd",
        created_at: "2024-01-01",
        updated_at: "2024-01-02",
      };

      mockFetch.mockResolvedValue(mockResponse(patStatus));

      const result = await getGithubPatStatus("token");

      expect(result).toEqual(patStatus);
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/settings/github-pat"),
        expect.objectContaining({ method: "GET" })
      );
    });

    it("should return null if PAT not set", async () => {
      mockFetch.mockResolvedValue(mockResponse(null));

      const result = await getGithubPatStatus("token");

      expect(result).toBeNull();
    });

    it("should save GitHub PAT", async () => {
      const patStatus = {
        github_username: "octocat",
        scopes: "repo",
        last_4: "1234",
        created_at: "2024-01-01",
        updated_at: "2024-01-02",
      };

      mockFetch.mockResolvedValue(mockResponse(patStatus));

      const result = await saveGithubPat("token", "ghp_xxx");

      expect(result).toEqual(patStatus);
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/settings/github-pat"),
        expect.objectContaining({
          method: "PUT",
          body: JSON.stringify({ pat: "ghp_xxx" }),
        })
      );
    });

    it("should delete GitHub PAT", async () => {
      mockFetch.mockResolvedValue(mockResponse(undefined, 204));

      await deleteGithubPat("token");

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/settings/github-pat"),
        expect.objectContaining({ method: "DELETE" })
      );
    });
  });

  describe("API keys management", () => {
    it("should list API keys", async () => {
      const keys = [
        {
          id: "key-1",
          name: "Dev Key",
          token_prefix: "sk_dev",
          last_used_at: "2024-01-01",
          created_at: "2023-12-01",
          revoked_at: null,
        },
      ];

      mockFetch.mockResolvedValue(mockResponse(keys));

      const result = await listApiKeys("token");

      expect(result).toEqual(keys);
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/settings/api-keys"),
        expect.objectContaining({ method: "GET" })
      );
    });

    it("should create API key", async () => {
      const createdKey = {
        id: "key-new",
        name: "New Key",
        token: "sk_live_xxx",
        token_prefix: "sk_live",
        last_used_at: null,
        created_at: "2024-01-01",
        revoked_at: null,
      };

      mockFetch.mockResolvedValue(mockResponse(createdKey));

      const result = await createApiKey("token", "New Key");

      expect(result).toEqual(createdKey);
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/settings/api-keys"),
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ name: "New Key" }),
        })
      );
    });

    it("should revoke API key", async () => {
      mockFetch.mockResolvedValue(mockResponse(undefined, 204));

      await revokeApiKey("token", "key-id");

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/settings/api-keys/key-id"),
        expect.objectContaining({ method: "DELETE" })
      );
    });

    it("should URL-encode key ID in revoke", async () => {
      mockFetch.mockResolvedValue(mockResponse(undefined, 204));

      await revokeApiKey("token", "key/with/slash");

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining("key%2Fwith%2Fslash"),
        expect.anything()
      );
    });
  });

  describe("error handling", () => {
    it("should handle JSON parse errors", async () => {
      mockFetch.mockResolvedValue({
        status: 500,
        ok: false,
        json: () => Promise.reject(new Error("Invalid JSON")),
        statusText: "Internal Server Error",
      } as Response);

      await expect(getHandoff("token", "id")).rejects.toThrow();
    });

    it("should use statusText on parse failure", async () => {
      mockFetch.mockResolvedValue({
        status: 500,
        ok: false,
        json: () => Promise.reject(new Error("Invalid JSON")),
        statusText: "Server Error",
      } as Response);

      await expect(getHandoff("token", "id")).rejects.toThrow("Server Error");
    });

    it("should handle 204 No Content as undefined", async () => {
      mockFetch.mockResolvedValue(
        Promise.resolve({
          status: 204,
          ok: true,
          json: () => Promise.resolve(null),
        } as Response)
      );

      const result = await deleteGithubPat("token");
      expect(result).toBeUndefined();
    });
  });
});
