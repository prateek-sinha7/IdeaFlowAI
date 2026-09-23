import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  getAnalyticsSummary,
  getCapabilities,
  getPreferences,
  setToken,
  updatePreferences,
} from "@/lib/api";

// ─────────────────────────────────────────────────────────────────
// ISS-782 (QA-PS-036) / ISS-796 — the shared read-only GET cache.
//
// /analytics fired /api/analytics/summary, /api/settings/preferences and
// /api/capabilities twice each on one cold load, and the composer fires
// /api/capabilities once per `useAgentCapabilities` call site, because each
// caller owned its own fetch. These pin the cache that collapses them:
// concurrent AND short-interval-sequential callers of the same URL+token share
// one request, a different key still queries, and a write evicts.
// ─────────────────────────────────────────────────────────────────

const fetchMock = vi.fn();

function ok(body: unknown) {
  return {
    ok: true,
    status: 200,
    headers: new Headers(),
    json: async () => body,
  };
}

function callsTo(fragment: string): unknown[][] {
  return fetchMock.mock.calls.filter((call) => String(call[0]).includes(fragment));
}

beforeEach(() => {
  fetchMock.mockReset();
  fetchMock.mockImplementation(() => Promise.resolve(ok({ capabilities: [], model_catalog: [] })));
  vi.stubGlobal("fetch", fetchMock);
  localStorage.clear();
  setToken("tok");
});

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("shared read-only GET cache (ISS-782 / ISS-796)", () => {
  it("coalesces concurrent callers of the same endpoint into one fetch", async () => {
    // StrictMode's mount→unmount→remount shape: the same effect twice, same args.
    await Promise.all([getCapabilities("caps-a"), getCapabilities("caps-a")]);
    expect(callsTo("/api/capabilities")).toHaveLength(1);
  });

  it("serves a later caller from the resolved result (ISS-796 CanvasConfigRail)", async () => {
    // CanvasView fetches on mount; CanvasConfigRail asks again seconds later
    // when the agent-config tab opens, long after the first fetch RESOLVED —
    // an in-flight-only guard would miss this one.
    await getCapabilities("caps-b");
    await getCapabilities("caps-b");
    expect(callsTo("/api/capabilities")).toHaveLength(1);
  });

  it("keeps different tokens apart", async () => {
    await getCapabilities("caps-c");
    await getCapabilities("caps-d");
    expect(callsTo("/api/capabilities")).toHaveLength(2);
  });

  it("re-queries the server when an analytics filter changes", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(ok({ kpis: {} })));
    await getAnalyticsSummary("an-a", "30d");
    await getAnalyticsSummary("an-a", "30d");
    await getAnalyticsSummary("an-a", "7d");
    // Same range shares one request; a new range is a new key (SC-1: the server
    // scopes every figure, so a filter change must reach it).
    expect(callsTo("/api/analytics/summary")).toHaveLength(2);
  });

  it("drops the cached preferences after a write", async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(ok({ preferred_model: null, available_models: [] })),
    );
    await getPreferences("pref-a");
    await updatePreferences("pref-a", "claude-x");
    await getPreferences("pref-a");
    const gets = callsTo("/api/settings/preferences").filter(
      (call) => ((call[1] as RequestInit | undefined)?.method ?? "GET") === "GET",
    );
    // Two GETs, not one: the PUT made the cached copy stale.
    expect(gets).toHaveLength(2);
  });

  it("does not cache a failure", async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve({ ok: false, status: 500, headers: new Headers(), json: async () => ({ detail: "boom" }) }),
    );
    await expect(getCapabilities("caps-e")).rejects.toThrow();
    fetchMock.mockImplementation(() => Promise.resolve(ok({ capabilities: [], model_catalog: [] })));
    await getCapabilities("caps-e");
    expect(callsTo("/api/capabilities")).toHaveLength(2);
  });
});

describe("shared read-only GET cache — realistic compose session (ISS-833)", () => {
  it(
    "still reuses the cache when the second caller asks more than 30s later",
    async () => {
      vi.useFakeTimers();
      try {
        await getCapabilities("caps-f");
        await vi.advanceTimersByTimeAsync(31_000);
        await getCapabilities("caps-f");
        expect(callsTo("/api/capabilities")).toHaveLength(1);
      } finally {
        vi.useRealTimers();
      }
    },
  );
});
