// QA-KB-033 analyzer evidence. Run from anywhere:  node evidence/qa-kb-033/sim.js
// Reads the REAL frontend/src/app/[...view]/page.tsx, mutates it ONLY in memory, writes nothing.
//
// Part 1: how each candidate form of the whole-file idiom count assertion in
//         workflowDetailCatch.source.test.ts:86-87 behaves across the scenarios that matter.
// Part 2: the same mechanism for the one same-class sibling, launchImageAndRecents.source.test.ts:31-34.
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const SRC = fs.readFileSync(path.join(ROOT, "frontend/src/app/[...view]/page.tsx"), "utf8");

// ───────────────────────── Part 1 ─────────────────────────
const IDIOM = "if (err instanceof ApiError && (err.status === 403 || err.status === 404)) {";
const count = (s) => s.split(IDIOM).length - 1;

// The five sites, keyed by the unique setter each one calls on 403/404.
const SETTERS = [
  "setBuiltinCanvasAccessDenied", // FIX-368 / ISS-299  /workflows/{type}/canvas
  "setRunAccessDenied",           // T24                run-detail
  "setWorkflowEditAccessDenied",  // T8                 /workflows/{id}/edit
  "setWorkflowDetailFailed",      // T30 (F7)           /workflows/{id}
  "setWorkflowRunFailed",         // ISS-380            /workflows/{id}/run
];

// Each form returns true when the assertion PASSES (test stays green).
const forms = {
  "toBe(5) [today]": (s) => count(s) === 5,
  ">=3 [agreed fix]": (s) => count(s) >= 3,
  ">=5 [ratchet]": (s) => count(s) >= 5,
  "per-setter": (s) =>
    SETTERS.every((setter) => {
      const i = s.indexOf(`${setter}(true)`);
      if (i < 0) return false;
      const c = Math.max(s.lastIndexOf("catch (", i), s.lastIndexOf(".catch(", i));
      return c >= 0 && s.slice(c, i).includes(IDIOM);
    }),
};

const nth = (s, needle, n) => { let idx = -1; for (let k = 0; k <= n; k++) idx = s.indexOf(needle, idx + 1); return idx; };
// site n (0-based, file order) reverts to swallow-all: its guard is removed
const revertSite = (s, n) => { const i = nth(s, IDIOM, n); return s.slice(0, i) + "if (true) {" + s.slice(i + IDIOM.length); };
const addLegitSite = (s, tag) =>
  s + `\n// ${tag}\ntry { await f(); } catch (err) {\n  ${IDIOM}\n    setSomethingNewDenied(true);\n  }\n}\n`;

const scenarios = {
  "HEAD as-is (5 sites)": SRC,
  "S1 +1 legitimate new narrowed site": addLegitSite(SRC, "new T-series effect"),
  "S4 -1: /edit site reverted to swallow-all": revertSite(SRC, 2),
  "S2 -2: /run + canvas reverted (ISS-380, FIX-368 undone)": revertSite(revertSite(SRC, 4), 0),
  "S3 -1 reverted AND +1 added (compensating)": addLegitSite(revertSite(SRC, 2), "new site"),
};

console.log("PART 1: idiom sites in HEAD:", count(SRC));
const names = Object.keys(forms);
console.log("scenario".padEnd(58) + names.map((n) => n.padEnd(18)).join("") + "count");
for (const [label, src] of Object.entries(scenarios)) {
  console.log(label.padEnd(58) + names.map((n) => (forms[n](src) ? "pass" : "FAIL").padEnd(18)).join("") + count(src));
}

// ───────────────────────── Part 2 ─────────────────────────
const P = "pending.images && pending.images.length > 0";
const n2 = (x) => x.split(P).length - 1;
const ppt = SRC.indexOf("setPendingOdPptParams({");
const pptSpread = SRC.indexOf(P, ppt);
const withThird = SRC + "\nconst x = pending.images && pending.images.length > 0 ? 1 : 0;\n";
const pptLost = SRC.slice(0, pptSpread) + "false" + SRC.slice(pptSpread + P.length) + "\nconst y = pending.images && pending.images.length > 0;\n";

console.log("\nPART 2: launchImageAndRecents.source.test.ts:31-34 asserts split(P).length-1 === 2");
console.log("HEAD                                     count=" + n2(SRC) + "  toBe(2): " + (n2(SRC) === 2 ? "pass" : "FAIL"));
console.log("S1 legit third reader of pending.images  count=" + n2(withThird) + "  toBe(2): " + (n2(withThird) === 2 ? "pass" : "FAIL") + "  (FAIL = false alarm)");
console.log("S3 ppt setter loses spread, unrelated +1 count=" + n2(pptLost) + "  toBe(2): " + (n2(pptLost) === 2 ? "pass" : "FAIL") + "  (pass = real regression missed)");
