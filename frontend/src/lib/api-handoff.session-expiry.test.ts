/**
 * api-handoff.ts's authedJson() — 401 session-expiry handling (T33).
 *
 * V7's sweep found this was the 5th place the shared 401 -> session-expired
 * flow (FR-015) had been reimplemented as a generic throw instead of routing
 * through lib/api's handleSessionExpiry(). Drives the real fetch path (mocked
 * global fetch, clones the api.test.ts idiom) and asserts the shared helper
 * actually fires on a 401 for both handoff and settings call sites.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

const { handleSessionExpiryMock } = vi.hoisted(() => ({
  handleSessionExpiryMock: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  handleSessionExpiry: handleSessionExpiryMock,
}));

import { getHandoff, getGithubPatStatus } from "@/lib/api-handoff";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  handleSessionExpiryMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function unauthorized() {
  return {
    ok: false,
    status: 401,
    statusText: "Unauthorized",
    json: async () => ({ detail: "Not authenticated" }),
  };
}

describe("api-handoff authedJson — 401 handling", () => {
  it("calls handleSessionExpiry on a 401 from getHandoff (/handoff/{token})", async () => {
    fetchMock.mockResolvedValue(unauthorized());

    await expect(getHandoff("stale.token", "handoff-1")).rejects.toThrow();

    expect(handleSessionExpiryMock).toHaveBeenCalledTimes(1);
  });

  it("calls handleSessionExpiry on a 401 from getGithubPatStatus (/handoff/settings)", async () => {
    fetchMock.mockResolvedValue(unauthorized());

    await expect(getGithubPatStatus("stale.token")).rejects.toThrow();

    expect(handleSessionExpiryMock).toHaveBeenCalledTimes(1);
  });

  it("does not call handleSessionExpiry on a non-401 error", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      json: async () => ({ detail: "boom" }),
    });

    await expect(getHandoff("t.t.t", "handoff-1")).rejects.toThrow();

    expect(handleSessionExpiryMock).not.toHaveBeenCalled();
  });
});
