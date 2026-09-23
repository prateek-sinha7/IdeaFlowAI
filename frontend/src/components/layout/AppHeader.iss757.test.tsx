/**
 * ISS-757 / ISS-771 — QA-SG-007: notification bell shows "No notifications
 * yet" on the first open after a page reload even when pipelines are
 * actively running, and the header's own single-run badge / "N Running"
 * dropdown render nothing at all during the same window.
 *
 * Root cause (see ISS-757 card, "Mechanism (root cause)" / "Analysis"):
 * `AppHeader.tsx:186` computes `hasServerData = recentRuns.length > 0` and
 * uses it (`:187`) to decide whether to trust `recentRuns` at all. On a full
 * page reload with runs that were already in flight before the reload,
 * `recentRuns` starts empty and only becomes non-empty once `page.tsx`'s own
 * fetch resolves — so for one or more renders, `hasServerData` is `false`
 * even though runs ARE live server-side, and there is no way for AppHeader to
 * tell "not fetched yet" from "confirmed zero" from `recentRuns=[]` alone.
 * The documented fallback (`useNotifications`) is also empty for the same
 * window (FIX-204 drops "running"/"gate" entries at hydration; SSE resume
 * never redelivers `pipeline_start` for an already-in-flight backgrounded
 * run), so BOTH sources agree on a confidently wrong empty answer.
 *
 * The card's prescribed fix: thread a `recentRunsLoaded`-style boolean signal
 * down from `page.tsx` (the only place that knows the initial fetch is still
 * in flight) and use it at `:186-187` to suppress the confident-empty render
 * until the fetch has actually resolved. `runningPipelines` (built from
 * `hasServerData`) drives all three affected render sites in this file:
 * - ISS-757: `AppHeader.tsx:482` — `NotificationPanel`'s `liveRuns` prop.
 * - ISS-771: `AppHeader.tsx:304` / `:349` — the single-run badge and the
 *   "N Running" dropdown, which render NOTHING (not a wrong count) for the
 *   same window since both `=== 1` and `> 1` are false against `.length` 0.
 *
 * No harness can reliably reproduce the timing race itself (ISS-757's own
 * live repro landed the empty state on only 1 of 3 cold-reload attempts), so
 * these tests pin the defect directly against the real derivation AppHeader
 * uses to decide "trust recentRuns yet or not" — the same approach already
 * used in this file's sibling ISS-769 test for the same class of race.
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";

function readAppHeaderSource() {
  return readFileSync(path.join(__dirname, "AppHeader.tsx"), "utf8");
}

describe("AppHeader — ISS-757 hasServerData race (QA-SG-007)", () => {
  it(
    "does not decide recentRuns is trustworthy from length alone — it must know whether the fetch has actually resolved",
    () => {
      const src = readAppHeaderSource();

      const match = src.match(/const hasServerData = ([^;]+);/);
      expect(match, "expected a `hasServerData` derivation in AppHeader.tsx").not.toBeNull();

      const rhs = match![1];

      // Today: `recentRuns.length > 0` — indistinguishable from "not fetched
      // yet". The bug is exactly this: a fresh mount with runs already live
      // server-side renders the same `hasServerData === false` as a mount
      // with genuinely zero runs.
      expect(rhs.trim()).not.toBe("recentRuns.length > 0");

      // Expected/correct behaviour: some loaded/resolved signal (the card
      // names it `recentRunsLoaded`) must gate the confident-empty branch,
      // so a reload with in-flight runs does not render as if there were
      // none until the fetch has actually come back.
      expect(rhs).toMatch(/loaded/i);
    },
  );
});

describe("AppHeader — ISS-771 badge/dropdown render nothing during the same race", () => {
  it(
    "gates the single-run badge and 'N Running' dropdown on the same loaded-aware signal as the notification panel",
    () => {
      const src = readAppHeaderSource();

      // Both render sites read `runningPipelines`, which is built from
      // `liveRuns` (`hasServerData ? liveRunsFromServer : null`). Confirm
      // both conditions are still wired to that same array...
      expect(src).toMatch(/runningPipelines\.length === 1/);
      expect(src).toMatch(/runningPipelines\.length > 1/);

      // ...and that the array's own upstream gate is loaded-aware (not the
      // bare `recentRuns.length > 0` this card and ISS-757 both name as the
      // root cause) — so during the race window the badge/dropdown do not
      // silently render nothing while runs are actually live.
      const match = src.match(/const hasServerData = ([^;]+);/);
      expect(match, "expected a `hasServerData` derivation in AppHeader.tsx").not.toBeNull();
      expect(match![1]).toMatch(/loaded/i);
    },
  );
});
