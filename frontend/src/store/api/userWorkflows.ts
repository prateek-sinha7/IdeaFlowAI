import { http } from "./http";
import { getToken } from "@/lib/api";
import type {
  AgentDef,
  ManifestStep,
  WorkflowCapabilities,
  WorkflowManifest,
  WorkflowRunConfig,
} from "@/types/index";
// Re-exported so callers (ComposerPage) can pull the manifest types from the
// same module they already import the tree-editing helpers from.
export type { ManifestStep, WorkflowManifest };

export interface UserWorkflowSummary {
  id: string;
  name: string;
  description?: string | null;
  base_pipeline_type: string;
  agent_ids: string[];
  model_overrides?: Record<string, string> | null;
  // Spec 012 (R-27/R-29): `manifest_json` holds ONE of two shapes — the compact
  // EMP-03 `{agent_id: {...}}` selections map, or a full per-step `{"steps":
  // [...]}` manifest once a node carries a skill/prompt/subagents tree.
  // `_project` splits them across these two fields, so exactly one is ever
  // non-null and no caller has to sniff for a `"steps"` key.
  selections?: Record<string, Record<string, unknown>> | null;
  manifest?: WorkflowManifest | null;
  created_at?: string;
  updated_at?: string;
}

export interface CreateUserWorkflowBody {
  name: string;
  description?: string;
  base_pipeline_type: string;
  agent_ids: string[];
  model_overrides?: Record<string, string>;
  // The compact per-agent selections map (EMP-03).
  selections?: Record<string, Record<string, unknown>>;
  // Spec 012 (T36): the full `{"steps": [...], capabilities?}` manifest, sent
  // once the composition uses per-node skills/prompt/subagents. A SIBLING of
  // `selections`, not a union with it — both persist into the same reused
  // `manifest_json` column, so sending both is a 422 naming both fields.
  manifest?: WorkflowManifest;
}

// ─── Spec 012 (R-35) — pure tree-editing helpers over a `pipelineAgents` node
//     tree (root array + nested `children`). Immutable: every helper returns a
//     NEW array, never mutates in place. Shared by CanvasView (canvas tree
//     edits) AND ComposerPage (Simple-view "+ Sub-agent" add), so there is one
//     implementation of "find/add/remove anywhere in the tree" — not two. ──────

/** Depth-first lookup of a node anywhere in the tree (root or nested). */
export function findAgentInTree(agents: AgentDef[], id: string): AgentDef | null {
  for (const a of agents) {
    if (a.id === id) return a;
    if (a.children) {
      const found = findAgentInTree(a.children, id);
      if (found) return found;
    }
  }
  return null;
}

/** Replace the node with id `id` (wherever it lives) via `fn`. */
export function mapAgentInTree(
  agents: AgentDef[],
  id: string,
  fn: (a: AgentDef) => AgentDef,
): AgentDef[] {
  return agents.map((a) => {
    if (a.id === id) return fn(a);
    if (a.children) return { ...a, children: mapAgentInTree(a.children, id, fn) };
    return a;
  });
}

/** Append `child` under the node with id `parentId` (wherever it lives),
 *  defaulting a fresh child group to `sequential` (R-04). */
export function addChildInTree(agents: AgentDef[], parentId: string, child: AgentDef): AgentDef[] {
  return agents.map((a) => {
    if (a.id === parentId) {
      return { ...a, children: [...(a.children ?? []), child], strategy: a.strategy ?? "sequential" };
    }
    if (a.children) return { ...a, children: addChildInTree(a.children, parentId, child) };
    return a;
  });
}

/** Remove the node with id `id` wherever it lives in the tree. */
export function removeAgentInTree(agents: AgentDef[], id: string): AgentDef[] {
  return agents
    .filter((a) => a.id !== id)
    .map((a) => (a.children ? { ...a, children: removeAgentInTree(a.children, id) } : a));
}

