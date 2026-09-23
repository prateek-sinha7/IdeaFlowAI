/**
 * ISS-834 (sibling of ISS-832, QA-PS-046 — `BUGS.md#qa-ps-046`).
 *
 * `capabilitiesApi.get` (`./capabilities.ts`) is a second, axios-based
 * implementation of `GET /api/capabilities` that has zero current callers
 * today but sits on `store/api/http.ts`, which has no cache/dedupe of its
 * own (grep confirmed — see the card). `lib/api.ts`'s `getCapabilities` was
 * wrapped in a shared, TTL-based `cachedGet()` by FIX-617 specifically so
 * concurrent callers share one network request. `capabilitiesApi.get` was
 * never given the same treatment, so the moment any caller is wired to it,
 * FIX-617's fix is bypassed and the duplicate-fetch defect returns.
 *
 * See `.knowledge/cards/20260922-2003-ISS-834.md`.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("./http", () => ({
  http: { get: vi.fn() },
}));

import { http } from "./http";
import { capabilitiesApi } from "./capabilities";

describe("capabilitiesApi.get (ISS-834)", () => {
  beforeEach(() => {
    vi.mocked(http.get).mockReset();
  });

  it("dedupes two concurrent calls into a single underlying request", async () => {
    vi.mocked(http.get).mockResolvedValue({
      data: { capabilities: [], model_catalog: [] },
    });

    await Promise.all([capabilitiesApi.get(), capabilitiesApi.get()]);

    expect(http.get).toHaveBeenCalledTimes(1);
  });
});
