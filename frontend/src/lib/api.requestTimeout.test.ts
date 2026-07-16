import { afterEach, describe, expect, it, vi } from "vitest";
import { getWorkflow } from "@/lib/api";

// ─────────────────────────────────────────────────────────────────
// BUG-013 Part B (260716-r7d) — the REST client `request()` must fail-fast on a
// starved/hung call (a saturated ~6-per-origin pool leaves the reopen GET with
// no free socket) instead of hanging into a silent idle screen. `request()`
// wraps its fetch in a ~30s AbortController; on abort it rejects with a typed,
// catchable error. Clones the global-fetch mock idiom from
// api.getRunArtifacts.test.ts, plus fake timers to fast-forward the timeout.
//
// The stub honors the AbortSignal (mirrors real fetch: an aborted signal rejects
// with an AbortError) so the assertion exercises the real timeout path.
// ─────────────────────────────────────────────────────────────────

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("request() abort timeout (BUG-013 Part B)", () => {
  it(
    "rejects with a typed timeout/abort error when fetch never resolves",
    async () => {
      vi.useFakeTimers();

      // A fetch that NEVER resolves on its own — it only settles if the passed
      // AbortSignal fires (as a real fetch does). FAIL-BEFORE: request() passes
      // no signal, so this promise stays pending forever and the assertion hits
      // the per-test 3000ms cap — RED. GREEN: request()'s 30s AbortController
      // aborts the signal → this rejects → request() translates to ApiError.
      const fetchMock = vi.fn(
        (_url: string, opts?: RequestInit) =>
          new Promise((_resolve, reject) => {
            const signal = opts?.signal;
            if (signal) {
              signal.addEventListener("abort", () => {
                reject(
                  new DOMException("The operation was aborted.", "AbortError"),
                );
              });
            }
          }),
      );
      vi.stubGlobal("fetch", fetchMock);

      const promise = getWorkflow("tok", "run-x");
      const assertion = expect(promise).rejects.toThrow(/timeout|aborted/i);

      await vi.advanceTimersByTimeAsync(30_000);
      await assertion;
    },
    3000,
  );
});
