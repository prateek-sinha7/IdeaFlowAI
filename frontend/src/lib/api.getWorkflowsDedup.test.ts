import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getWorkflows, setToken } from "@/lib/api";

// ─────────────────────────────────────────────────────────────────
// QA-PS-037 / ISS-783 — /runs cold load fires GET /api/runs?limit=50 up to
// 6x: WorkflowHistory's own mount effects, page.tsx's mount effect and
// RunConnectionProvider's app-wide boot effect all call `getWorkflows()`
// independently with no shared dedup, unlike the existing `inFlightRefresh`
// single-flight guard a few lines above it in the same file (api.ts:225).
//
// This pins the fix at its root: concurrent callers requesting the SAME
// query (same limit/type/offset) must share one in-flight fetch, exactly
// like refreshOnce() already does for token refresh.
// ─────────────────────────────────────────────────────────────────

const fetchMock = vi.fn();

function okRuns(runs: unknown[] = []) {
  return {
    ok: true,
    status: 200,
    headers: new Headers({ "X-Total-Count": String(runs.length) }),
    json: async () => runs,
  };
}

beforeEach(() => {
  fetchMock.mockReset();
  fetchMock.mockImplementation(() => Promise.resolve(okRuns([])));
  vi.stubGlobal("fetch", fetchMock);
  localStorage.clear();
  setToken("tok");
});

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

// @pytest.mark.issue("ISS-783") equivalent for vitest: `it.fails` is the
// xfail(strict=True) analogue used elsewhere in this suite (see
// routes.iss339.test.ts) — remove `.fails` once getWorkflows() gets its
// in-flight dedup guard.
describe("getWorkflows() concurrent-call dedup (QA-PS-037 / ISS-783)", () => {
  it("coalesces concurrent calls with the SAME params into a single fetch", async () => {
    const [a, b, c] = await Promise.all([
      getWorkflows("tok", { limit: 50 }),
      getWorkflows("tok", { limit: 50 }),
      getWorkflows("tok", { limit: 50 }),
    ]);

    expect(a).toEqual(b);
    expect(b).toEqual(c);

    const runsCalls = fetchMock.mock.calls.filter((call) =>
      String(call[0]).includes("/api/runs"),
    );
    // Without a dedup guard this is 3 — the bug's whole symptom is redundant
    // identical /api/runs calls fired within the same tick.
    expect(runsCalls).toHaveLength(1);
  });
});
