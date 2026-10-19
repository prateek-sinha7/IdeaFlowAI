/**
 * QA-SG-004 — switching between parallel workflow runs from the notification
 * bar (and its sibling entry points) is unreliable once a SECOND live-to-live
 * switch happens: the first `/dashboard` -> live run click always works, but
 * switching again from an already-viewed live run's own `/runs/<id>/stream`
 * page silently no-ops or lands several seconds late.
 *
 * Root cause (`.knowledge/cards/20260922-1330-ISS-775.md`, confirmed by direct
 * code read): every call site below fires `onSwitchToLiveRun`/an equivalent
 * switch WITHOUT awaiting it, then calls `router.push` unconditionally. The
 * push remounts `page.tsx` under the shared `[...view]` catch-all (confirmed
 * live, `page.tsx:3374-3378`), which replaces `trackedRunIdRef`'s ref OBJECT
 * and flips `useRunStateStore`'s `mountedRef` to false mid-replay — so the
 * pre-remount instance's in-flight `getRunEvents` write usually lands in a
 * throwaway object instead of applying, and there is no guard anywhere that
 * detects "a switch is already in flight" before the push fires.
 *
 * Each test below reads the real, current source of one call site named by
 * one card and asserts a re-entrancy/in-flight guard exists there. None do
 * today, so every test fails now, for the reason each card names — not on a
 * selector or fixture error, since these tests never mount the app at all
 * (`page.tsx` has no harness for its `use()`-based async route params, auth
 * bootstrap and SSE wiring — see `page.iss657.test.tsx`'s own note on why a
 * source-level assertion is the narrowest test that still fails on the real
 * defect instead of on invented plumbing).
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";

const dashboardLayoutSrc = readFileSync(
  path.join(__dirname, "../../components/layout/DashboardLayout.tsx"),
  "utf8",
);
const appHeaderSrc = readFileSync(
  path.join(__dirname, "../../components/layout/AppHeader.tsx"),
  "utf8",
);
const pageSrc = readFileSync(path.join(__dirname, "page.tsx"), "utf8");

/** Same generic guard-detection ISS-657 already used for this exact defect shape. */
function hasInFlightGuard(body: string): boolean {
  return (
    /trackedRunIdRef\.current\s*!==/.test(body) ||
    /\.aborted\b/i.test(body) ||
    /generation/i.test(body) ||
    /await\s+onSwitchToLiveRun/.test(body) ||
    /await\s+on(GoToPipeline|SelectWorkflowRun)/.test(body)
  );
}

describe("ISS-775 — bell panel onViewResults (DashboardLayout.tsx) has no in-flight switch guard", () => {
  it(
    "ISS-775 — the live/gate branch of onViewResults must not push before a prior switch has settled",
    () => {
      const start = dashboardLayoutSrc.indexOf("onViewResults={(n) => {");
      expect(start).toBeGreaterThan(-1);
      const end = dashboardLayoutSrc.indexOf('} else if (n.status === "completed")', start);
      expect(end).toBeGreaterThan(start);
      const body = dashboardLayoutSrc.slice(start, end);

      // Sanity: this is genuinely the live-switch-then-push shape the card
      // describes — if these markers move, the slice is no longer the right
      // branch and this test would pass/fail for the wrong reason.
      expect(body).toContain("onSwitchToLiveRun(targetRunId)");
      expect(body).toContain("router.push(routes.runStream(targetRunId))");

      expect(hasInFlightGuard(body)).toBe(true);
    },
  );
});