// ─── Spec 012 — canvas tree ↔ manifest round-trip (R-01..R-05, T30) ───────────

const INSTANCE_ID_RE = /^[a-z0-9][a-z0-9-]*$/;

/** Every node id in the tree, root and nested (R-03: instance_id is unique
 *  across the whole workflow, including nested `subagents.steps`). */
export function collectAgentIds(agents: AgentDef[]): string[] {
  const ids: string[] = [];
  for (const a of agents) {
    ids.push(a.id);
    if (a.children?.length) ids.push(...collectAgentIds(a.children));
  }
  return ids;
}

/** A short, regex-safe (`[a-z0-9]+`) segment derived from the caller's auth
 *  token — not a decoded user id (no JWT-decode dependency here), just a
 *  deterministic-per-session hash so instance ids stay traceable to "who
 *  made this" without exposing anything from the token itself. `"anon"` when
 *  logged out (id generation must never hard-fail on a missing token). */
function shortUserSegment(): string {
  const token = getToken();
  if (!token) return "anon";
  let h = 0;
  for (let i = 0; i < token.length; i++) {
    h = (Math.imul(h, 31) + token.charCodeAt(i)) >>> 0;
  }
  return h.toString(36);
}

/** Generate a fresh, workflow-unique `instance_id` for a new custom-agent
 *  node (R-03): `^[a-z0-9][a-z0-9-]*$`, generated once, never regenerated on
 *  rename. Shaped `<user-segment>-<random>` (hyphen-joined — the id regex has
 *  no underscore) so ids stay globally unique across saves/users rather than
 *  colliding on the same sequential `agent-1`, `agent-2`, ... every workflow
 *  produced before this. */
export function generateInstanceId(existingIds: Iterable<string> = []): string {
  const used = new Set(existingIds);
  const prefix = shortUserSegment();
  const randomSuffix = () => Math.random().toString(36).slice(2, 8);
  let id = `${prefix}-${randomSuffix()}`;
  while (used.has(id)) {
    id = `${prefix}-${randomSuffix()}`;
  }
  return id;
}

/** True iff `id` satisfies the backend's `instance_id` shape (R-03) — the
 *  backend refuses anything else with a `ValueError`. */
export function isValidInstanceId(id: string): boolean {
  return INSTANCE_ID_RE.test(id);
}

/** The blank agent's catalog id. `agents/prompts/custom-agent/AGENT.md` declares
 *  `template: true`, meaning it exists to be INSTANTIATED, never to be a
 *  pipeline member itself (R-02/R-03). `GET /api/agents/library` still lists it,
 *  because listing it is how the user picks "add a blank agent". */
export const CUSTOM_AGENT_TEMPLATE_ID = "custom-agent";

/** The synthetic-id prefix a custom-agent step's backend agent_id is built from
 *  (`${CUSTOM_AGENT_PREFIX}${instance_id}`). Mirrors
 *  `agents/workflows/artifacts.py::CUSTOM_AGENT_PREFIX` byte-for-byte: `depends_on`
 *  values built with it are matched against the compiler's own formula. */
export const CUSTOM_AGENT_PREFIX = `${CUSTOM_AGENT_TEMPLATE_ID}:`;

/** True iff `agent` is the reusable blank template rather than a real library
 *  agent or an already-instantiated node. */
export function isCustomAgentTemplate(agent: AgentDef): boolean {
  return agent.id === CUSTOM_AGENT_TEMPLATE_ID && !agent.isCustom;
}

/**
 * Turn the blank `custom-agent` template into a FRESH, independent node (R-03).
 *
 * The template is meant to be used N times in one workflow — each use is its own
 * step with its own prompt and skills, compiled to `custom-agent:<instance_id>`.
 * That only works if every add mints a NEW id: inserting the raw template would
 * put the literal id `custom-agent` into the pipeline, which then (a) collides
 * with the next add and (b) makes the "already added" library filter hide the
 * template forever after one use.
 *
 * `existingIds` must be the WHOLE tree (`collectAgentIds`), not just the top
 * level — instance ids are unique across nested `subagents.steps` too.
 *
 * A non-template agent is returned unchanged, so callers can pipe every add
 * through this without branching.
 */
