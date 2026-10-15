/**
 * Project a `GET /api/workflows/{id}` payload into the canvas/Advanced data model.
 *
 * Extracted from `IdeaInputPage` (spec 016 T6) so the LaunchWizard can render the
 * SAME rows for an overridden built-in. One seam, not two: the projection is
 * fiddly in three places that each cost a bug the first time round, and a second
 * copy would drift out of sync with the first.
 *
 * The three things it gets right, all of which a naive `detail.steps.map()` misses:
 *
 * 1. **Raw steps beat the compiled projection.** `detail.steps` is lossy — no
 *    `prompt`, `tools`, `instance_id` or `route` — so a step that hands off to
 *    another workflow renders as an ordinary node with nothing showing the handoff.
 *    `manifest_steps` carries the authoring shape. Falls back to the compiled
 *    projection when the manifest could not be read.
 *
 * 2. **Route targets are normalised to node ids.** Targets in a hand-authored
 *    manifest are BARE instance ids ("done") because the engine resolves them with
 *    a suffix fallback (ADR-0017). The canvas has no such fallback — it compares
 *    against node ids ("custom-agent:done"). Unnormalised, a target is never seen,
 *    the node renders as an orphan, and every branch edge fails to resolve.
 *    `trigger: "workflow"` targets are workflow ids, not steps, and are left alone.
 *
 * 3. **Gates are returned as a `selections` map.** A node draws as a conditional
 *    (diamond + branch edges) only when BOTH `agent.route` has outcomes AND
 *    `selections[id].gates` includes "conditional". Gates live in `selections`
 *    rather than on `AgentDef` because in the composer they are a user-toggled
 *    lever; a workflow opened from its manifest has them DECLARED instead. Without
 *    seeding this, a conditional step draws as an ordinary node — its route was
 *    there, but the gate half of the canvas's own test was never satisfied.
 */

import type { WorkflowDetail } from "@/lib/api";
import type { AgentDef } from "@/types";
import { manifestStepsToAgents } from "@/store/api/userWorkflows";

export interface ManifestProjection {
  /** The workflow's steps as canvas/Advanced rows. */
  agents: AgentDef[];
  /** Declared per-step gates in the shape the canvas reads them from. */
  selections: Record<string, Record<string, unknown>> | undefined;
  /** The manifest's raw steps, verbatim, for an "open in canvas" hand-off. */
  rawSteps: WorkflowDetail["manifest_steps"];
}

/** `instance_id` -> canvas node id, for route-target normalisation. */
function nodeIdMap(raw: NonNullable<WorkflowDetail["manifest_steps"]>) {
  const out = new Map<string, string>();
  for (const st of raw) {
    const base = st.agent || "custom-agent";
    if (st.instance_id) out.set(st.instance_id, `${base}:${st.instance_id}`);
  }
  return out;
}

function normaliseRoute(
  r: AgentDef["route"],
  nodeIdOf: Map<string, string>,
): AgentDef["route"] {
  if (!r?.outcomes) return r;
  const outcomes = Object.fromEntries(
    Object.entries(r.outcomes).map(([k, o]) => [
      k,
      // Only a step target is a node id. A workflow target is a workflow id.
      o.trigger === "step" ? { ...o, target: nodeIdOf.get(o.target) ?? o.target } : o,
    ]),
  );
  return {
    ...r,
    outcomes,
    // The decision source is a step reference too, authored bare ("ask") exactly
    // like a target (ADR-0017). Every consumer compares it against node ids —
    // CanvasConfigRail's Prompt User toggle against `prev.id` — so unnormalised
    // it never matches and the one control that surfaces `before-human` reads
    // OFF for a step that genuinely declares it. An already-normalised id is not
    // in the map and falls through unchanged.
    condition_agent: r.condition_agent
      ? (nodeIdOf.get(r.condition_agent) ?? r.condition_agent)
      : r.condition_agent,
    default_next: r.default_next
      ? (nodeIdOf.get(r.default_next) ?? r.default_next)
      : r.default_next,
  };
}

