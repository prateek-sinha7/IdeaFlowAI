/**
 * figma-frame-store.ts — in-memory store for pending Figma frames.
 *
 * Why not sessionStorage?
 * sessionStorage has a ~5 MB limit per origin. Base64-encoding PNG frames
 * or a multi-page Figma PDF easily blows past that (QuotaExceededError).
 *
 * Why a module-level variable?
 * Next.js in-app navigation (router.push) never unloads the JS runtime, so a
 * module-level variable survives the wizard → dashboard transition. It is
 * consumed once (by page.tsx) and then cleared — no stale state.
 *
 * A sentinel key in sessionStorage tells page.tsx to look here:
 *   "prototype_v2.hasFigmaFrames" = "1"
 * The actual File objects live only here.
 */

import type { FigmaFrame } from "@/components/workflow/prototype/FigmaUploadSection";

let _pendingFrames: FigmaFrame[] = [];

export function setPendingFigmaFrames(frames: FigmaFrame[]): void {
  _pendingFrames = frames;
  // Sentinel: tells page.tsx to look in this store rather than sessionStorage.
  if (typeof window !== "undefined") {
    sessionStorage.setItem("prototype_v2.hasFigmaFrames", "1");
  }
}

export function getPendingFigmaFrames(): FigmaFrame[] {
  return _pendingFrames;
}

export function clearPendingFigmaFrames(): void {
  _pendingFrames = [];
  if (typeof window !== "undefined") {
    sessionStorage.removeItem("prototype_v2.hasFigmaFrames");
    sessionStorage.removeItem("prototype_v2.figmaFrames"); // legacy key cleanup
  }
}
