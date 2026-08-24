import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getMe, login, setToken, getToken } from "@/lib/api";

// ─────────────────────────────────────────────────────────────────
// Cognito migration Phase 4 — the shared REST client must survive an
// access-token expiry the same way the SSE hook already does
// (`useRunStream.ts::attemptSilentRefresh`).
//
// Cognito access tokens live ~60 min, so an authenticated REST call can expire
// mid-session. Before this, `request()` threw on every non-2xx, so a token that
// aged out between page load and the next click surfaced as a hard 401 the user
// could only clear by logging in again.
//
// These tests pin the behaviour AND its three bounds, which are the parts that
// would turn a convenience into a retry storm: one retry per request, only for
// requests that actually sent a bearer, and never for /refresh itself. The
// single-flight assertion matters because a screen fires several calls at once,
// so one expiry produces a burst of simultaneous 401s.
// ─────────────────────────────────────────────────────────────────

const fetchMock = vi.fn();

function okJson(body: unknown) {
  return { ok: true, status: 200, json: async () => body };
}

function unauthorized() {
  return {
    ok: false,
    status: 401,
    statusText: "Unauthorized",
    json: async () => ({ detail: "Invalid token" }),
  };
}

/** Authorization header actually sent on the Nth fetch call. */
function bearerOf(callIndex: number): string | null {
  const init = fetchMock.mock.calls[callIndex]?.[1] as RequestInit | undefined;
  return new Headers(init?.headers as HeadersInit | undefined).get("Authorization");
}

function urlOf(callIndex: number): string {
  return String(fetchMock.mock.calls[callIndex]?.[0]);
}

const ME = { id: "u1", email: "u@example.com", tier: "pro", is_admin: false };

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  localStorage.clear();
  setToken("stale.access.token");
});

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("request() 401 → refresh → retry (Cognito Phase 4)", () => {
  it("refreshes once and replays the original request with the NEW bearer", async () => {
    fetchMock
      .mockResolvedValueOnce(unauthorized()) // GET /api/auth/me — token aged out
      .mockResolvedValueOnce(okJson({ token: "fresh.access.token" })) // POST /refresh
      .mockResolvedValueOnce(okJson(ME)); // replayed GET /api/auth/me

    const user = await getMe("stale.access.token");

    expect(user).toEqual(ME);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(urlOf(1)).toContain("/api/auth/refresh");
    // The replay must carry the refreshed credential, not the dead one —
    // replaying the stale bearer would 401 again forever.
    expect(urlOf(2)).toContain("/api/auth/me");
    expect(bearerOf(2)).toBe("Bearer fresh.access.token");
    // The new token is persisted through the existing seam, so every later
    // call (and the SSE hook, which reads the same key) picks it up.
    expect(getToken()).toBe("fresh.access.token");
  });

  it("retries AT MOST once — a second 401 propagates instead of looping", async () => {
    fetchMock
      .mockResolvedValueOnce(unauthorized())
      .mockResolvedValueOnce(okJson({ token: "fresh.access.token" }))
      .mockResolvedValueOnce(unauthorized()); // the replay fails too

    await expect(getMe("stale.access.token")).rejects.toMatchObject({
      name: "ApiError",
      status: 401,
    });

    // Exactly 3: original + one refresh + one replay. Any recursion would keep
    // going, so the count IS the assertion.
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("surfaces the original 401 when the refresh itself fails", async () => {
    fetchMock
      .mockResolvedValueOnce(unauthorized())
      .mockResolvedValueOnce({
        ok: false,
        status: 501,
        statusText: "Not Implemented",
        json: async () => ({ detail: "Token refresh is not available." }),
      });

    // A break-glass/local user gets a 501 from /refresh. The caller must see the
    // real 401 rather than a confusing 501 from an endpoint it never called.
    await expect(getMe("stale.access.token")).rejects.toMatchObject({
      name: "ApiError",
      status: 401,
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("does NOT refresh a 401 from an unauthenticated request", async () => {
    fetchMock.mockResolvedValueOnce(unauthorized());

    // Wrong password on /login is a real answer, not an expiry. The login form
    // relies on receiving it — refreshing here would mask a failed sign-in.
    await expect(login("u@example.com", "wrong")).rejects.toMatchObject({
      name: "ApiError",
      status: 401,
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(urlOf(0)).toContain("/api/auth/login");
  });

  it("coalesces concurrent 401s into a SINGLE refresh call", async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (String(url).includes("/api/auth/refresh")) {
        return Promise.resolve(okJson({ token: "fresh.access.token" }));
      }
      const bearer = new Headers(init?.headers as HeadersInit | undefined).get(
        "Authorization",
      );
      return Promise.resolve(
        bearer === "Bearer fresh.access.token" ? okJson(ME) : unauthorized(),
      );
    });

    const [a, b, c] = await Promise.all([
      getMe("stale.access.token"),
      getMe("stale.access.token"),
      getMe("stale.access.token"),
    ]);

    expect([a, b, c]).toEqual([ME, ME, ME]);

    const refreshCalls = fetchMock.mock.calls.filter((call) =>
      String(call[0]).includes("/api/auth/refresh"),
    );
    // Without the single-flight guard this would be 3 — and the losers would
    // install a token a later refresh had already superseded.
    expect(refreshCalls).toHaveLength(1);
  });

  it("leaves a non-401 error untouched (no refresh attempt)", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 403,
      statusText: "Forbidden",
      json: async () => ({ detail: "Not permitted" }),
    });

    await expect(getMe("stale.access.token")).rejects.toMatchObject({
      name: "ApiError",
      status: 403,
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
