/**
 * useSmoothText — the streaming-reply typewriter (quick-260719-rqo, Issue 2
 * part 1, shipped in 312271aa). This guard proves the three behaviours the lane
 * relies on, WITHOUT asserting the exact reveal rate (bounds, not counts, so the
 * test survives a rate tweak):
 *
 *   1. a STATIC target (never grows) is returned verbatim — no animation, no
 *      throw — under jsdom whether or not requestAnimationFrame exists;
 *   2. `enabled=false` returns the target verbatim even as it "grows" across
 *      rerenders (the animation is fully bypassed);
 *   3. a GROWING target, driven one frame at a time by a mocked
 *      requestAnimationFrame, reveals INCREMENTALLY toward the target — the shown
 *      text is always a PREFIX of the target and advances (it does NOT jump to the
 *      full target on the first frame for a large delta).
 */
import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useSmoothText } from "./useSmoothText";

describe("useSmoothText — streaming typewriter", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("Test 1: a static target is returned verbatim (no animation, no throw)", () => {
    const target = "a settled, historical line that never grows";
    const { result } = renderHook(() => useSmoothText(target));
    expect(result.current).toBe(target);
  });

  it("Test 2: enabled=false returns the target verbatim even as it grows", () => {
    const { result, rerender } = renderHook(
      ({ t }) => useSmoothText(t, false),
      { initialProps: { t: "ab" } },
    );
    expect(result.current).toBe("ab");
    // Even though the target grows across rerenders, the animation is bypassed —
    // the target is returned verbatim (no lag, no throw).
    rerender({ t: "abcdefghij" });
    expect(result.current).toBe("abcdefghij");
  });

  it("Test 3: a growing target reveals incrementally (prefix, advancing) under a mocked rAF", () => {
    // A single-step frame runner: requestAnimationFrame QUEUES the callback; a
    // frame is flushed manually. Because the tick re-schedules the NEXT frame via
    // requestAnimationFrame (which lands in the fresh queue), flushing ONE frame
    // advances the reveal by exactly one step — proving it is incremental, not a
    // synchronous run-to-completion (which a self-invoking rAF stub would give).
    let rafQueue: FrameRequestCallback[] = [];
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
      rafQueue.push(cb);
      return rafQueue.length;
    });
    vi.stubGlobal("cancelAnimationFrame", () => {});

    const flushOneFrame = () => {
      const due = rafQueue;
      rafQueue = [];
      act(() => {
        for (const cb of due) cb(0);
      });
    };

    const short = "hello";
    const long = `hello ${"x".repeat(60)}`; // 66 chars — a large delta

    const { result, rerender } = renderHook(({ t }) => useSmoothText(t), {
      initialProps: { t: short },
    });
    // Initially caught up (shown === the mounted target).
    expect(result.current).toBe(short);

    // The target grows: the effect schedules the first animation frame.
    rerender({ t: long });

    // One frame reveals a PREFIX that has advanced past the old length but is NOT
    // yet the full target (a large delta is spread across several frames).
    flushOneFrame();
    const afterOne = result.current;
    expect(long.startsWith(afterOne)).toBe(true);
    expect(afterOne.length).toBeGreaterThan(short.length);
    expect(afterOne.length).toBeLessThan(long.length);

    // A second frame advances further toward the target, still a prefix.
    flushOneFrame();
    const afterTwo = result.current;
    expect(long.startsWith(afterTwo)).toBe(true);
    expect(afterTwo.length).toBeGreaterThan(afterOne.length);
    expect(afterTwo.length).toBeLessThanOrEqual(long.length);
  });
});
