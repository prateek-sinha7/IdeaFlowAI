import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// ─────────────────────────────────────────────────────────────────
// F7 (015-frontend-routing, FR-009 audit fix): source-lock assertions for
// the `/workflows/{id}` read-view (T30) cold-mount catch block — impractical
// to exercise in a full render of the huge page.tsx (see the sibling
// `*.source.test.ts` files in this directory), so this mirrors the sanctioned
// "grep-style source assertion" pattern (e.g. reviseGuard.source.test.ts).
//
// The audit found T30's catch block set the not-found flag for ANY fetch
// failure (5xx, network blip), unlike the narrower 403/404-only pattern
// already used at the run-detail fetch's catch block and T7/T8's
// `/workflows/{id}/edit` fetch's catch block in this same file. This locks
// the fix: the not-found state is now gated behind the same
// `err instanceof ApiError && (err.status === 403 || err.status === 404)`
// check as those two sibling sites.
// ─────────────────────────────────────────────────────────────────

const pageSource = readFileSync(
  resolve(__dirname, "../../app/[...view]/page.tsx"),
  "utf8",
);

// Isolate the T30 workflow-detail cold-mount effect (bounded by its own
// leading comment and the next effect's leading comment) so assertions
// can't accidentally match the sibling run-detail/edit catch blocks that
// deliberately share the same 403/404 condition string.
const t30EffectStart = pageSource.indexOf(
  "// T30 (015-frontend-routing, FR-011): fetch the saved workflow for the",
);
const t30EffectEnd = pageSource.indexOf(
  "// T6 (retry, 015-frontend-routing, FR-001/FR-003, data-model.md T4",
  t30EffectStart,
);
const t30Effect = pageSource.slice(t30EffectStart, t30EffectEnd);

describe("page.tsx /workflows/{id} read-view catch block (F7, FR-009)", () => {
  it("locates the T30 cold-mount effect", () => {
    expect(t30EffectStart).toBeGreaterThan(-1);
    expect(t30EffectEnd).toBeGreaterThan(t30EffectStart);
  });

  it("still redirects a 401 via handleSessionExpiry before any other check (unchanged)", () => {
    expect(t30Effect).toContain(
      "if (err instanceof ApiError && err.status === 401) {",
    );
    expect(t30Effect).toContain("handleSessionExpiry();");
  });

  it("gates setWorkflowDetail(null)/setWorkflowDetailFailed(true) behind the narrowed 403/404 check", () => {
    // Matches the exact pattern used at the run-detail and /workflows/{id}/edit
    // catch blocks elsewhere in this file.
    expect(t30Effect).toMatch(
      /if \(err instanceof ApiError && \(err\.status === 403 \|\| err\.status === 404\)\) \{\s*\n\s*setWorkflowDetail\(null\);\s*\n\s*setWorkflowDetailFailed\(true\);\s*\n\s*\}/,
    );
  });

  it("no longer sets workflowDetailFailed unconditionally for any non-401 error", () => {
    // The old defect: setWorkflowDetail(null)/setWorkflowDetailFailed(true)
    // called directly after the 401 check with no 403/404 guard. Assert the
    // 403/404 condition precedes (and gates) both calls, i.e. neither call
    // appears outside that if-block.
    const setDetailIndex = t30Effect.indexOf("setWorkflowDetail(null);");
    const setFailedIndex = t30Effect.indexOf("setWorkflowDetailFailed(true);");
    const gateIndex = t30Effect.indexOf(
      "if (err instanceof ApiError && (err.status === 403 || err.status === 404)) {",
    );
    expect(gateIndex).toBeGreaterThan(-1);
    expect(setDetailIndex).toBeGreaterThan(gateIndex);
    expect(setFailedIndex).toBeGreaterThan(gateIndex);
    // Exactly one call site of each within this effect (no duplicate/unguarded copy).
    expect(t30Effect.split("setWorkflowDetail(null);").length - 1).toBe(1);
    expect(t30Effect.split("setWorkflowDetailFailed(true);").length - 1).toBe(1);
  });

  it("matches the exact narrowed pattern used at the run-detail and edit catch blocks (no drift)", () => {
    const narrowedPattern =
      "if (err instanceof ApiError && (err.status === 403 || err.status === 404)) {";
    // Present at: run-detail fetch (T24), /workflows/{id}/edit fetch (T8), and
    // now /workflows/{id} read-view fetch (T30, this fix) — three sites total.
    const occurrences = pageSource.split(narrowedPattern).length - 1;
    expect(occurrences).toBe(3);
  });
});
