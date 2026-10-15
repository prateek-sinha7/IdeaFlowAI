// QA-KB-002 analysis proof. Executes the REAL current parseViewPath (frontend/src/lib/routes.ts) and the
// REAL current initialWorkflowTypeFor (sliced out of frontend/src/app/[...view]/page.tsx) on the actual URLs.
// Reads source only; touches nothing in the repo; no server, no network.
//
// Run from the frontend/ directory:
//   cd frontend && node ../evidence/qa-kb-002/analysis-proof-initialWorkflowTypeFor.cjs
const fs = require("fs"), path = require("path");
const ts = require(path.resolve("node_modules/typescript"));
const tr = (s) => ts.transpileModule(s, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;

// routes.ts -> parseViewPath
const routesJs = tr(fs.readFileSync("src/lib/routes.ts", "utf8"));
const m = { exports: {} }; new Function("module", "exports", "require", routesJs)(m, m.exports, require);
const { parseViewPath } = m.exports;

// page.tsx -> slice the one self-contained function
const page = fs.readFileSync("src/app/[...view]/page.tsx", "utf8");
const start = page.indexOf("function initialWorkflowTypeFor(");
const end = page.indexOf("\n}\n", start) + 3;
const fnSrc = page.slice(start, end);
console.log("SLICED SOURCE:\n" + fnSrc);
const initialWorkflowTypeFor = new Function(tr(fnSrc) + "; return initialWorkflowTypeFor;")();

for (const url of ["/create/app", "/create/user-stories", "/create/app_builder", "/create/user_stories", "/create/ex_A2_branch"]) {
  const parsed = parseViewPath(url.split("/").filter(Boolean));
  console.log(url.padEnd(24), JSON.stringify(parsed).padEnd(52), "-> initialWorkflowType =", JSON.stringify(initialWorkflowTypeFor(parsed)));
}
