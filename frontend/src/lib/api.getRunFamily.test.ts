import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { getRunFamily, getWorkflow } from "@/lib/api";

// ─────────────────────────────────────────────────────────────────
// Revision Families (B1): real behavior of the getRunFamily fetcher and
// the normalizeWorkflowRun parent/root mapping, driven through the global
// fetch that api.ts's request() calls.
// ─────────────────────────────────────────────────────────────────

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function okJson(body: unknown) {
  return { ok: true, json: async () => body };
}

describe("getRunFamily", () => {
  it("GETs /api/runs/{id}/family with a Bearer token and returns the parsed family", async () => {
    const family = {
      root_id: "root-9",
      members: [
        {
          id: "root-9",
          type: "prototype",
          title: "t",
          status: "completed",
          revision_index: 1,
          parent_run_id: null,
          created_at: "2026-07-01T00:00:00Z",
          completed_at: null,
        },
      ],
    };
    fetchMock.mockResolvedValue(okJson(family));

    const result = await getRunFamily("tok", "run-1");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/runs/run-1/family");
    expect(options.method).toBe("GET");
    expect((options.headers as Record<string, string>).Authorization).toBe("Bearer tok");

    // Returned verbatim (unnormalized, snake_case) like getChainContext.
    expect(result).toEqual(family);
    expect(result.root_id).toBe("root-9");
    expect(result.members[0].revision_index).toBe(1);
  });
});

describe("normalizeWorkflowRun parent/root mapping", () => {
  const baseRaw = {
    id: "run-1",
    title: "t",
    type: "prototype",
    status: "completed",
    input: "in",
    output: "out",
    agent_outputs: null,
    agent_count: 3,
    duration: 10,
    error: null,
    token_usage: null,
    model_id: null,
    created_at: "2026-07-01T00:00:00Z",
    completed_at: null,
  };

  it("maps parent_run_id/root_run_id when present", async () => {
    fetchMock.mockResolvedValue(
      okJson({ ...baseRaw, parent_run_id: "p-1", root_run_id: "r-1" }),
    );

    const result = await getWorkflow("tok", "run-1");

    expect(result.parentRunId).toBe("p-1");
    expect(result.rootRunId).toBe("r-1");
  });

  it("falls back to null parent + own-id root when absent", async () => {
    fetchMock.mockResolvedValue(okJson({ ...baseRaw }));

    const result = await getWorkflow("tok", "run-1");

    expect(result.parentRunId).toBeNull();
    expect(result.rootRunId).toBe(result.id);
  });
});