export function instantiateIfTemplate(
  agent: AgentDef,
  existingIds: Iterable<string>,
): AgentDef {
  if (!isCustomAgentTemplate(agent)) return agent;
  const newId = generateInstanceId(existingIds);
  return {
    ...agent,
    id: newId,
    instance_id: newId,
    isCustom: true,
    // A fresh node starts blank: the template's catalog copy is a placeholder,
    // and its prompt/skills belong to the instance the user is about to edit,
    // never shared back to the template or to sibling instances.
    name: "New agent",
    role: "Custom agent",
    prompt: undefined,
    skills: undefined,
    children: undefined,
  };
}

function agentToManifestStep(
  agent: AgentDef,
  selections?: Record<string, { gates?: string[] }>,
): ManifestStep {
  const step: ManifestStep = agent.isCustom
    ? { agent: "custom-agent", instance_id: agent.instance_id ?? agent.id, name: agent.name }
    : { agent: agent.id };
  if (agent.isCustom && agent.prompt) step.prompt = agent.prompt;
  if (agent.skills && agent.skills.length > 0) step.skills = [...agent.skills];
  // Spec 014 (R-02/T37): mirrors AgentDef.route field-for-field onto the
  // compiled ManifestStep — only emitted when outcomes is non-empty, matching
  // the same "non-empty" trigger ComposerPage's needsFullManifest checks.
  if (agent.route && Object.keys(agent.route.outcomes ?? {}).length > 0) {
    step.route = { ...agent.route };
  }
  const isParent = !!agent.children && agent.children.length > 0;
  // Fixed grants, no longer author-editable (SPEC012-ADR-10). `write_files`/
  // `read_files` must stay ON — every step writes its own artifact, and OFF
  // never actually gated the native tools, only the secret-scan hook.
  // `exec`/`spawn_subagents` stay OFF — the compiler rejects either for
  // db-trust manifests.
  step.tools = {
    read_files: true,
    write_files: true,
    exec: false,
    ...(isParent ? { spawn_subagents: false } : {}),
  };
  step.gates = selections?.[agent.id]?.gates ?? [];
  if (isParent) {
    step.subagents = {
      mode: agent.strategy ?? "sequential",
      max_parallel: agent.maxParallel ?? 3,
      steps: agent.children!.map((child) => agentToManifestStep(child, selections)),
    };
  } else {
    step.strategy = "single_shot";
  }
  return step;
}

/** The backend agent id for a compiled step — the identity `depends_on` edges
 *  and `_build_roster` are keyed on. Composed steps are `custom-agent:<instance_id>`;
 *  built-in steps are their bare catalog id. */
function stepAgentId(step: ManifestStep): string {
  return step.instance_id ? `${CUSTOM_AGENT_PREFIX}${step.instance_id}` : (step.agent ?? "");
}

/** Record each step's upstream data dependencies, so the engine knows where a
 *  step's inputs came from and can point it at what they produced.
 *
 *  Two edge kinds, both derived from POSITION/SHAPE at serialise time and never
 *  stored on the node — reordering or deleting can therefore never leave a stale
 *  edge behind:
 *
 *    parent  -> its own sub-agents      (A1 + A2 -> A)
 *    step i  -> step i-1, top level     (A -> B -> C)
 *
 *  A parent that also follows another top-level step gets both.
 *
 *  What is deliberately NOT emitted: edges between sub-agent siblings. Sequential
 *  siblings are already chained by the compiler (child *i* depends on child *i-1*),
 *  and parallel siblings must stay edge-free or the DAG would serialise them and
 *  the group would lose its concurrency.
 *
 *  The backend merges and de-duplicates these against its own derived edges, so
 *  declaring them here is idempotent rather than conflicting. */
