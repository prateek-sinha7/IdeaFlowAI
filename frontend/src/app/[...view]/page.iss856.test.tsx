/**
 * QA-PS-048 / ISS-856 — switching versions from the History family picker
 * fetches the full run record TWICE: `WorkflowHistory.tsx`'s
 * `handleSelectVersion` (~line 388) awaits `getWorkflow(token, memberId)` and
 * hands the result to `onOpenRun(full)`, which is wired (`DashboardLayout.tsx`)
 * to `page.tsx`'s `handleSelectWorkflowRun` (~line 2999) — and that function
 * reads only `run.id` off the object it was just handed before firing a
 * SECOND `getWorkflow(currentToken, run.id)` for data it already has.
 *
 * The two fetches are provably SEQUENTIAL (the second starts from inside the
 * first's own resolved callback), so no in-flight dedupe guard (FIX-637's
 * singleFlightGet included) could ever coalesce them — this needs a real
 * guard in `handleSelectWorkflowRun` itself, per the card's "Suggested fix":
 * "so a caller that already awaited getWorkflow ... is not made to pay for
 * it twice. The fix belongs in handleSelectWorkflowRun itself".
 *
 * `handleSelectWorkflowRun` is an inline `useCallback` inside a 4000+ line
 * page component with no existing test harness mounting it (same situation
 * ISS-657's own test documents) — this pins the gap directly against the
 * real, current source instead of inventing that harness, so it fails today
 * for the reason the card describes and starts passing the moment a guard is
 * added before the `getWorkflow(currentToken, run.id)` call.
 *
 * See `.knowledge/cards/20260923-0028-ISS-856.md`.
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";

describe("handleSelectWorkflowRun must not blindly re-fetch a run it was already handed a full record for (QA-PS-048 / ISS-856)", () => {
  it("guards the getWorkflow(currentToken, run.id) call so an already-full run is not refetched", () => {
    const src = readFileSync(path.join(__dirname, "page.tsx"), "utf8");

    const start = src.indexOf("const handleSelectWorkflowRun = useCallback(");
    expect(start).toBeGreaterThan(-1);
    const callMarker = "await getWorkflow(currentToken, run.id)";
    const callIdx = src.indexOf(callMarker, start);
    expect(callIdx).toBeGreaterThan(start);

    // Sanity: this is genuinely the reopen-fetch site the card describes —
    // if these markers move, the slice below is no longer the right code and
    // this test would otherwise pass/fail for the wrong reason.
    const tryIdx = src.lastIndexOf("try {", callIdx);
    expect(tryIdx).toBeGreaterThan(start);
    expect(callIdx - tryIdx).toBeLessThan(600);

    const guardWindow = src.slice(tryIdx, callIdx);

    // ISS-856 unfixed: nothing between `try {` and the fetch checks whether
    // `run` already carries a full record (e.g. a caller that just awaited
    // getWorkflow itself, like WorkflowHistory's handleSelectVersion via
    // onOpenRun). The call is unconditional today.
    const hasAlreadyFullGuard = /if\s*\(/.test(guardWindow);

    expect(hasAlreadyFullGuard).toBe(true);
  });

  it("sanity: WorkflowHistory's handleSelectVersion really does await getWorkflow before handing off via onOpenRun", () => {
    const src = readFileSync(
      path.join(__dirname, "..", "..", "components", "history", "WorkflowHistory.tsx"),
      "utf8",
    );
    const start = src.indexOf("const handleSelectVersion = useCallback(async (memberId: string) => {");
    expect(start).toBeGreaterThan(-1);
    const end = src.indexOf("}, [onOpenRun]);", start);
    expect(end).toBeGreaterThan(start);
    const body = src.slice(start, end);

    expect(body).toContain("await getWorkflow(token, memberId)");
    expect(body).toContain("onOpenRun(full)");
  });
});
