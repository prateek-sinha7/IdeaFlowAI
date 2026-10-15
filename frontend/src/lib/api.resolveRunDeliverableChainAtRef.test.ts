import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { resolveRunDeliverable } from "@/lib/api";

// ISS-975 (sibling of ISS-665 / QA-KB-053) — Backlog.pdf at pinned ref v2 lives
// only at .chain/Backlog.pdf, but the live tree holds a ROOT Backlog.pdf. The
// resolver is ref-blind, so it returns the root path, which 404s at the ref.
// Fixed: a ref-aware resolver lists the tree AT the ref and returns the .chain path.

const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

const file = (path: string) => ({ path, size: 10, modified: 1, text: false, kind: "binary", deliverable: true });

describe("resolveRunDeliverable — path resolved at the pinned ref (ISS-975)", () => {
  it("ISS-975: with ref v2 the deliverable path is the one listed at v2 (.chain/Backlog.pdf), not the live root path", async () => {
    fetchMock.mockImplementation(async (url: string) => {
      const atRef = String(url).includes("ref=v2");
      return {
        ok: true,
        json: async () => ({
          run_id: "run-1", expired: false, truncated: false,
          files: [file(atRef ? ".chain/Backlog.pdf" : "Backlog.pdf")],
        }),
      };
    });

    const hit = await resolveRunDeliverable("test-token", "run-1", "Backlog.pdf", "v2");

    expect(hit?.path).toBe(".chain/Backlog.pdf");
  });
});
