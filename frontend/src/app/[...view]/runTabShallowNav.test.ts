/**
 * BUG-030 — clicking a run tab (Steps/Files/Workspace/Audit) flashed Preview
 * for ~1s before jumping to the clicked tab.
 *
 * A tab click was a full `router.push`, which changes the [...view] catch-all
 * params and REMOUNTS page.tsx — wiping every page-local run state and forcing
 * a re-fetch/durable replay. PreviewPanel remounted on its "preview" default
 * and only re-applied the tab from the fetch's `.finally()` deep-link request.
 *
 * The fix is a shallow URL update (window.history.pushState), which Next's
 * app-router patches to update usePathname WITHOUT touching the router tree.
 * These three guards are what keep it shallow — a regression on any one of
 * them brings the flash back.
 */

import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const pageSource = readFileSync(resolve(__dirname, "page.tsx"), "utf8");
const dashboardSource = readFileSync(
  resolve(__dirname, "../../components/layout/DashboardLayout.tsx"),
  "utf8",
);

function tabSelectBody(): string {
  const start = dashboardSource.indexOf("const handlePreviewPanelTabSelect = useCallback(");
  expect(start).toBeGreaterThan(-1);
  const end = dashboardSource.indexOf("}, [contentSourceRunId]);", start);
  expect(end).toBeGreaterThan(start);
  // Comments in this handler name `router.push` as the thing it must NOT do,
  // so strip them before asserting on what it actually calls.
  return dashboardSource
    .slice(start, end)
    .split("\n")
    .filter((l) => !l.trim().startsWith("//"))
    .join("\n");
}

describe("BUG-030 — run tab switching stays shallow", () => {
  it("the tab handler pushes history directly, never through the router", () => {
    const body = tabSelectBody();
    expect(body).toContain("window.history.pushState");
    expect(body).not.toContain("router.push");
  });

  it("page.tsx reads the path from usePathname, not useParams", () => {
    // useParams is fed by the router tree, which pushState deliberately leaves
    // alone — params-derived routing would go stale on every tab switch.
    expect(pageSource).toContain("const pathname = usePathname();");
    expect(pageSource).toMatch(/import \{[^}]*usePathname[^}]*\} from "next\/navigation";/);
    expect(pageSource).not.toMatch(/import \{[^}]*useParams[^}]*\} from "next\/navigation";/);
  });

  it("the already-tracked run branch still applies the URL's tab", () => {
    // With no remount, this early return is the ONLY branch a tab click and
    // the back/forward after it reach — so it has to mint the deep link.
    const start = pageSource.indexOf("if (runId === trackedRunIdRef.current) {");
    expect(start).toBeGreaterThan(-1);
    const branch = pageSource.slice(start, pageSource.indexOf("\n    }", start));
    expect(branch).toContain("reopenTabFor(parsedView.screen)");
    // ISS-277 widened the seam: the request now also carries the agent the path
    // names (`/runs/{id}/steps/{agentId}`). The guard is unchanged in intent —
    // this branch must still mint the deep link for the URL's tab — the call it
    // pins simply grew that second argument.
    expect(branch).toContain(
      "runTabDeepLink.requestOpenTab(openTab, deepLinkAgentIdFor(parsedView))",
    );
  });
});