describe("ISS-778 — header dropdown/badge (AppHeader.handleRunClick, DashboardLayout.onGoToPipeline) share the same unguarded shape", () => {
  it(
    "ISS-778 — handleRunClick must not switch-then-navigate without a re-entrancy guard",
    () => {
      const start = appHeaderSrc.indexOf("const handleRunClick = (run: WorkflowRun) => {");
      expect(start).toBeGreaterThan(-1);
      const end = appHeaderSrc.indexOf("\n  };", start);
      expect(end).toBeGreaterThan(start);
      const body = appHeaderSrc.slice(start, end);

      expect(body).toContain("onSwitchToLiveRun(run.id)");
      expect(body).toContain("onGoToPipeline?.(run.id)");

      expect(hasInFlightGuard(body)).toBe(true);
    },
  );

  it(
    "ISS-778 — onGoToPipeline (DashboardLayout.tsx) must not push before a prior switch has settled",
    () => {
      const start = dashboardLayoutSrc.indexOf("onGoToPipeline={(clickedRunId) => {");
      expect(start).toBeGreaterThan(-1);
      const end = dashboardLayoutSrc.indexOf("onSwitchToLiveRun={(runId) => {", start);
      expect(end).toBeGreaterThan(start);
      const body = dashboardLayoutSrc.slice(start, end);

      expect(body).toContain("onSwitchToLiveRun?.(runId)");
      expect(body).toContain("router.push(routes.runStream(runId))");

      expect(hasInFlightGuard(body)).toBe(true);
    },
  );
});

describe("ISS-779 — handleSelectWorkflowRun (page.tsx) carries no trackedRunIdRef-style guard at all", () => {
  it(
    "ISS-779 — handleSelectWorkflowRun must bail when a newer switch has superseded it",
    () => {
      const start = pageSrc.indexOf("const handleSelectWorkflowRun = useCallback(");
      expect(start).toBeGreaterThan(-1);
      const depsMarker =
        "[runStore.viewed.pipelineState.pipelineRunId, resetPipeline, setWaveGroups, handleWebSocketMessage, setSubmittedBrief, seedRunChatTranscript, runConnection]";
      const end = pageSrc.indexOf(depsMarker, start);
      expect(end).toBeGreaterThan(start);
      const body = pageSrc.slice(start, end);

      // Sanity: genuinely the two-phase async reopen path the card describes.
      expect(body).toContain("trackedRunIdRef.current = run.id");
      expect(body).toContain("getRunEvents(");

      // ISS-779 unfixed: `trackedRunIdRef.current` is WRITTEN in this function
      // (to claim the switch) but never READ back to check it is still current
      // before durable frames are applied — zero `!==` comparisons anywhere in
      // the body, unlike its sibling `handleSwitchToLiveRun` (ISS-657/page.tsx:2765).
      expect(hasInFlightGuard(body)).toBe(true);
    },
  );
});

describe("ISS-780 — the in-flight switch guard is per-mount (useRef), not module-scope, so it cannot see across the page.tsx remount", () => {
  it(
    "ISS-780 — the guard protecting a live-to-live switch must survive a page.tsx remount",
    () => {
      const declStart = pageSrc.indexOf("const trackedRunIdRef = useRef<string | null>(null);");
      expect(declStart).toBeGreaterThan(-1);

      // Confirms the guard is declared INSIDE the component function (a React
      // hook call), not at module scope — so `router.push`'s remount
      // (page.tsx:3374-3378, "a fresh render-instance id appears right after
      // router.push") replaces the ref object itself and the guard forgets
      // every switch the previous instance had in flight.
      const componentStart = pageSrc.lastIndexOf("\nfunction ", declStart);
      const componentIsModuleScope = componentStart === -1;
      expect(componentIsModuleScope).toBe(false);

      // ISS-780 unfixed: no module-scope (outside any component function)
      // generation counter or switch-id guards the replay-vs-remount race —
      // only this per-instance ref exists.
      const moduleScopeGuard =
        /^const\s+\w*[Ss]witch(Generation|Guard|Id)\w*\s*=/m.test(pageSrc) ||
        /^let\s+\w*[Ss]witch(Generation|Guard|Id)\w*\s*=/m.test(pageSrc);
      expect(moduleScopeGuard).toBe(true);
    },
  );
});
