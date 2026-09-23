import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { resolveRunDeliverable } from "@/lib/api";

// ─────────────────────────────────────────────────────────────────
// ISS-665 (sibling of QA-PS-008 / ISS-652) — resolveRunDeliverable has no
// `ref` parameter at all, so it always resolves the deliverable against the
// LIVE sandbox tree (`getRunSandbox(token, runId)`, no ref) even when the
// caller is displaying an older, pinned version. FilesTab's current-run row
// and its "From v{n-1}" base-version section both call this function while
// showing a pinned version, so the row can silently name/size the CURRENT
// file instead of that version's own tagged snapshot.
//
// Fixed behaviour: resolveRunDeliverable accepts an optional ref and forwards
// it to getRunSandbox exactly like SandboxTab.tsx already threads its own
// selectedRef through every sandbox call. Driven through the global fetch
// that api.ts's request() calls (clones the api.getRunArtifacts.test.ts
// fetch-mock idiom).
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

describe("resolveRunDeliverable — ref-scoped resolution (ISS-665)", () => {
  // it.fails: ISS-665 unfixed — this must start passing (and the .fails
  // wrapper removed) once resolveRunDeliverable gains a ref parameter.
  it.fails("ISS-665: forwards a supplied ref to the sandbox listing fetch, not the live tree", async () => {
    fetchMock.mockResolvedValue(
      okJson({
        run_id: "run-1",
        expired: false,
        truncated: false,
        files: [{ path: "prototype.html", size: 10, modified: 1, text: true, kind: "text", deliverable: true }],
      }),
    );

    // @ts-expect-error — ISS-665: resolveRunDeliverable has no ref parameter
    // yet; the fix adds a 4th argument threaded through to getRunSandbox.
    await resolveRunDeliverable("test-token", "run-1", "prototype.html", "v1");

    const sandboxCall = fetchMock.mock.calls.find(([url]) =>
      String(url).includes("/sandbox"),
    );
    expect(sandboxCall).toBeDefined();
    const requestedUrl = String(sandboxCall?.[0]);

    expect(requestedUrl).toContain("ref=v1");
  });
});
