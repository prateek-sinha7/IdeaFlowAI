import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// ─────────────────────────────────────────────────────────────────
// BUG-012: source-lock assertions for the DURABLE viewed-run-type thread —
// the reopened od_ppt/od_prototype deck/prototype rendered BLANK because the
// PreviewPanel render dispatch keyed on a stale `workflowType` default. The fix
// threads the viewed run's REAL type end-to-end (fullRun.type → page.tsx
// contentSourceRunType → DashboardLayout viewedRunType → effectiveReviseType →
// PreviewPanel). Impractical to exercise in a full render of the huge page.tsx,
// so the sanctioned "grep-style source assertion" (mirrors
// contentSourceRunScope.source.test.ts / revisionFamilyLinkage.source.test.ts):
//
//  1. page.tsx SETS the durable type on reopen + CLEARS it on the fresh-launch reset.
//  2. DashboardLayout feeds `effectiveReviseType` (not the stale `workflowType`)
//     into the PreviewPanel render dispatch, and the old dispatch literal at that
//     PreviewPanel site is GONE.
// ─────────────────────────────────────────────────────────────────

const pageSource = readFileSync(
  resolve(__dirname, "../../app/dashboard/page.tsx"),
  "utf8",
);
const layoutSource = readFileSync(
  resolve(__dirname, "../../components/layout/DashboardLayout.tsx"),
  "utf8",
);

// Collapse whitespace runs to a single space so the JSX-site assertions are
// robust to indentation/line-wrap without loosening what they pin.
const layoutCollapsed = layoutSource.replace(/\s+/g, " ");

describe("BUG-012 durable viewed-run-type thread (source-lock)", () => {
  it("page.tsx declares the durable contentSourceRunType state", () => {
    expect(pageSource).toContain(
      "const [contentSourceRunType, setContentSourceRunType] = useState<WorkflowType | null>(null);",
    );
  });

  it("page.tsx SETS the viewed run's real type on reopen", () => {
    expect(pageSource).toContain("setContentSourceRunType(fullRun.type ?? null);");
  });

  it("page.tsx CLEARS the durable type on the fresh-launch reset", () => {
    expect(pageSource).toContain("setContentSourceRunType(null);");
  });

  it("page.tsx passes contentSourceRunType down to DashboardLayout", () => {
    expect(pageSource).toContain("contentSourceRunType={contentSourceRunType}");
  });

  it("DashboardLayout folds the durable type into viewedRunType", () => {
    expect(layoutCollapsed).toContain(
      "contentSourceRunType ?? recentRuns?.find((r) => r.id === contentSourceRunId)?.type",
    );
  });

  it("DashboardLayout feeds effectiveReviseType into the PreviewPanel render dispatch", () => {
    expect(layoutSource).toContain("workflowType={effectiveReviseType}");
  });

  it("DashboardLayout no longer keys the PreviewPanel dispatch on the stale workflowType", () => {
    // The PreviewPanel site is uniquely identified by the adjacent rawPipelineType
    // prop; the IdeaInputPage/ComposerPage `workflowType={workflowType}` sites are
    // intentionally left unchanged (they are NOT the render dispatch).
    expect(layoutCollapsed).not.toContain(
      "workflowType={workflowType} rawPipelineType={pipelineState?.pipeline_type || workflowType}",
    );
  });
});
