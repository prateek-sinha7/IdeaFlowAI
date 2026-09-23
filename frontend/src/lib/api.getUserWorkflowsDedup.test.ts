import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getUserWorkflows, setToken } from "@/lib/api";

// ─────────────────────────────────────────────────────────────────
// QA-PS-041 / ISS-788 — a cold /workflows load fired GET /api/user-workflows
// 2x (4x on a client-side nav): SavedWorkflowsPage's mount effect is the only
// caller, but React StrictMode re-runs it in dev and an SPA route change
// mounts the page on top of the shell that is already up.
//
// The guard belongs in the request layer, mirroring `getWorkflows()`'s
// `inFlightWorkflows` and `refreshOnce()`'s `inFlightRefresh` in the same
// file — so it covers every remount and any future caller, not one page.
// ─────────────────────────────────────────────────────────────────

const fetchMock = vi.fn();

function okRows() {
  return {
    ok: true,
    status: 200,
    headers: new Headers(),
    json: async () => [{ id: "w1", name: "My presentation" }],
  };
}

beforeEach(() => {
  fetchMock.mockReset();
  fetchMock.mockImplementation(() => Promise.resolve(okRows()));
  vi.stubGlobal("fetch", fetchMock);
  localStorage.clear();
  setToken("tok");
});

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

function listCalls() {
  return fetchMock.mock.calls.filter((call) =>
    String(call[0]).endsWith("/api/user-workflows"),
  );
}

describe("getUserWorkflows() concurrent-call dedup (QA-PS-041 / ISS-788)", () => {
  it("coalesces concurrent calls into a single fetch", async () => {
    const [a, b, c] = await Promise.all([
      getUserWorkflows("tok"),
      getUserWorkflows("tok"),
      getUserWorkflows("tok"),
    ]);

    expect(a).toEqual(b);
    expect(b).toEqual(c);
    // Without the guard this is 3 — the bug's symptom is redundant identical
    // /api/user-workflows calls fired within the same tick.
    expect(listCalls()).toHaveLength(1);
  });

  it("de-duplicates without caching: a later call still hits the network", async () => {
    await getUserWorkflows("tok");
    await getUserWorkflows("tok");

    // The list is mutated in place (rename/duplicate/delete), so a mount after
    // the previous request settled MUST see the server's copy.
    expect(listCalls()).toHaveLength(2);
  });

  it("never shares one identity's list with another", async () => {
    await Promise.all([getUserWorkflows("tok"), getUserWorkflows("other")]);

    expect(listCalls()).toHaveLength(2);
  });
});
