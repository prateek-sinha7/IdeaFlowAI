// QA-KB-124 analysis 05 (read-only, offline): run the REAL canvas serializer over the built-in ex_A1_loop steps,
// for each way a "Save as my version" / inline Run can be seeded, and print the grants and data edges it writes.
//
//   cd frontend && node ../evidence/qa-kb-124/analysis-05-serializer-probe.mjs
//
// Input: the built-in's raw manifest steps exactly as GET /api/workflows/ex_A1_loop?original=true returned them
// (stored by the QA-KB-103 analysis: evidence/qa-kb-103/analysis-07-serializer-payloads-all-39.json, key ex_A1_loop.file_steps).
// No network, no backend, nothing written.
import { readFileSync } from "node:fs";

const FE = process.cwd(); // run from frontend/
const stored = JSON.parse(
  readFileSync(`${FE}/../evidence/qa-kb-103/analysis-07-serializer-payloads-all-39.json`, "utf8"),
);
const fileSteps = stored["ex_A1_loop"].file_steps;
const ID = "ex_A1_loop";

const { createServer } = await import(`${FE}/node_modules/vite/dist/node/index.js`);
const server = await createServer({
  root: FE,
  configFile: false,
  logLevel: "error",
  resolve: { alias: { "@": `${FE}/src` } },
  server: { middlewareMode: true, hmr: false, watch: null },
  appType: "custom",
  optimizeDeps: { noDiscovery: true, include: [] },
});
const uw = await server.ssrLoadModule("/src/store/api/userWorkflows.ts");
const ma = await server.ssrLoadModule("/src/lib/manifestAgents.ts");

const detail = { steps: [], manifest_steps: fileSteps };

// IdeaInputPage.tsx:1286-1312 - the hand-rolled `manifestAgents` projection (no `extra`; keeps tools/skills/prompt/route)
const ideaInputAgents = fileSteps.map((st, i) => {
  const base = st.agent || "custom-agent";
  const id = st.instance_id ? `${base}:${st.instance_id}` : base;
  return {
    id, name: st.name || id, role: "Workflow step", description: "", pipeline_type: ID, order: i + 1, icon: "x",
    estimated_duration: 0, has_skill: (st.skills?.length ?? 0) > 0, gate: null,
    isCustom: base === "custom-agent", instance_id: st.instance_id, prompt: st.prompt, skills: st.skills,
    tools: st.tools, route: st.route,
  };
});
// IdeaInputPage.tsx:1278-1285 - `manifestSelections`: declared GATES only, keyed by node id
const gateOnly = {};
for (const st of fileSteps) {
  const base = st.agent || "custom-agent";
  const sid = st.instance_id ? `${base}:${st.instance_id}` : base;
  if (st.gates && st.gates.length > 0) gateOnly[sid] = { gates: [...st.gates] };
}

const build = (agents, sel) => JSON.parse(JSON.stringify(uw.buildWorkflowManifest(agents, undefined, sel)));
const show = (tag, manifest) => {
  console.log(`== ${tag}`);
  for (const s of manifest.steps) {
    console.log(
      `   ${String(s.instance_id).padEnd(6)} tools=${JSON.stringify(s.tools)} produces=${JSON.stringify(s.produces ?? null)} consumes=${JSON.stringify(s.consumes ?? null)} depends_on=${JSON.stringify(s.depends_on ?? null)}`,
    );
  }
};

console.log("== BUILT-IN file steps (GET /api/workflows/ex_A1_loop?original=true)");
for (const s of fileSteps) {
  console.log(
    `   ${String(s.instance_id).padEnd(6)} tools=${JSON.stringify(s.tools)} produces=${JSON.stringify(s.produces ?? null)} consumes=${JSON.stringify(s.consumes ?? null)} depends_on=${JSON.stringify(s.depends_on ?? null)}`,
  );
}

// (a) IdeaInputPage.handleSaveAsOverride when its hand-rolled projection seeds the roster (the path /create/ex_A1_loop takes)
show("(a) IdeaInputPage hand-rolled projection + gates-only selections  [what the e2e save wrote]", build(ideaInputAgents, gateOnly));
// (b) the canonical shared seam (lib/manifestAgents.agentsFromManifest) + gates-only selections (LaunchWizard / ISS-1128 fix direction a)
const proj = ma.agentsFromManifest(detail, ID);
show("(b) agentsFromManifest (carries extra) + gates-only selections", build(proj.agents, { ...(proj.selections ?? {}) }));
// (c) the Composer canvas path: manifestStepsToAgents + manifestStepsToGateSelections (seeds tools when they deviate from read+write)
const canvasAgents = uw.manifestStepsToAgents(fileSteps);
const canvasSel = uw.manifestStepsToGateSelections(fileSteps);
show("(c) Composer canvas: manifestStepsToAgents + manifestStepsToGateSelections", build(canvasAgents, canvasSel));
await server.close();
