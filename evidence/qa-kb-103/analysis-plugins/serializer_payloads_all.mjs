// QA-KB-103 analysis probe (read-only): run the REAL canvas serializer
// (frontend/src/store/api/userWorkflows.ts buildWorkflowManifest + lib/manifestAgents.ts agentsFromManifest)
// over each affected built-in, for each way the roster can be seeded, and dump the override
// payload the canvas would POST. Nothing is written to the app; GETs only.
//
// cd frontend && node ../evidence/qa-kb-103/analysis-plugins/serializer_payloads_all.mjs ../evidence/qa-kb-103/analysis-07-serializer-payloads-all-39.json   (every built-in listed by GET /api/workflows)
import { writeFileSync } from "node:fs";

const FE = process.cwd(); // run from frontend/
const API = "http://localhost:8000";
const out = process.argv[2];

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

const login = await fetch(`${API}/api/auth/login`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ email: "admin@velocity.ai", password: "Velocity!Dev2026" }),
}).then((r) => r.json());
const token = login.access_token || login.token;
const H = { Authorization: `Bearer ${token}` };

const lib = (await fetch(`${API}/api/agents/library`, { headers: H }).then((r) => r.json())).agents;
const has = (pt, t) => (Array.isArray(pt) ? pt.includes(t) : pt === t);

const TARGETS = (await fetch(`${API}/api/workflows`, { headers: H }).then((r) => r.json())).map((w) => w.id);

// IdeaInputPage.tsx:1284-1310 — the hand-rolled `manifestAgents` projection (no `extra`).
function ideaInputManifestAgents(detail, workflowId) {
  const raw = detail.manifest_steps;
  return raw.map((st, i) => {
    const agentBase = st.agent || "custom-agent";
    const id = st.instance_id ? `${agentBase}:${st.instance_id}` : agentBase;
    const compiled = detail.steps.find((c) => c.agent_id === id);
    return {
      id,
      name: st.name || compiled?.name || id,
      role: compiled?.role || "Workflow step",
      description: compiled?.role || "",
      pipeline_type: workflowId,
      order: compiled?.order ?? i + 1,
      icon: "x",
      estimated_duration: 0,
      has_skill: (st.skills?.length ?? 0) > 0,
      gate: compiled?.declared_gate ?? null,
      isCustom: agentBase === "custom-agent",
      instance_id: st.instance_id,
      prompt: st.prompt,
      skills: st.skills,
      tools: st.tools,
      route: st.route,
    };
  });
}

const result = {};
for (const id of TARGETS) {
  const detail = await fetch(`${API}/api/workflows/${id}?original=true`, { headers: H }).then((r) => r.json());
  const proj = ma.agentsFromManifest(detail, id);
  const libraryRoster = lib
    .filter((a) => has(a.pipeline_type, id))
    .sort((a, b) => a.order - b.order);
  // IdeaInputPage `manifestSelections` (declared gates keyed by node id)
  const manifestSelections = {};
  for (const st of detail.manifest_steps || []) {
    const base = st.agent || "custom-agent";
    const sid = st.instance_id ? `${base}:${st.instance_id}` : base;
    if (st.gates && st.gates.length > 0) manifestSelections[sid] = { gates: [...st.gates] };
  }
  const build = (agents, sel) => JSON.parse(JSON.stringify(uw.buildWorkflowManifest(agents, undefined, sel)));
  result[id] = {
    file_steps: detail.manifest_steps,
    library_roster_ids: libraryRoster.map((a) => a.id),
    // LaunchWizard when the compiled plan seeds pipelineAgents (mergePlanWithLibrary), selectionsRef = {}
    wizard_plan_seeded: build(proj.agents, {}),
    // LaunchWizard / IdeaInputPage when the library roster seeds pipelineAgents
    library_seeded: libraryRoster.length ? build(libraryRoster, {}) : null,
    // IdeaInputPage when its hand-rolled manifestAgents wins (library incomplete)
    ideainput_manifest_agents: build(ideaInputManifestAgents(detail, id), manifestSelections),
    // The shared seam (agentsFromManifest) with IdeaInputPage-style merged selections
    plan_seeded_with_manifest_selections: build(proj.agents, manifestSelections),
  };
}
writeFileSync(out, JSON.stringify(result, null, 1));
console.log("wrote", out, Object.keys(result).length, "workflows");
await server.close();
