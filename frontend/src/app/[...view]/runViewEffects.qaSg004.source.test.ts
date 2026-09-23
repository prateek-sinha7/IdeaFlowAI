/**
 * QA-SG-004 / ISS-775 — the silent no-op when switching from one live run's
 * page to another's (bell panel, "N Running" dropdown, badge, History).
 *
 * T7 and T11 (page.tsx) are URL-driven, but their deps also carry
 * handleSelectWorkflowRun, whose identity changes on every click-driven
 * switch. That re-run still sees the OLD run's URL (the switch's router.push
 * has not committed) with trackedRunIdRef already on the NEW run, so it
 * re-seeded the old run — switchViewTo(old) made DashboardLayout's
 * pipelineRunId effect push the old URL, and Next discarded the pending push.
 *
 * page.tsx has no mount harness (see page.iss657.test.tsx), so this pins the
 * guard against the real source: each effect must bail on an already-applied
 * path BEFORE it can re-seed, and the record must be per-mount.
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";

const src = readFileSync(path.join(__dirname, "page.tsx"), "utf8");
const GUARD = "if (appliedRunViewKeyRef.current === viewPathKey) return;";

function effectBody(startMarker: string, depsMarker: string): string {
  const start = src.indexOf(startMarker);
  expect(start).toBeGreaterThan(-1);
  const end = src.indexOf(depsMarker, start);
  expect(end).toBeGreaterThan(start);
  return src.slice(start, end);
}

describe("ISS-775 — T7/T11 act on a route change only", () => {
  it.each([
    ["T7", "const runId = reopenedRunIdFor(parsedView);", "}, [viewPathKey, isAuthenticated, handleSelectWorkflowRun, runTabDeepLink.requestOpenTab]);"],
    ["T11", "const runId = liveStreamRunIdFor(parsedView);", "}, [viewPathKey, isAuthenticated, handleSelectWorkflowRun]);"],
  ])("%s bails on an already-applied path before it can re-seed a run", (_name, startMarker, depsMarker) => {
    const body = effectBody(startMarker, depsMarker);
    const guardAt = body.indexOf(GUARD);
    expect(guardAt).toBeGreaterThan(-1);
    // Both re-seed paths: the liveRunIds fast path and the full reopen.
    expect(guardAt).toBeLessThan(body.indexOf("runConnection.liveRunIds.includes(runId)"));
    expect(guardAt).toBeLessThan(body.indexOf("handleSelectWorkflowRun({ id: runId }"));
    expect(body).toContain("appliedRunViewKeyRef.current = viewPathKey;");
  });

  it("records the applied path per mount, so a real navigation's remount still applies its URL", () => {
    expect(src).toContain("const appliedRunViewKeyRef = useRef<string | null>(null);");
    expect(src).not.toMatch(/^(let|const|var)\s+appliedRunViewKey/m);
  });
});
