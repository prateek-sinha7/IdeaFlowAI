// QA-KB-050 analysis proof. Executes the REAL current parseViewPath (frontend/src/lib/routes.ts) and the REAL current
// initialWorkflowTypeFor (sliced out of frontend/src/app/[...view]/page.tsx) on the three composer URLs, and prints the
// workflowType initializer DashboardLayout runs when it gets undefined. Reads source only; no server, no network.
//
// Run from the frontend/ directory:
//   cd frontend && node ../evidence/qa-kb-050/analysis-proof-initialWorkflowTypeFor.cjs
const fs = require("fs"), path = require("path");
const ts = require(path.resolve("node_modules/typescript"));
const tr = (s) => ts.transpileModule(s, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;

const m = { exports: {} }; new Function("module", "exports", "require", tr(fs.readFileSync("src/lib/routes.ts", "utf8")))(m, m.exports, require);
const { parseViewPath } = m.exports;
const page = fs.readFileSync("src/app/[...view]/page.tsx", "utf8");
const start = page.indexOf("function initialWorkflowTypeFor(");
const fnSrc = page.slice(start, page.indexOf("\n}\n", start) + 3);
console.log("SLICED SOURCE:\n" + fnSrc);
const initialWorkflowTypeFor = new Function(tr(fnSrc) + "; return initialWorkflowTypeFor;")();

// page.tsx passes `initialWorkflowTypeFor(parsedView) ?? builtinCanvasType` down as initialWorkflowType (page.tsx ~4250).
const builtinCanvasTypeFor = (p) => (p.screen === "workflow-canvas" ? p.pipelineType : undefined);
const dl = fs.readFileSync("src/components/layout/DashboardLayout.tsx", "utf8");
const i0 = dl.indexOf("const [workflowType, setWorkflowType] = useState<WorkflowType>(() => {");
console.log("DashboardLayout workflowType initializer:\n" + dl.slice(i0, dl.indexOf("});", i0) + 3) + "\n");

console.log("url                        screen            initialWorkflowTypeFor  -> initialWorkflowType passed down");
for (const url of ["/workflows/new", "/workflows/abc123/edit", "/workflows/abc123/run", "/workflows/ppt/canvas", "/create/app"]) {
  const p = parseViewPath(url.split("/").filter(Boolean));
  const own = initialWorkflowTypeFor(p);
  console.log(url.padEnd(26), p.screen.padEnd(17), String(own).padEnd(23), "->", String(own ?? builtinCanvasTypeFor(p)),
    (own ?? builtinCanvasTypeFor(p)) === undefined ? '  => DashboardLayout falls through to "user_stories"' : "");
}
