import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getWorkflow } from "@/lib/api";

// ISS-1213 — the history-reopen path calls getWorkflow(token, id, false), which
// requests `?include_heavy=false`. The backend then returns `input: null` and
// `agent_outputs: null`. The normalizer must accept that payload and hand the
// UI an empty-string `input` (never null) and no agentOutputs.

const fetchMock = vi.fn();

function heavyStrippedRun() {
  return {
    ok: true,
    status: 200,
    headers: new Headers(),
    json: async () => ({
      id: "run-iss1213",
      title: "t",
      type: "prototype",
      status: "completed",
      input: null,
      output: "out",
      agent_outputs: null,
      agent_count: 3,
      duration: 10,
      error: null,
      token_usage: null,
      model_id: null,
      created_at: "2026-07-01T00:00:00Z",
      completed_at: null,
    }),
  };
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("getWorkflow() with includeHeavy=false (ISS-1213)", () => {
  it("requests include_heavy=false and normalizes a null input to an empty string", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(heavyStrippedRun()));

    const run = await getWorkflow("tok", "run-iss1213", false);

    expect(String(fetchMock.mock.calls[0][0])).toContain(
      "/api/runs/run-iss1213?include_heavy=false",
    );
    expect(run.input).toBe("");
    expect(run.agentOutputs).toBeUndefined();
    expect(run.output).toBe("out");
  });
});
