import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// QA-KB-035 / ISS-676 + ISS-927 — a BACKGROUND run's pipeline_cancelled/failed frame
// (frameRunId !== tracked run, but launched by this tab so isForeignFrame is false) must not
// clear the VIEWED run's clarify state nor overwrite lastCancelledRunId.
// Source-slice test: the live terminal block is sliced out of page.tsx and executed with stubs.
// Fix landed (FIX-708); these are plain assertions now.
const src = readFileSync(resolve(__dirname, "page.tsx"), "utf8");
const start = src.indexOf('if (msg.type === "pipeline_cancelled" || msg.type === "pipeline_failed") {');
const end = src.indexOf("\n      return;\n", start);
const block = src.slice(start, end);

// wsReplayState.ts isForeignRunFrame, verbatim
const isForeignRunFrame = (f?: string, t?: string | null) => (!f || !t ? false : f !== t);
const names = ["setBackgroundRunTransition", "setReviewGateData", "setQuestionnaireData", "setActivePipelineRunId", "setLastCancelledRunId", "patchRecentRunStatus"];

function run(type: string, frameRunId: string, tracked: string) {
  const calls: string[] = [];
  const rec = (n: string) => (...a: unknown[]) => { calls.push(`${n}(${a.map((x) => JSON.stringify(x)).join(",")})`); };
  const stubs = names.map(rec);
  const runStore = { update: rec("runStore.update") };
  const detachRunRef = { current: rec("detachRunRef") };
  const trackedRunIdRef = { current: tracked };
  const fn = new Function("msg", "isForeignFrame", "frameRunId", "trackedRunIdRef", "runStore", "detachRunRef", "isForeignRunFrame", ...names, block);
  fn({ type }, false, frameRunId, trackedRunIdRef, runStore, detachRunRef, isForeignRunFrame, ...stubs);
  return calls;
}

describe("QA-KB-035 background terminal frame vs viewed run", () => {
  it("slices the live block", () => {
    expect(start).toBeGreaterThan(-1);
    expect(end).toBeGreaterThan(start);
  });

  for (const type of ["pipeline_cancelled", "pipeline_failed"]) {
    it(`ISS-676: background ${type} leaves the viewed run's clarify state alone`, () => {
      const calls = run(type, "BG", "VIEW");
      expect(calls.filter((c) => /^(setReviewGateData|setQuestionnaireData|setActivePipelineRunId)\(/.test(c))).toEqual([]);
    });
  }

  it("ISS-927: background cancel does not overwrite lastCancelledRunId", () => {
    const calls = run("pipeline_cancelled", "BG", "VIEW");
    expect(calls.filter((c) => c.startsWith("setLastCancelledRunId("))).toEqual([]);
  });
});
