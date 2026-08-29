"use client";

/**
 * Adapted from nexu-io/open-design (Apache-2.0) — see /THIRD-PARTY-NOTICES.md
 *
 * useTabDeepLink — the nonce'd deep-link-into-tabs seam (open-design borrow #6,
 * Phase 31, CHATUI-01). Lifts open-design's `onRequestOpenFile(tabId)` →
 * `{ name, nonce }` → `setActiveTab` chain (`AssistantMessage.tsx:2385`,
 * `ProjectView.tsx:2423`, `FileWorkspace.tsx:1101`): a nonce'd callback chain
 * with no router / postMessage / custom-events.
 *
 * A result card (plan 04) calls `requestOpenTab(tab)`; the Preview panel (plan
 * 07) consumes the pending `{ tab, nonce }` in a `useEffect` and calls
 * `setActiveTab`. The nonce makes the target:
 *   - CONSUME-ONCE: `consume()` clears the pending target so a stale/replayed
 *     nonce cannot re-navigate (T-31-03-T);
 *   - RE-TRIGGERABLE: two successive requests to the SAME tab mint DIFFERENT
 *     nonces, so a repeat deep-link to an already-open tab still re-fires the
 *     consumer effect (a plain `{tab}` target would be referentially equal and
 *     the effect would not re-run).
 *
 * Tab ids are plain GENERIC strings (never a workflow/agent name — SC-001).
 */

import { useCallback, useRef, useState } from "react";

/** A single-use deep-link target: which tab to open + a fresh nonce. */
export interface TabDeepLinkTarget {
  /** Generic string tab id (e.g. "preview" / "steps" / "files" / "audit"). */
  tab: string;
  /** ISS-277: which agent inside that tab the request targets, when the URL named
   *  one (`/runs/{id}/steps/{agentId}`). An OPAQUE run-scoped id the consumer only
   *  matches against the run's own agent ids — never a workflow/agent name literal
   *  (SC-001). Undefined for every request that names no agent. */
  agentId?: string;
  /** Monotonic single-use token — different per request, even for the same tab. */
  nonce: number;
}

export interface UseTabDeepLinkReturn {
  /** The pending target the consumer navigates to, or null when nothing pending. */
  pending: TabDeepLinkTarget | null;
  /** Request opening a tab (optionally on a specific agent); mints a fresh nonce
   *  and sets it pending. */
  requestOpenTab: (tab: string, agentId?: string) => void;
  /** Read-and-clear the pending target (single-use). Returns null if nothing pending. */
  consume: () => TabDeepLinkTarget | null;
}

// Module-level monotonic nonce source: guarantees every request (across every
// hook instance) gets a strictly increasing, unique token.
let _globalNonce = 0;
function nextNonce(): number {
  return ++_globalNonce;
}

export function useTabDeepLink(): UseTabDeepLinkReturn {
  const [pending, setPending] = useState<TabDeepLinkTarget | null>(null);
  // Ref is the canonical source of truth so `consume()` reads-and-clears
  // synchronously (independent of React's state-flush timing).
  const pendingRef = useRef<TabDeepLinkTarget | null>(null);

  const requestOpenTab = useCallback((tab: string, agentId?: string) => {
    const target: TabDeepLinkTarget = { tab, agentId, nonce: nextNonce() };
    pendingRef.current = target;
    setPending(target);
  }, []);

  const consume = useCallback((): TabDeepLinkTarget | null => {
    const taken = pendingRef.current;
    if (taken === null) return null;
    pendingRef.current = null;
    setPending(null);
    return taken;
  }, []);

  return { pending, requestOpenTab, consume };
}
