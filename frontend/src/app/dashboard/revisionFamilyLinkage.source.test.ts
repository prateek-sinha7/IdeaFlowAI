import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// ─────────────────────────────────────────────────────────────────
// Revision Families (B1): source-lock assertions for the wiring that is
// impractical to exercise in a unit render (the huge DashboardLayout /
// page.tsx). These pin the exact linkage the two implementation tasks
// produced — the sanctioned "grep-style source assertion".
// ─────────────────────────────────────────────────────────────────

const dashboardLayout = readFileSync(
  resolve(__dirname, "../../components/layout/DashboardLayout.tsx"),
  "utf8",
);
const dashboardPage = readFileSync(resolve(__dirname, "./page.tsx"), "utf8");

describe("DashboardLayout revision linkage source", () => {
  it("removed the fragile currentWorkflowRunId heuristic", () => {
    expect(dashboardLayout).not.toContain('workflowType + "_revision"');
    expect(dashboardLayout).not.toContain("const currentWorkflowRunId");
  });

  it("sources every linkage path from contentSourceRunId / sourceRunId", () => {
    // Inline handlers read the prop; the ppt run_revision uses parent_run_id.
    expect(dashboardLayout).toContain("parent_run_id: contentSourceRunId");
    expect(dashboardLayout).toContain("source_workflow_run_id: contentSourceRunId");
    // History onRevise* callbacks thread the per-run sourceRunId.
    expect(dashboardLayout).toContain("source_workflow_run_id: sourceRunId");
  });
});

describe("dashboard page.tsx contentSourceRunId lifecycle", () => {
  it("sets the source on live completion and reopen, clears on fresh run", () => {
    expect(dashboardPage).toContain("setContentSourceRunId(data.pipeline_run_id");
    expect(dashboardPage).toContain("setContentSourceRunId(fullRun.id)");
    expect(dashboardPage).toContain("setContentSourceRunId(null)");
  });

  it("passes contentSourceRunId down to DashboardLayout", () => {
    expect(dashboardPage).toContain("contentSourceRunId={contentSourceRunId}");
  });
});
