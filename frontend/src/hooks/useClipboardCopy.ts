"use client";

/**
 * useClipboardCopy — the shared, guarded clipboard write behind every Copy
 * button in the app.
 *
 * ISS-331: every call site re-wrote its own `navigator.clipboard.writeText`
 * with no failure path at all. Two shapes existed, both broken: `await`/
 * `.then()` with no `catch` (a rejection leaves the button silent forever and
 * the rejection unhandled — the reported hook-detail symptom), and
 * fire-and-forget with an unconditional `setCopied(true)` (the button claims
 * "Copied" for a write that never landed).
 *
 * One guard here instead of one per call site: `copied` only flips once the
 * write actually resolves, and a rejection sets `failed` so the button can say
 * so with the same inline label-swap idiom it already uses for `copied`.
 */

import { useCallback, useEffect, useRef, useState } from "react";

export function useClipboardCopy(resetMs = 2000) {
  const [copied, setCopied] = useState(false);
  const [failed, setFailed] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (timerRef.current) clearTimeout(timerRef.current);
  }, []);

  const copy = useCallback(async (text: string) => {
    let ok = true;
    try {
      // Throws synchronously when the API is absent, rejects when it is denied.
      await navigator.clipboard.writeText(text);
    } catch {
      ok = false;
    }
    setCopied(ok);
    setFailed(!ok);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      setCopied(false);
      setFailed(false);
    }, resetMs);
    return ok;
  }, [resetMs]);

  return { copied, failed, copy };
}
