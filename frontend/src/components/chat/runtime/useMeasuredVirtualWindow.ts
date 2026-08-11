/**
 * useMeasuredVirtualWindow — a ResizeObserver-measured virtual window over a
 * long transcript (open-design borrow #5).
 *
 * Adapted from nexu-io/open-design (Apache-2.0) — see /THIRD-PARTY-NOTICES.md
 *
 * Clean-room reimplementation (from the behavioral spec, no build-time dep on
 * open-design source) of upstream `useMeasuredVirtualWindow`
 * (`ChatPane.tsx:3059`) + `CHAT_MESSAGE_VIRTUALIZE_THRESHOLD = 80`
 * (`ChatPane.tsx:663`). Custom virtualization, no library.
 *
 * The hook depends ONLY on a scroll ref + an item count + a per-index measured
 * height map. The windowing math is pure: it reads `scrollTop`/`clientHeight`
 * off the passed ref and returns the visible slice + top/bottom spacers, so a
 * >80-message list renders only its visible window (T-31-02-D DoS mitigation).
 * The consuming component owns the `ResizeObserver` and feeds real heights back
 * via `measure(index, height)`; below the threshold virtualization disengages
 * and the full range renders (the kit's naive auto-scroll stays for small
 * transcripts).
 */

import { useCallback, useEffect, useReducer, useRef } from "react";
import type { RefObject } from "react";

/** Above this many messages the measured virtual window engages. */
export const VIRTUALIZE_THRESHOLD = 80;

/** The minimal scroll surface the hook reads — a real element satisfies this. */
export interface ScrollSurface {
  scrollTop: number;
  clientHeight: number;
  addEventListener?: (
    type: "scroll",
    listener: () => void,
    options?: AddEventListenerOptions,
  ) => void;
  removeEventListener?: (type: "scroll", listener: () => void) => void;
}

export interface MeasuredVirtualWindowOptions {
  itemCount: number;
  scrollRef: RefObject<ScrollSurface | null>;
  /** Estimated row height (px) — a number, or a per-index function. */
  estimateHeight: number | ((index: number) => number);
  /** Extra rows rendered above/below the viewport to hide seams. */
  overscan?: number;
}

export interface MeasuredVirtualWindow {
  startIndex: number;
  /** Exclusive upper bound — render `items.slice(startIndex, endIndex)`. */
  endIndex: number;
  topSpacer: number;
  bottomSpacer: number;
  /** Feed a measured height for an index (from a ResizeObserver). */
  measure: (index: number, height: number) => void;
}

/**
 * Pure windowing math. Kept a free function (not exported) so the hook stays a
 * thin ref-reading shell and the math is deterministic given the same inputs.
 */
function computeWindow(
  itemCount: number,
  scrollTop: number,
  viewport: number,
  heights: Map<number, number>,
  estimate: (index: number) => number,
  overscan: number,
): Omit<MeasuredVirtualWindow, "measure"> {
  // Prefix offsets: prefix[i] = top of item i; prefix[itemCount] = total height.
  const prefix = new Array<number>(itemCount + 1);
  prefix[0] = 0;
  for (let i = 0; i < itemCount; i++) {
    const h = heights.get(i) ?? estimate(i);
    prefix[i + 1] = prefix[i] + h;
  }
  const total = prefix[itemCount];
  const bottom = scrollTop + viewport;

  // First item whose BOTTOM is past the top edge → first visible.
  let firstVisible = itemCount;
  for (let i = 0; i < itemCount; i++) {
    if (prefix[i + 1] > scrollTop) {
      firstVisible = i;
      break;
    }
  }
  // First item whose TOP is at/below the bottom edge → first fully off-window.
  let firstBelow = itemCount;
  for (let i = 0; i < itemCount; i++) {
    if (prefix[i] >= bottom) {
      firstBelow = i;
      break;
    }
  }

  let startIndex = Math.max(0, firstVisible - overscan);
  let endIndex = Math.min(itemCount, firstBelow + overscan);
  if (endIndex <= startIndex) endIndex = Math.min(itemCount, startIndex + 1);

  return {
    startIndex,
    endIndex,
    topSpacer: prefix[startIndex],
    bottomSpacer: total - prefix[endIndex],
  };
}

export function useMeasuredVirtualWindow(
  options: MeasuredVirtualWindowOptions,
): MeasuredVirtualWindow {
  const { itemCount, scrollRef, estimateHeight, overscan = 5 } = options;

  const heights = useRef<Map<number, number>>(new Map());
  // A version counter forces a recompute on scroll or on a new measurement.
  const [, bump] = useReducer((n: number) => n + 1, 0);

  const measure = useCallback((index: number, height: number) => {
    const prev = heights.current.get(index);
    if (prev !== height) {
      heights.current.set(index, height);
      bump();
    }
  }, []);

  // Subscribe to the scroll surface so the window recomputes as the user
  // scrolls. Guarded so a plain mock ref (no addEventListener) is a no-op.
  // Use a ref to the scroll element captured at mount time — depending on
  // `scrollRef` (the ref OBJECT) in the dependency array means the effect never
  // re-runs after mount, but scrollRef.current may not yet be set. We instead
  // capture scrollRef.current inside the effect body (run after mount) and store
  // the unsub in a cleanup. A `requestAnimationFrame` gate batches scroll events
  // so a layout shift caused by a bump()-induced re-render cannot synchronously
  // fire the scroll handler again and create an infinite loop.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || typeof el.addEventListener !== "function") return;
    let rafId = 0;
    const onScroll = () => {
      if (rafId) return; // already queued — coalesce
      rafId = requestAnimationFrame(() => {
        rafId = 0;
        bump();
      });
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      el.removeEventListener?.("scroll", onScroll);
      if (rafId) cancelAnimationFrame(rafId);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const estimate =
    typeof estimateHeight === "function"
      ? estimateHeight
      : () => estimateHeight;

  // Below the threshold virtualization disengages: full range, zero spacers.
  if (itemCount <= VIRTUALIZE_THRESHOLD) {
    return {
      startIndex: 0,
      endIndex: itemCount,
      topSpacer: 0,
      bottomSpacer: 0,
      measure,
    };
  }

  const el = scrollRef.current;
  const scrollTop = el?.scrollTop ?? 0;
  const viewport = el?.clientHeight ?? 0;

  const window = computeWindow(
    itemCount,
    scrollTop,
    viewport,
    heights.current,
    estimate,
    overscan,
  );

  return { ...window, measure };
}
