import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { RefObject } from "react";

import {
  VIRTUALIZE_THRESHOLD,
  useMeasuredVirtualWindow,
  type ScrollSurface,
} from "./useMeasuredVirtualWindow";

// ─── open-design borrow #5 (31-02 Task 2) — measured virtual window ───────────
// Depends only on a scroll ref + item count + a measured-height map. Below the
// threshold virtualization disengages; above it, only a windowed slice renders.

function scrollRef(scrollTop: number, clientHeight: number): RefObject<ScrollSurface | null> {
  // Plain mock surface: no addEventListener, so the scroll subscription is a
  // no-op and the window is a pure function of the injected scroll inputs.
  return { current: { scrollTop, clientHeight } };
}

describe("useMeasuredVirtualWindow", () => {
  it("exposes VIRTUALIZE_THRESHOLD = 80", () => {
    expect(VIRTUALIZE_THRESHOLD).toBe(80);
  });

  it("disengages below the threshold: full range, zero spacers", () => {
    const { result } = renderHook(() =>
      useMeasuredVirtualWindow({
        itemCount: 80,
        scrollRef: scrollRef(0, 600),
        estimateHeight: 100,
      }),
    );
    expect(result.current.startIndex).toBe(0);
    expect(result.current.endIndex).toBe(80);
    expect(result.current.topSpacer).toBe(0);
    expect(result.current.bottomSpacer).toBe(0);
  });

  it("above the threshold returns only a windowed slice; spacers sum to the off-window height", () => {
    const itemCount = 200;
    const estimateHeight = 100; // total = 20000
    const scrollTop = 5000;
    const clientHeight = 600;
    const { result } = renderHook(() =>
      useMeasuredVirtualWindow({
        itemCount,
        scrollRef: scrollRef(scrollTop, clientHeight),
        estimateHeight,
        overscan: 2,
      }),
    );

    // A slice, not the whole list.
    expect(result.current.startIndex).toBeGreaterThan(0);
    expect(result.current.endIndex).toBeLessThan(itemCount);
    expect(result.current.endIndex - result.current.startIndex).toBeLessThan(30);

    // First visible item at scrollTop=5000 with 100px rows is index 50; with
    // overscan 2 → startIndex 48. topSpacer = 48 * 100 = 4800.
    expect(result.current.startIndex).toBe(48);
    expect(result.current.topSpacer).toBe(4800);

    // Spacers + rendered slice height reconstruct the full scroll height.
    const total = itemCount * estimateHeight;
    const rendered =
      (result.current.endIndex - result.current.startIndex) * estimateHeight;
    expect(result.current.topSpacer + result.current.bottomSpacer).toBe(
      total - rendered,
    );
  });

  it("measure(index, height) updates the height model so a later window uses the measured height", () => {
    const itemCount = 200;
    const { result } = renderHook(() =>
      useMeasuredVirtualWindow({
        itemCount,
        scrollRef: scrollRef(5000, 600),
        estimateHeight: 100,
        overscan: 0,
      }),
    );

    // Estimate-only: 100px rows, scrollTop 5000 → first visible index 50.
    expect(result.current.startIndex).toBe(50);

    // Grow item 0 from the 100px estimate to 300px (+200). Everything below it
    // shifts down by 200px, so at the same scrollTop two fewer rows sit above
    // the fold → startIndex drops from 50 to 48. This proves the SUBSEQUENT
    // window read the MEASURED height, not the estimate.
    act(() => {
      result.current.measure(0, 300);
    });
    expect(result.current.startIndex).toBe(48);
  });

  it("is deterministic: identical scroll inputs yield identical windows", () => {
    const opts = {
      itemCount: 300,
      scrollRef: scrollRef(12345, 720),
      estimateHeight: 80,
      overscan: 3,
    };
    const a = renderHook(() => useMeasuredVirtualWindow(opts)).result.current;
    const b = renderHook(() => useMeasuredVirtualWindow(opts)).result.current;
    expect(a.startIndex).toBe(b.startIndex);
    expect(a.endIndex).toBe(b.endIndex);
    expect(a.topSpacer).toBe(b.topSpacer);
    expect(a.bottomSpacer).toBe(b.bottomSpacer);
  });
});
