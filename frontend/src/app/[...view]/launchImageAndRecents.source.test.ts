import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// ─────────────────────────────────────────────────────────────────
// 260710-ftq: source-lock assertions for two frontend wiring fixes that
// are impractical to exercise in a unit render (the huge page.tsx /
// DashboardLayout). The sanctioned "grep-style source assertion" idiom,
// mirroring revisionFamilyLinkage.source.test.ts.
//
//   DEFECT 1 — the prototype + ppt launch-staging setters now carry the
//   attached `images` through to pendingOd*Params (length-guarded so an
//   image-less launch stays byte-identical, INV-3 dormancy).
//   DEFECT 2 — the Home "Recent runs" chip switches the shell to the
//   execution view on open.
// ─────────────────────────────────────────────────────────────────

const dashboardPage = readFileSync(resolve(__dirname, "./page.tsx"), "utf8");
const dashboardLayout = readFileSync(
  resolve(__dirname, "../../components/layout/DashboardLayout.tsx"),
  "utf8",
);

describe("dashboard page.tsx launch-staging image carry (DEFECT 1)", () => {
  it("spreads images through the launch setters, length-guarded", () => {
    expect(dashboardPage).toContain(
      "pending.images && pending.images.length > 0 ? { images: pending.images }",
    );
  });

  it("keeps a floor of 2 length-guarded images spreads, one per launch setter (prototype + ppt)", () => {
    // A FLOOR, not an exact count (ISS-867). The two launch setters,
    // setPendingOdProtoParams and setPendingOdPptParams, each carry one
    // length-guarded images spread. Below 2 means a setter dropped its images;
    // a legitimate new reader of pending.images elsewhere must not turn this
    // red. Raise the floor when a launch setter is added, lower it only when
    // one is deliberately removed.
    expect(
      dashboardPage.split("pending.images && pending.images.length > 0").length - 1,
    ).toBeGreaterThanOrEqual(2);
  });
});

describe("DashboardLayout recents chip opens the run (DEFECT 2)", () => {
  it("switches to the execution view alongside onSelectWorkflowRun", () => {
    expect(dashboardLayout).toContain(
      'onSelectWorkflowRun?.(run); setMainView("execution")',
    );
  });
});
