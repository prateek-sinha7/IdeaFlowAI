import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// ─────────────────────────────────────────────────────────────────
// BUG-011: source-lock assertions for the run-scoped `pipeline_complete`
// content-source guard — impractical to exercise in a full render of the huge
// page.tsx, so the sanctioned "grep-style source assertion" (mirrors
// reviseGuard.source.test.ts / revisionFamilyLinkage.source.test.ts).
//
//  1. the OLD unconditional set on pipeline_complete is GONE.
//  2. the pipeline_complete branch now computes an `isForeignCompletion` guard
//     and only sets the content-source when NOT foreign.
//  3. the launch-flow / BUG-005 pins the guard reuses stay intact.
// ─────────────────────────────────────────────────────────────────

const pageSource = readFileSync(
  resolve(__dirname, "../../app/dashboard/page.tsx"),
  "utf8",
);

describe("page.tsx pipeline_complete run-scope guard (BUG-011)", () => {
  it("removes the old UNCONDITIONAL setContentSourceRunId on pipeline_complete", () => {
    expect(pageSource).not.toContain(
      "if (data.pipeline_run_id) setContentSourceRunId(data.pipeline_run_id as string);",
    );
  });

  it("run-scopes the pipeline_complete set behind an isForeignCompletion guard", () => {
    expect(pageSource).toContain("isForeignCompletion");
    // The set is gated on NOT-foreign (launch->watch + no-tracked-id preserved).
    expect(pageSource).toContain(
      "if (completingRunId && !isForeignCompletion) setContentSourceRunId(completingRunId);",
    );
    // The foreign computation mirrors the BUG-005 isForeignRun shape.
    expect(pageSource).toContain(
      "completingRunId !== trackedRunIdRef.current",
    );
  });

  it("preserves the launch-flow / BUG-005 pins the guard reuses (no regression)", () => {
    // Launch set — the tracked ref is pinned to the launched run at launch time.
    expect(pageSource).toContain("trackedRunIdRef.current = launchedRunId;");
    // The pipeline_start BUG-005 foreign-run guard token remains present.
    expect(pageSource).toContain("const isForeignRun =");
  });
});
