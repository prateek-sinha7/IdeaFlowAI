import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// ─────────────────────────────────────────────────────────────────
// BUG-003: source-lock assertions for the reopen-revise wiring that is
// impractical to exercise in a unit render of the huge DashboardLayout —
// the sanctioned "grep-style source assertion" (mirrors
// revisionFamilyLinkage.source.test.ts).
//
//  1. handleRevisePpt's empty-content guard no longer blocks the REST path
//     when a parent run id (contentSourceRunId) exists.
//  2. the revise-handler selector binds to the VIEWED run's TYPE on a
//     completed reopen (so a reopened od_ppt run resolves handleRevisePpt).
//
// It ALSO re-pins the Revision-Families linkage tokens the guard relaxation
// must NOT disturb, so a future edit can't silently break the parent lineage.
// ─────────────────────────────────────────────────────────────────

const dashboardLayout = readFileSync(
  resolve(__dirname, "../../components/layout/DashboardLayout.tsx"),
  "utf8",
);

describe("DashboardLayout revise guard + viewed-run-type source (BUG-003)", () => {
  it("relaxes the handleRevisePpt empty-content guard to allow the REST path", () => {
    expect(dashboardLayout).toContain(
      "if (!contentSourceRunId && !pptxCode && !pptContent) return;",
    );
    // The old unconditional guard must be gone.
    expect(dashboardLayout).not.toContain("if (!pptxCode && !pptContent) return;");
  });

  it("binds the revise-handler selection to the viewed run's type on reopen", () => {
    expect(dashboardLayout).toContain(
      "recentRuns?.find((r) => r.id === contentSourceRunId)?.type",
    );
    expect(dashboardLayout).toContain("const effectiveReviseType = viewedRunType ?? workflowType;");
  });

  it("preserves the Revision-Families parent-linkage tokens (no regression)", () => {
    // The self-sufficient REST path — the guard relaxation must keep it intact.
    expect(dashboardLayout).toContain('postRevision(getToken() ?? "", contentSourceRunId,');
    // The History onRevise* callbacks still thread the per-run sourceRunId.
    expect(dashboardLayout).toContain("source_workflow_run_id: sourceRunId");
  });
});
