// QA-KB-116 analysis probe. Offline. Reads payloads captured from the live :8000 backend
// (GET /api/workflows/{id} as admin@velocity.ai, who holds saved overrides, and as pro@velocity.ai,
// who holds none; GET /api/agents/library) and feeds them to the REAL frontend functions.
//
//   [today]    asserts what the code does now (documents the defect, passes)
//   [contract] asserts what the product intends (RED today, wrapped in it.fails so the file is green)
//   [control]  must stay green after the fix
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";
import { agentsFromManifest } from "@/lib/manifestAgents";
import { manifestStepsToAgents } from "@/store/api/userWorkflows";
import { mergePlanWithLibrary } from "@/components/workflow/LaunchWizard";
import { agentMatchesPipelineType } from "@/lib/workflowIcons";
import type { AgentDef } from "@/types";

const DIR = path.resolve(process.cwd(), "../evidence/qa-kb-116/analysis-plugins");
const load = (f: string) => JSON.parse(readFileSync(path.join(DIR, f), "utf8"));
const detail = (who: "admin" | "pro", wid: string) => load(`detail.${who}.${wid}.json`);
const LIBRARY: AgentDef[] = load("library.json").agents;
const libFor = (pt: string) =>
  LIBRARY.filter((a) => agentMatchesPipelineType(a.pipeline_type, pt)).sort((a, b) => a.order - b.order);
const rows = (agents: AgentDef[]) => agents.map((a) => `${a.id} | name=${JSON.stringify(a.name)} | role=${JSON.stringify(a.role)} | icon=${JSON.stringify(a.icon)} | est=${a.estimated_duration}s`);