export function agentsFromManifest(
  detail: WorkflowDetail,
  pipelineType: string,
): ManifestProjection {
  const raw = detail.manifest_steps ?? undefined;

  if (!raw || raw.length === 0) {
    // No authoring shape available — the compiled projection is all there is.
    // Carries no prompt/tools/route, so the canvas renders plain nodes.
    return {
      agents: detail.steps.map((st, i) => ({
        id: st.agent_id,
        name: st.name || st.agent_id,
        role: st.role || "Workflow step",
        description: st.role || "",
        pipeline_type: pipelineType,
        order: st.order ?? i + 1,
        icon: "\u{1F9E9}",
        estimated_duration: 0,
        has_skill: (st.skills?.length ?? 0) > 0,
        gate: st.declared_gate ?? null,
      })),
      selections: undefined,
      rawSteps: undefined,
    };
  }

  const nodeIdOf = nodeIdMap(raw);

  const selections: Record<string, Record<string, unknown>> = {};
  const collectGates = (list: NonNullable<WorkflowDetail["manifest_steps"]>) => {
    for (const st of list) {
      const base = st.agent || "custom-agent";
      const sid = st.instance_id ? `${base}:${st.instance_id}` : base;
      if (st.gates && st.gates.length > 0) selections[sid] = { gates: [...st.gates] };
      // a nested child can declare its own gates; the flat loop never saw them
      const kids = (st as { subagents?: { steps?: NonNullable<WorkflowDetail["manifest_steps"]> } }).subagents?.steps;
      if (kids?.length) collectGates(kids);
    }
  };
  collectGates(raw);

  // The canvas's OWN converter (store/api/userWorkflows) is the single source of
  // truth for manifest -> AgentDef. It is what ComposerPage uses, and it is the
  // only one that walks `subagents.steps` into `agent.children` — the hand-rolled
  // `raw.map` that used to live here flattened every fan-out parent, so the
  // Advanced popup drew a parent with an empty "+ Sub-agent" slot while the full
  // canvas drew its children correctly. Delegating means a fix to the canvas's
  // conversion lands in the popup for free, which is the whole point of this seam.
  const decorate = (a: AgentDef, i: number): AgentDef => {
    // `manifestStepToAgent` uses the COMPOSER's bare-id convention for a custom
    // agent ("page"); this seam uses the canvas NODE id ("custom-agent:page"),
    // which is what depends_on, route targets, the compiled lookup and the
    // selections map are all keyed on. Re-prefix before anything reads `id`.
    const id = a.isCustom && a.instance_id ? `custom-agent:${a.instance_id}` : a.id;
    const compiled = detail.steps.find((c) => c.agent_id === id);
    return {
      ...a,
      id,
      role: compiled?.role || a.role || "Workflow step",
      description: compiled?.role || a.description || "",
      pipeline_type: pipelineType,
      order: compiled?.order ?? i + 1,
      icon: a.icon || "\u{1F9E9}",
      estimated_duration: a.estimated_duration ?? 0,
      has_skill: (a.skills?.length ?? 0) > 0,
      gate: compiled?.declared_gate ?? null,
      route: normaliseRoute(a.route, nodeIdOf),
      children: a.children ? a.children.map(decorate) : undefined,
    };
  };
  // ISS-1157: without a lookup the converter names a built-in step by its agent
  // id and gives it the composer's 60 s blank-agent estimate. A built-in step
  // rarely declares a `name`; the compiled step carries the display name (an
  // explicit manifest `name` still wins inside the converter).
  const fromCompiled = (id: string): AgentDef | undefined => {
    const c = detail.steps.find((s) => s.agent_id === id);
    if (!c) return undefined;
    return {
      id,
      name: c.name || id,
      role: c.role,
      description: c.role,
      pipeline_type: pipelineType,
      order: c.order,
      icon: "",
      estimated_duration: 0,
      has_skill: false,
    };
  };
  const agents: AgentDef[] = manifestStepsToAgents(raw, fromCompiled).map(decorate);

  return {
    agents,
    selections: Object.keys(selections).length > 0 ? selections : undefined,
    rawSteps: raw,
  };
}
