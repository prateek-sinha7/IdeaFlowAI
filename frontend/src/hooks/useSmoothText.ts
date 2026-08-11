"use client";

import { useEffect, useRef, useState } from "react";

/**
 * useSmoothText — reveal a GROWING text at a steady, smooth pace instead of the
 * coarse bursts the model/transport deliver it in (quick-260719-rqo, Issue 2).
 *
 * The Concierge reply streams as ~70-180-char Bedrock deltas (one `setMessages`
 * per delta → one visible jump), which reads as "jerky". As `target` grows the
 * shown text catches up a FRACTION of the outstanding buffer per animation frame,
 * so a burst renders as a smooth flow. The rate scales with how far behind we are,
 * so a big burst is revealed quickly and the tail eases in — never a visible lag.
 *
 * Each transcript row is its OWN MessageBubble (keyed by message.id), so within a
 * hook instance `target` only ever grows — no reset/rewind handling is needed. A
 * static (historical) message never grows, so it shows instantly. When disabled
 * or without requestAnimationFrame (jsdom under vitest), the target is returned
 * verbatim — degrade rather than animate/throw.
 *
 * Lint-clean: the progress ref is written ONLY inside the rAF callback / effect
 * (never during render), and setState happens ONLY inside the rAF callback.
 */
export function useSmoothText(target: string, enabled = true): string {
  const hasRaf = typeof requestAnimationFrame === "function";
  const [shown, setShown] = useState(target);
  const shownLenRef = useRef(target.length);

  useEffect(() => {
    if (!enabled || !hasRaf) return;

    // Reset the cursor when the target string changes in a way that makes our
    // current position invalid (e.g. a completely different message started
    // streaming, or the target was trimmed). Without this guard the rAF loop
    // skips the whole run because shownLenRef.current >= target.length even
    // though `shown` no longer matches `target`.
    if (shownLenRef.current > target.length) {
      shownLenRef.current = 0;
      setShown("");
    }

    if (shownLenRef.current >= target.length) return; // already caught up

    let raf = 0;
    let active = true; // guard: don't setShown after unmount / effect cleanup
    const tick = () => {
      if (!active) return;
      const curLen = shownLenRef.current;
      if (curLen >= target.length) {
        raf = 0;
        return;
      }
      const remaining = target.length - curLen;
      // Reveal ~1/6 of the outstanding buffer per frame (min 2 chars): a burst
      // smooths over a handful of frames and the rate scales with the backlog,
      // so later bursts / the stream ending never leave the text lagging behind.
      const advance = Math.max(2, Math.ceil(remaining / 6));
      const nextLen = Math.min(target.length, curLen + advance);
      shownLenRef.current = nextLen;
      setShown(target.slice(0, nextLen));
      raf = nextLen < target.length ? requestAnimationFrame(tick) : 0;
    };
    raf = requestAnimationFrame(tick);
    return () => {
      active = false;
      if (raf) cancelAnimationFrame(raf);
    };
  }, [target, enabled, hasRaf]);

  // Disabled / no-rAF: show the target verbatim (the effect never animates, so
  // `shown` would otherwise lag a growing target).
  return enabled && hasRaf ? shown : target;
}
