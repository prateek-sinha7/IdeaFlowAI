// QA-KB-050 analysis proof. Executes the REAL getRole (sliced out of frontend/src/components/workflow/AgentsPopup.tsx,
// together with the LOCKED/REQUIRED id sets it reads) and applies the REAL badge/lock predicates, which it first
// asserts are still present verbatim in CanvasNode.tsx and AgentRow.tsx. Reads source only; no server, no network.
//
// Run from the frontend/ directory:
//   cd frontend && node ../evidence/qa-kb-050/analysis-proof-getRole.cjs
const fs = require("fs"), path = require("path");
const ts = require(path.resolve("node_modules/typescript"));
const tr = (s) => ts.transpileModule(s, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;

const popup = fs.readFileSync("src/components/workflow/AgentsPopup.tsx", "utf8");
const a = popup.indexOf("const LOCKED_AGENT_IDS");
const g = popup.indexOf("export function getRole(");
const end = popup.indexOf("\n}\n", g) + 3;
const src = popup.slice(a, end).replace("export function getRole", "function getRole");
const getRole = new Function(tr(src) + "; return getRole;")();

// The predicates, asserted verbatim in both renderers before they are used below.
for (const f of ["src/components/workflow/composer/CanvasNode.tsx", "src/components/workflow/composer/AgentRow.tsx"]) {
  const t = fs.readFileSync(f, "utf8");
  for (const line of ['const locked = role === "locked";', 'const removable = role === "optional";']) {
    if (!t.includes(line)) throw new Error(`${f} no longer contains: ${line}`);
  }
  console.log("verified in " + f + ":  const locked = role === \"locked\";  const removable = role === \"optional\";");
}
const probe = (id, type) => { const role = getRole(id, type); return { role, coreBadge: role === "locked", removeEnabled: role === "optional" }; };

console.log("\npipelineType  agent             role / Core badge / Remove enabled");
for (const type of ["user_stories", "custom", "ppt"]) {
  for (const id of ["domain-analyst", "epic-architect", "story-estimator", "backlog-compiler", "nfr-specialist"]) {
    console.log(type.padEnd(13), id.padEnd(17), JSON.stringify(probe(id, type)));
  }
}