function deriveDependsOn(steps: ManifestStep[], topLevel: boolean): ManifestStep[] {
  steps.forEach((step, i) => {
    if (step.subagents) deriveDependsOn(step.subagents.steps, false);
    if (step.depends_on) return; // an explicit declaration always wins
    const deps: string[] = [];
    if (step.subagents) {
      deps.push(...step.subagents.steps.map(stepAgentId).filter(Boolean));
    }
    if (topLevel && i > 0) {
      const previous = stepAgentId(steps[i - 1]);
      if (previous) deps.push(previous);
    }
    // Always emitted, even as `[]` — same rule `gates` follows, so a saved
    // manifest never leaves a reader guessing whether "absent" means "no
    // upstream" or "nobody computed it yet".
    step.depends_on = deps;
  });
  return steps;
}

/** Declare `produces: ["route_decision"]` on every route's decision-source step
 *  (spec 014 / R-05b, required by the compiler's R-27 check).
 *
 *  Same class of field as `depends_on` above: DERIVED from the drawn graph at
 *  serialise time, never stored per-node, so editing or deleting a route can
 *  never leave a stale declaration behind. The composer has no user-facing
 *  `produces` control (the FE `AgentDef` carries no produces/consumes) — drawing
 *  a route on a node IS the author declaring that node's decision source, so the
 *  declaration the backend requires is derived from it rather than asked for
 *  twice.
 *
 *  Resolution mirrors `_validate_route_targets`/R-27 exactly, or the injection
 *  would land on a different step than the one the compiler checks:
 *    * the step set is the FLATTENED tree (the compiler validates its flat step
 *      list, so a sub-agent step is in the same id namespace as a top-level one);
 *    * ids are looked up dually — the backend agent id (`custom-agent:<instance_id>`
 *      for a composed step) AND the bare `instance_id` — because `condition_agent`
 *      may be authored either way;
 *    * the decision source is `route.condition_agent` when set, else the routing
 *      step itself (R-05's default).
 *
 *  An unresolvable `condition_agent` is left alone: R-27 already rejects it with a
 *  precise message, and silently inventing a declaration would hide that. */
function deriveRouteDecisionProduces(steps: ManifestStep[]): ManifestStep[] {
  const flat: ManifestStep[] = [];
  const collect = (list: ManifestStep[]) => {
    for (const step of list) {
      flat.push(step);
      if (step.subagents) collect(step.subagents.steps);
    }
  };
  collect(steps);

  const byName = new Map<string, ManifestStep>();
  for (const step of flat) {
    const agentId = stepAgentId(step);
    if (agentId) byName.set(agentId, step);
    if (step.instance_id) byName.set(step.instance_id, step);
  }

  for (const step of flat) {
    const route = step.route;
    if (!route || Object.keys(route.outcomes ?? {}).length === 0) continue;
    const source = byName.get(route.condition_agent || stepAgentId(step));
    if (!source) continue;
    if (!source.produces?.includes("route_decision")) {
      source.produces = [...(source.produces ?? []), "route_decision"];
    }
  }
  return steps;
}

/** Compose the composer's node tree into the full `{"steps": [...]}` manifest
 *  shape (R-02..R-05), with top-level `depends_on` edges derived from order. */
export function agentsToManifestSteps(
  agents: AgentDef[],
  selections?: Record<string, { gates?: string[] }>,
): ManifestStep[] {
  return deriveRouteDecisionProduces(
    deriveDependsOn(
      agents.map((agent) => agentToManifestStep(agent, selections)),
      true,
    ),
  );
}

/** Build the full `WorkflowManifest` (steps + top-level `capabilities`, R-07)
 *  a save should persist once the composition uses any per-node skill,
 *  custom prompt, or sub-agent tree. */
