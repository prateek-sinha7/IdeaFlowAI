import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { resolveRunDeliverable } from "@/lib/api";

// ─────────────────────────────────────────────────────────────────
// QA-SG-013 / ISS-768 (base `user_stories`) and ISS-774 (sibling, `custom`)
// — every `streamed_text`-strategy workflow's deliverable is materialized by
// the engine ONLY into `.chain/<name>` (engine.py's build_flat_payload,
// streamed_text branch), never to sandbox root. resolveRunDeliverable
// (api.ts:1193-1199) exact-matches candidates against the ROOT listing only
// (`f.path === c`), so it never finds a `.chain/`-only file and returns
// null — which disables the header Download button permanently on every
// completed run of these workflows.
//
// Fixed behaviour: resolveRunDeliverable should still resolve the declared
// deliverable when it exists only under `.chain/<name>` in the sandbox
// listing. Driven through the global fetch that api.ts's request() calls
// (clones the api.resolveRunDeliverableRef.test.ts fetch-mock idiom).
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

describe("resolveRunDeliverable — streamed_text deliverables living only in .chain/ (QA-SG-013)", () => {
  it("ISS-768: finds a base user_stories run's deliverable when it exists only at .chain/user_stories.md", async () => {
    fetchMock.mockResolvedValue(
      okJson({
        run_id: "run-1",
        expired: false,
        truncated: false,
        files: [
          { path: ".chain/user_stories.md", size: 42, modified: 1, text: true, kind: "text", deliverable: true },
        ],
      }),
    );

    const hit = await resolveRunDeliverable("test-token", "run-1", "user_stories.md");
    expect(hit).not.toBeNull();
  });

  it("ISS-774: finds a custom run's deliverable when it exists only at .chain/output.html", async () => {
    fetchMock.mockResolvedValue(
      okJson({
        run_id: "run-2",
        expired: false,
        truncated: false,
        files: [
          { path: ".chain/output.html", size: 416, modified: 1, text: true, kind: "text", deliverable: true },
        ],
      }),
    );

    const hit = await resolveRunDeliverable("test-token", "run-2", "output.html");
    expect(hit).not.toBeNull();
  });
});
