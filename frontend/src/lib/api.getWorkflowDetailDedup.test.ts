import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getWorkflowDetail, setToken } from "@/lib/api";

// ─────────────────────────────────────────────────────────────────
// QA-PS-043 / ISS-819 (root cause; also ISS-790, ISS-820, ISS-821, ISS-822) —
// `/create/user-stories` cold-loads `GET /api/workflows/user_stories` twice
// under React StrictMode because `IdeaInputPage.tsx:1116`'s mount effect
// calls `getWorkflowDetail()` with only a `cancelled` flag guarding the
// state update, never the fetch itself — no in-flight dedup, unlike the
// `inFlightWorkflows` guard `getWorkflows()` already has (FIX-616 /
// ISS-783). LaunchWizard.tsx:507, WorkflowDialog.tsx:79, ComposerPage.tsx:606
// and page.tsx:492 share the identical unguarded shape (ISS-820/821/822),
// so the fix belongs in `getWorkflowDetail()` itself — one guard closes
// every caller, the same way FIX-616 closed every `getWorkflows()` caller.
//
// This pins the fix at its root: concurrent calls for the SAME workflow id
// must share one in-flight fetch.
// ─────────────────────────────────────────────────────────────────

const fetchMock = vi.fn();

function okWorkflowDetail() {
  return {
    ok: true,
    status: 200,
    headers: new Headers(),
    json: async () => ({ id: "user_stories", agents: [], name: "User Stories" }),
  };
}

beforeEach(() => {
  fetchMock.mockReset();
  fetchMock.mockImplementation(() => Promise.resolve(okWorkflowDetail()));
  vi.stubGlobal("fetch", fetchMock);
  localStorage.clear();
  setToken("tok");
});

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

// @pytest.mark.issue("ISS-819") equivalent for vitest.
describe("getWorkflowDetail() concurrent-call dedup (QA-PS-043 / ISS-819)", () => {
  it("coalesces concurrent calls for the SAME workflow id into a single fetch", async () => {
    const [a, b] = await Promise.all([
      getWorkflowDetail("tok", "user_stories"),
      getWorkflowDetail("tok", "user_stories"),
    ]);

    expect(a).toEqual(b);

    const detailCalls = fetchMock.mock.calls.filter((call) =>
      String(call[0]).includes("/api/workflows/user_stories"),
    );
    // Without a dedup guard this is 2 — the bug's whole symptom is a
    // duplicate GET /api/workflows/user_stories fired within the same tick
    // (React StrictMode double-invoking IdeaInputPage's mount effect).
    expect(detailCalls).toHaveLength(1);
  });
});
