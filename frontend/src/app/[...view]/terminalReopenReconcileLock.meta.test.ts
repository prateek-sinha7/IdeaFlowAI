import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// Meta-lock for terminalReopenReconcile.source.test.ts (QA-KB-071).
// Each case asserts the CORRECT state of that lock file; it.fails was expected red until the fix landed
// (vitest's xfail). When the lock is repaired a case passes, it.fails flips red, and the verifier
// removes the `.fails`.

const lockSource = readFileSync(resolve(__dirname, "terminalReopenReconcile.source.test.ts"), "utf8");
const pageSource = readFileSync(resolve(__dirname, "page.tsx"), "utf8");

function caseBody(title: string): string {
  const start = lockSource.indexOf(title);
  expect(start).toBeGreaterThan(-1);
  const end = lockSource.indexOf("\n  it(", start);
  return lockSource.slice(start, end === -1 ? undefined : end);
}

describe("ISS-126 source-lock stays in step with page.tsx (QA-KB-071)", () => {
  // ISS-898 — every terminal-status call anchor the lock greps for must still exist in page.tsx.
  it("ISS-898: every applyTerminalStatus/reconcileTerminalStatus anchor in the lock occurs in page.tsx", () => {
    const anchors = [...lockSource.matchAll(/"((?:apply|reconcile)TerminalStatus\([^"]*)"/g)].map((m) => m[1]);
    expect(anchors.length).toBeGreaterThan(0);
    for (const a of anchors) expect(pageSource, `stale anchor: ${a}`).toContain(a);
  });

  // ISS-1009 — the reviewGateData case must fail, not pass on an empty slice, when its anchor is absent.
  it("ISS-1009: the reviewGateData case guards that its anchor was found before slicing", () => {
    const body = caseBody('it("does NOT clear reviewGateData');
    expect(body).toMatch(/expect\(call\)\.toBeGreaterThan\(-1\)/);
  });

  // ISS-1010 — the ordering case must search the replay loop from the reopen fetch, not the first loop in the file.
  it("ISS-1010: the ordering case searches the replay loop from the reopen fetch", () => {
    const body = caseBody('it("runs AFTER the durable replay loop');
    expect(body).toMatch(/indexOf\("for \(const frame of durableFrames\)",\s*\w+\)/);
  });
});
