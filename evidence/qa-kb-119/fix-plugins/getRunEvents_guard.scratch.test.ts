// Scratch check for FIX-778 (not in the tree). Run by copying it to frontend/src/lib/ and
// `npx vitest run src/lib/<file>`, then delete it. Observed 2026-10-09: 4 passed (4).
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { getRunEvents } from "@/lib/api";
const fetchMock = vi.fn();
beforeEach(() => { fetchMock.mockReset(); vi.stubGlobal("fetch", fetchMock); });
afterEach(() => { vi.unstubAllGlobals(); });
const ok = (b: unknown) => ({ ok: true, json: async () => b });
describe("scratch: getRunEvents loop guards", () => {
  it("stuck cursor (has_more true, next_after == after) stops after one request", async () => {
    fetchMock.mockResolvedValue(ok({ events: [], has_more: true, next_after: 0 }));
    await getRunEvents("t", "r", 0);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
  it("NaN cursor with the {} catch-all stops after one request", async () => {
    fetchMock.mockResolvedValue(ok({}));
    await getRunEvents("t", "r", Number.NaN);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
  it("has_more true with no next_after stops after one request", async () => {
    fetchMock.mockResolvedValue(ok({ events: [], has_more: true }));
    await getRunEvents("t", "r", 0);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
  it("first request asks for after=<afterSeq>&limit=5000", async () => {
    fetchMock.mockResolvedValue(ok({ events: [] }));
    await getRunEvents("t", "r", 7);
    expect(String(fetchMock.mock.calls[0][0])).toContain("/api/runs/r/events?after=7&limit=5000");
  });
});
