import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { getRunArtifacts } from "@/lib/api";

// ─────────────────────────────────────────────────────────────────
// Workstream C1 (POR §6.6) — getRunArtifacts is the FIRST FE consumer of
// Workstream-A's `?kind=` filter on GET /api/runs/{id}/artifacts (260702-s3p).
// Real behavior driven through the global fetch that api.ts's request() calls
// (clones the api.getRunFamily.test.ts fetch-mock idiom).
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

describe("getRunArtifacts", () => {
  it("GETs /artifacts with ?kind= and ?include=content, a Bearer token, and parses the shape", async () => {
    const wire = {
      workflow_id: "run-1",
      artifacts: [
        {
          id: "a-1",
          kind: "clarifications",
          producer_step: "clarify",
          producer_agent: "clarify_engine",
          task_id: "t-1",
          content_hash: "h1",
          version: 1,
          visibility: "workspace",
          location: "db",
          parents: [],
          derived_from: [],
          children: [],
          content: "[{\"round\":1}]",
        },
      ],
    };
    fetchMock.mockResolvedValue(okJson(wire));

    const result = await getRunArtifacts("tok", "run-1", {
      kind: "clarifications",
      includeContent: true,
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/runs/run-1/artifacts");
    expect(String(url)).toContain("kind=clarifications");
    expect(String(url)).toContain("include=content");
    expect(options.method).toBe("GET");
    expect((options.headers as Record<string, string>).Authorization).toBe("Bearer tok");

    expect(result).toEqual(wire);
    expect(result.workflow_id).toBe("run-1");
    expect(result.artifacts[0].kind).toBe("clarifications");
    expect(result.artifacts[0].content).toBe("[{\"round\":1}]");
  });

  it("issues a clean no-query-string URL when no opts are given", async () => {
    fetchMock.mockResolvedValue(okJson({ workflow_id: "run-2", artifacts: [] }));

    await getRunArtifacts("tok", "run-2");

    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/runs/run-2/artifacts");
    expect(String(url)).not.toContain("?");
  });
});
