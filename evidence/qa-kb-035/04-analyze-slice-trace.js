// QA-KB-035 analyzer trace. READ-ONLY on the repo: slices the live terminal block out of page.tsx,
// runs it with recording stubs, and (in memory only) applies the proposed guard to prove its call sequences.
const fs = require("fs");
const PAGE = "/Users/bilala/Developer/Projects/VELOCITY-AI-worktrees/feat-user-stories-v2/frontend/src/app/[...view]/page.tsx";
const src = fs.readFileSync(PAGE, "utf8");
const START = 'if (msg.type === "pipeline_cancelled" || msg.type === "pipeline_failed") {';
const start = src.indexOf(START);
const end = src.indexOf("\n      return;\n", start); // same end marker the repo's source-lock tests use
if (start < 0 || end < 0) throw new Error("block not found");
const lineOf = (i) => src.slice(0, i).split("\n").length;
console.log(`live block: page.tsx:${lineOf(start)}-${lineOf(end)}`);
const block = src.slice(start, end);

// wsReplayState.ts:80-86, copied verbatim (the shared predicate the fix should reuse)
const isForeignRunFrame = (f, t) => { if (!f || !t) return false; return f !== t; };

function run(label, code, { type, frameRunId, tracked, isForeignFrame = false }) {
  const calls = [];
  const rec = (n) => (...a) => { calls.push(`${n}(${a.map((x) => JSON.stringify(x)).join(",")})`); };
  const names = ["setBackgroundRunTransition", "setReviewGateData", "setQuestionnaireData", "setActivePipelineRunId", "setLastCancelledRunId", "patchRecentRunStatus"];
  const stubs = Object.fromEntries(names.map((n) => [n, rec(n)]));
  const runStore = { update: rec("runStore.update") };
  const detachRunRef = { current: rec("detachRunRef") };
  const trackedRunIdRef = { current: tracked };
  const fn = new Function("msg", "isForeignFrame", "frameRunId", "trackedRunIdRef", "runStore", "detachRunRef", "isForeignRunFrame", ...names, code);
  fn({ type }, isForeignFrame, frameRunId, trackedRunIdRef, runStore, detachRunRef, isForeignRunFrame, ...names.map((n) => stubs[n]));
  console.log(`${label.padEnd(44)} ${type.padEnd(18)} frame=${String(frameRunId).padEnd(5)} tracked=${String(tracked).padEnd(5)} -> ${calls.join(" ; ") || "(nothing)"}`);
  return calls;
}

// ---- 1. CURRENT code ----
console.log("\n== CURRENT block ==");
for (const type of ["pipeline_cancelled", "pipeline_failed"]) {
  run("BG terminal while VIEW is tracked", block, { type, frameRunId: "BG", tracked: "VIEW" });
}
run("control: the tracked run itself terminates", block, { type: "pipeline_cancelled", frameRunId: "VIEW", tracked: "VIEW" });
run("foreign frame (other tab's run)", block, { type: "pipeline_cancelled", frameRunId: "BG", tracked: "VIEW", isForeignFrame: true });

// ---- 2. PROPOSED guard, applied in memory to the extracted text ----
// (a) the three legacy setters only; (b) additionally setLastCancelledRunId. detach/patch/bgTransition/store.update stay unconditional.
let fixA = block.replace(
  /(\n\s*)setReviewGateData\(null\);\n\s*setQuestionnaireData\(null\);\n\s*setActivePipelineRunId\(null\);/,
  "$1if (!isForeignRunFrame(frameRunId, trackedRunIdRef.current)) {$1  setReviewGateData(null);$1  setQuestionnaireData(null);$1  setActivePipelineRunId(null);$1}",
);
if (fixA === block) throw new Error("fixA transform did not apply");
let fixB = fixA.replace(
  /\n(\s*)setLastCancelledRunId\(cancelledId\);/,
  "\n$1if (!isForeignRunFrame(frameRunId, trackedRunIdRef.current)) setLastCancelledRunId(cancelledId);",
);
if (fixB === fixA) throw new Error("fixB transform did not apply");

for (const [name, code] of [["PROPOSED (a): three setters guarded", fixA], ["PROPOSED (b): (a) + setLastCancelledRunId guarded", fixB]]) {
  console.log(`\n== ${name} ==`);
  for (const type of ["pipeline_cancelled", "pipeline_failed"]) {
    run("BG terminal while VIEW is tracked", code, { type, frameRunId: "BG", tracked: "VIEW" });
  }
  run("control: the tracked run itself terminates", code, { type: "pipeline_cancelled", frameRunId: "VIEW", tracked: "VIEW" });
  run("no tracked id yet (remount window)", code, { type: "pipeline_cancelled", frameRunId: "BG", tracked: null });
  run("frame carries no run id", code, { type: "pipeline_cancelled", frameRunId: undefined, tracked: "VIEW" });
}