export function buildWorkflowManifest(
  agents: AgentDef[],
  capabilities?: WorkflowCapabilities,
  selections?: Record<string, { gates?: string[] }>,
  runConfig?: WorkflowRunConfig,
): WorkflowManifest {
  const manifest: WorkflowManifest = { steps: agentsToManifestSteps(agents, selections) };
  if (capabilities && Object.keys(capabilities).length > 0) {
    manifest.capabilities = capabilities;
  }
  if (runConfig?.deliverable) manifest.deliverable = runConfig.deliverable;
  if (runConfig?.planner) manifest.planner = runConfig.planner;
  if (runConfig?.clarify) manifest.clarify = runConfig.clarify;
  return manifest;
}

function manifestStepToAgent(
  step: ManifestStep,
  lookup?: (id: string) => AgentDef | undefined,
): AgentDef {
  const isCustom = step.agent === "custom-agent";
  const id = isCustom ? step.instance_id ?? "" : step.agent ?? "";
  const base = !isCustom ? lookup?.(id) : undefined;
  const agent: AgentDef = base
    ? { ...base }
    : {
        id,
        name: step.name ?? id,
        role: isCustom ? "Custom agent" : id,
        description: "",
        pipeline_type: "custom",
        order: 0,
        icon: "",
        estimated_duration: 60,
        has_skill: false,
      };
  agent.id = id;
  if (step.name) agent.name = step.name;
  agent.skills = step.skills ? [...step.skills] : undefined;
  agent.tools = step.tools ? { ...step.tools } : undefined;
  if (isCustom) {
    agent.isCustom = true;
    agent.instance_id = step.instance_id;
    agent.prompt = step.prompt;
  }
  // Spec 014 (R-02/T37): reverse of agentToManifestStep's `step.route` write —
  // reopen fix, this was previously missing, silently dropping the route on
  // save→reopen.
  agent.route = step.route ? { ...step.route } : undefined;
  if (step.subagents) {
    agent.strategy = step.subagents.mode;
    agent.maxParallel = step.subagents.max_parallel;
    agent.children = step.subagents.steps.map((s) => manifestStepToAgent(s, lookup));
  } else {
    agent.children = undefined;
    agent.strategy = undefined;
    agent.maxParallel = undefined;
  }
  return agent;
}

/** Reverse of `agentsToManifestSteps` — reconstructs the composer's node tree
 *  from a saved `{"steps": [...]}` manifest (T30's reload contract). `lookup`
 *  resolves a built-in step's full `AgentDef` (name/role/icon/…) from the
 *  agent library; a custom-agent step never needs it. */
export function manifestStepsToAgents(
  steps: ManifestStep[],
  lookup?: (id: string) => AgentDef | undefined,
): AgentDef[] {
  return steps.map((s) => manifestStepToAgent(s, lookup));
}

export const userWorkflowsApi = {
  list: async (): Promise<UserWorkflowSummary[]> => {
    const { data } = await http.get<UserWorkflowSummary[]>("/api/user-workflows");
    return data;
  },
  get: async (userWorkflowId: string): Promise<UserWorkflowSummary> => {
    const { data } = await http.get<UserWorkflowSummary>(`/api/user-workflows/${userWorkflowId}`);
    return data;
  },
  create: async (body: CreateUserWorkflowBody): Promise<UserWorkflowSummary> => {
    const { data } = await http.post<UserWorkflowSummary>("/api/user-workflows", body);
    return data;
  },
  rename: async (
    userWorkflowId: string,
    body: { name?: string; description?: string }
  ): Promise<UserWorkflowSummary> => {
    const { data } = await http.patch<UserWorkflowSummary>(
      `/api/user-workflows/${userWorkflowId}`,
      body
    );
    return data;
  },
  delete: async (userWorkflowId: string): Promise<void> => {
    await http.delete(`/api/user-workflows/${userWorkflowId}`);
  },
};