describe("QA-KB-116 probe: agent labels built by agentsFromManifest", () => {
  it("[today] P1 admin's enabled user_stories override: every row's name is the raw agent id", () => {
    const d = detail("admin", "user_stories");
    expect(d.is_overridden).toBe(true);
    const { agents } = agentsFromManifest(d, "user_stories");
    console.log("[P1] agentsFromManifest(admin user_stories override):\n  " + rows(agents).join("\n  "));
    console.log("[P1] the payload's compiled step names (what the label should be):", d.steps.map((s: { name: string }) => s.name));
    console.log("[P1] manifest_steps[].name (what manifestStepToAgent reads):", d.manifest_steps.map((s: { name?: string }) => s.name ?? null));
    expect(agents.map((a) => a.name)).toEqual(agents.map((a) => a.id));
    expect(agents.map((a) => a.name)).toEqual([
      "domain-analyst", "epic-architect", "story-estimator", "nfr-specialist", "backlog-reviewer", "backlog-compiler",
    ]);
    // the role IS restored from the compiled projection (decorate), only the name is not
    expect(agents[0].role).toBe("Market & Persona Research");
  });

  it("[today] P2 the pre-1e329e47b formula on the same payload gives the real names", () => {
    const d = detail("admin", "user_stories");
    const old = d.manifest_steps.map((st: { agent: string; name?: string }) => {
      const compiled = d.steps.find((c: { agent_id: string }) => c.agent_id === st.agent);
      return st.name || compiled?.name || st.agent;
    });
    console.log("[P2] old `st.name || compiled?.name || id`:", old);
    expect(old[0]).toBe("Domain Discovery Agent");
  });

  it("[today] P3 est. duration / icon / description of the override rows are placeholders, not the library's", () => {
    const d = detail("admin", "user_stories");
    const { agents } = agentsFromManifest(d, "user_stories");
    const sum = (xs: AgentDef[]) => xs.reduce((s, a) => s + (a.estimated_duration ?? 0), 0);
    const lib = libFor("user_stories");
    // same formula as IdeaInputPage.tsx:2240 (`~${t < 60 ? `${t}s` : `${Math.round(t / 60)}m`}`)
    const pill = (t: number) => `~${t < 60 ? `${t}s` : `${Math.round(t / 60)}m`}`;
    console.log(`[P3] override roster: ${agents.length} rows, total est ${sum(agents)}s => "${pill(sum(agents))}"`);
    console.log(`[P3] library roster : ${lib.length} rows, total est ${sum(lib)}s => "${pill(sum(lib))}"`);
    console.log("[P3] override row0 description:", JSON.stringify(agents[0].description), "| library row0 description:", JSON.stringify(lib[0].description));
    expect(agents.every((a) => a.estimated_duration === 60)).toBe(true);
    expect(agents.every((a) => a.icon === "\u{1F9E9}")).toBe(true);
  });

  it("[control] P4 the five other manifest->AgentDef sites pass a library lookup and get real names", () => {
    const d = detail("admin", "user_stories");
    const lookup = (id: string) => LIBRARY.find((a) => a.id === id);
    const viaLookup = manifestStepsToAgents(d.manifest_steps, lookup);
    console.log("[P4] manifestStepsToAgents(raw, libraryLookup):\n  " + rows(viaLookup).join("\n  "));
    expect(viaLookup.map((a) => a.name)).toEqual([
      "Domain Discovery Agent", "Backlog Architecture Agent", "Estimation Agent",
      "Quality Requirements Agent", "Quality Review Agent", "Delivery Compilation Agent",
    ]);
  });

  it("[today] P5 LaunchWizard: ppt_v2 plan with NO override still renders raw ids after mergePlanWithLibrary", () => {
    const d = detail("pro", "ppt_v2");
    expect(d.has_override).toBe(false);
    const plan = agentsFromManifest(d, "ppt_v2").agents;
    const libRoster = libFor("ppt_v2");
    console.log(`[P5] ppt_v2: plan rows=${plan.length}, library roster (agentMatchesPipelineType) rows=${libRoster.length}  => plan wins merge: ${plan.length > libRoster.length}`);
    const merged = mergePlanWithLibrary(plan, LIBRARY);
    console.log("[P5] mergePlanWithLibrary(plan, library):\n  " + rows(merged).join("\n  "));
    console.log("[P5] library names for the same ids:", merged.map((m) => LIBRARY.find((l) => l.id === m.id)?.name ?? null));
    expect(merged.map((a) => a.name)).toEqual(merged.map((a) => a.id));
  });

  it("[today] P6 LaunchWizard: ppt / prototype / prototype_v2 plan rows, no override", () => {
    for (const wid of ["ppt", "prototype", "prototype_v2"]) {
      const d = detail("pro", wid);
      const plan = agentsFromManifest(d, wid).agents;
      const libRoster = libFor(wid);
      const merges = plan.length > libRoster.length || plan.some((a) => (a.children?.length ?? 0) > 0);
      const shown = merges ? mergePlanWithLibrary(plan, LIBRARY) : libRoster;
      console.log(`[P6] ${wid}: plan=${plan.length} library=${libRoster.length} planWinsMerge=${merges}; shown names=${JSON.stringify(shown.map((a) => a.name))}`);
    }
  });

  it("[today] P7 LaunchWizard: admin's enabled ppt / prototype / ppt_v2 overrides, rows go straight to pipelineAgents", () => {
    for (const wid of ["ppt", "prototype", "ppt_v2"]) {
      const d = detail("admin", wid);
      expect(d.is_overridden).toBe(true);
      const names = agentsFromManifest(d, wid).agents.map((a) => a.name);
      console.log(`[P7] ${wid} override roster names:`, JSON.stringify(names));
      expect(names.every((n, i) => n === agentsFromManifest(d, wid).agents[i].id)).toBe(true);
    }
  });

  it.fails("[contract, RED today] C1 an override row of a built-in step is labelled with the agent's display name", () => {
    const d = detail("admin", "user_stories");
    const { agents } = agentsFromManifest(d, "user_stories");
    expect(agents.map((a) => a.name)).toEqual(d.steps.map((s: { name: string }) => s.name));
  });

  it.fails("[contract, RED today] C2 a plan row of a built-in step reaches the roster with the library name (ppt_v2, no override)", () => {
    const d = detail("pro", "ppt_v2");
    const merged = mergePlanWithLibrary(agentsFromManifest(d, "ppt_v2").agents, LIBRARY);
    expect(merged.map((a) => a.name)).toEqual(merged.map((m) => LIBRARY.find((l) => l.id === m.id)?.name));
  });

  it("[control] C3 a custom-agent step with an explicit manifest name keeps it (must stay green)", () => {
    const d = detail("admin", "prototype_v2");
    const { agents } = agentsFromManifest(d, "prototype_v2");
    console.log("[C3] prototype_v2 names:", JSON.stringify(agents.map((a) => a.name)));
    expect(agents[0].name).toBe("Reading Planner");
  });
});
