import { http } from "./http";
import { getToken } from "@/lib/api";
import type {
  AgentDef,
  AgentToolGrants,
  ManifestStep,
  WorkflowCapabilities,
  WorkflowManifest,
  WorkflowRunConfig,
} from "@/types/index";

/** The per-step selection payload as it crosses the wire. Named once because it
 *  appeared inline in six signatures, which is how `wave_scheduler` came to be
 *  authorable in the composer but unrepresentable here. Structurally the same
 *  shape as `StepSelection` in AgentsPopup — imported from a component would be
 *  a store->component dependency, so it is declared, not shared. */
type StepSelectionWire = {
  gates?: string[];
  validators?: string[];
  tools?: AgentToolGrants;
  strategy?: "fanout_batch" | "wave_scheduler" | "task_loop";
  task_source?: {
    kind: "parsed";
    parser: string;
    target?: string;
    source_step: string;
  };
  fanout?: { agent?: "self"; mode?: "parallel"; max_parallel?: number };
  on_conflict?: "human_gate";
  model?: string;
  /** spec 020 — reasoning effort for this step's model. */
  effort?: string;
  retry?: number;
};
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

/** Resolve a route target to the id the CANVAS knows a step by.
 *
 *  A route target is authorable in EITHER form and the backend accepts both:
 *  `_validate_route_targets` resolves against `{every step's agent_id} ∪ {every
 *  step's instance_id}`, and the checked-in file workflows use the bare
 *  `instance_id` while a hand-authored or engine-shaped manifest usually
 *  carries `custom-agent:<instance_id>`.
 *
 *  The canvas keys its nodes on the bare id only, so every consumer that
 *  compared `outcome.target` to a node id by string equality silently dropped
 *  the prefixed form. Live symptoms, all one cause: the route edge was not
 *  drawn, the target picker showed the raw id instead of the step, the target
 *  step was flagged "Not connected", and the layout ranked it as an orphan and
 *  parked it away from the flow.
 *
 *  `knows` answers whether an id names a real step. A target already in canvas
 *  form is returned untouched, so a bare-id workflow behaves exactly as before.
 *  An unresolvable target is returned as it was — it is not this function's job
 *  to hide a genuinely dangling route. */
export function resolveRouteTargetId(
  target: string,
  knows: (id: string) => boolean,
): string {
  if (!target || knows(target)) return target;
  const bare = target.startsWith(CUSTOM_AGENT_PREFIX)
    ? target.slice(CUSTOM_AGENT_PREFIX.length)
    : target;
  return knows(bare) ? bare : target;
}

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

/** `ManifestStep` keys the canvas actively reads into (or fully recomputes
 *  onto) an `AgentDef` below. Everything else on a loaded step is opaque to
 *  the canvas and belongs in `AgentDef.extra` instead of being silently
 *  dropped — see `captureStepExtra` / the `extra` doc comment on `AgentDef`. */
const MODELED_STEP_KEYS = new Set([
  "agent",
  "instance_id",
  "name",
  "prompt",
  "skills",
  "tools",
  "gates",
  "route",
  "subagents",
  "mechanical",
  "injects",
]);

/** Everything on a raw manifest step that `MODELED_STEP_KEYS` doesn't cover —
 *  `undefined` when there is none, so an ordinary composer-created node never
 *  carries a stray empty `extra: {}`. */
function captureStepExtra(step: ManifestStep): Record<string, unknown> | undefined {
  const extra: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(step)) {
    if (!MODELED_STEP_KEYS.has(key)) extra[key] = value;
  }
  return Object.keys(extra).length > 0 ? extra : undefined;
}

function agentToManifestStep(
  agent: AgentDef,
  selections?: Record<string, StepSelectionWire>,
): ManifestStep {
  // Passthrough FIRST: every key the loaded step carried that the canvas has
  // no editor for (a hand-authored `strategy: wave_scheduler`, `fanout`,
  // `task_source`, `produces`, `consumes`, `validators`, `redoable`, `fix`,
  // `compaction`, `injects`, `on_conflict`, `require_render`, an explicit
  // `depends_on`, ...) survives untouched. Every field the canvas genuinely
  // computes is assigned AFTER this spread and wins on conflict.
  const step: ManifestStep = {
    ...(agent.extra ?? {}),
    ...(agent.isCustom
      ? { agent: "custom-agent", instance_id: agent.instance_id ?? agent.id, name: agent.name }
      : { agent: agent.id }),
  };
  // Mechanical (code step) — no prompt, model, or tools. Gates still emitted.
  if (agent.mechanical) {
    step.mechanical = agent.mechanical;
    step.gates = selections?.[agent.id]?.gates ?? [];
    return step;
  }
  if (agent.isCustom && agent.prompt) step.prompt = agent.prompt;
  if (agent.skills && agent.skills.length > 0) step.skills = [...agent.skills];
  if (agent.injects && agent.injects.length > 0) step.injects = [...agent.injects];
  // Spec 014 (R-02/T37): mirrors AgentDef.route field-for-field onto the
  // compiled ManifestStep — only emitted when outcomes is non-empty, matching
  // the same "non-empty" trigger ComposerPage's needsFullManifest checks.
  if (agent.route && Object.keys(agent.route.outcomes ?? {}).length > 0) {
    step.route = { ...agent.route };
  }
  const isParent = !!agent.children && agent.children.length > 0;
  // `read_files`/`write_files` come from the author's per-step selection and
  // default ON (an untouched step serialises exactly as it did before the Tools
  // tab became editable). They are really enforced: the compiler caps the grant
  // onto `Step.tools`, `factory.py` maps it through `permission_caps.denied_tools`
  // and the runner excludes those native tools from the graph.
  // `exec` always stays OFF — the untrusted cap zeroes it for db-trust
  // manifests, so there is nothing to offer. `spawn_subagents` has no rail
  // control either, but `agent.tools` (the FULL tools object captured at
  // load, never mutated by the UI — only `selections[...].tools` is) already
  // carries whatever the loaded manifest declared, so it is spread in first
  // and only defaulted to `false` for a genuinely NEW parent the composer
  // itself created (the untrusted-cap behaviour this default existed for).
  const grants = selections?.[agent.id]?.tools;
  step.tools = {
    ...agent.tools,
    read_files: grants?.read_files ?? true,
    write_files: grants?.write_files ?? true,
    exec: false,
    // Named tool packs (file_extract / playwright): emitted only when the
    // author ticked at least one, so untouched steps serialise unchanged.
    ...(grants?.tool_sets?.length ? { tool_sets: [...grants.tool_sets] } : {}),
    ...(isParent && agent.tools?.spawn_subagents === undefined ? { spawn_subagents: false } : {}),
  };
  step.gates = selections?.[agent.id]?.gates ?? [];
  // MODEL + EFFORT (spec 020). Both live on the SELECTION, and neither was read
  // here — so a full-manifest save (the branch `needsFullManifestOnSave` takes
  // once a step has a skill, a custom prompt, a route or a sub-agent tree) wrote
  // prompts, tools, gates and routes but silently dropped the author's model
  // override. Found by a real run: four agents each set to a different model all
  // executed on the workflow default.
  //
  // Shape is the compiler's ModelPolicy mapping (`{model, effort, ...}`), not a
  // bare string — see `_parse_model` in compiler.py, which rejects anything else.
  // An existing `agent.extra.model` (a hand-authored max_tokens/fallback the
  // canvas has no editor for) is spread first so only the keys the author
  // actually set here are overwritten.
  const selModel = selections?.[agent.id]?.model;
  const selEffort = selections?.[agent.id]?.effort;
  if (selModel || selEffort) {
    const inherited =
      step.model && typeof step.model === "object" ? (step.model as Record<string, unknown>) : {};
    step.model = {
      ...inherited,
      ...(selModel ? { model: selModel } : {}),
      ...(selEffort ? { effort: selEffort } : {}),
    } as ManifestStep["model"];
  }
  if (isParent) {
    // Fan-out lives on the SELECTION (the rail patches `sel.strategy` /
    // `sel.task_source`), not on `agent.strategy` — previously only the agent
    // field was read here, so a fan-out configured in the rail silently saved
    // as a plain parallel group with no task_source.
    const selStrategy = selections?.[agent.id]?.strategy;
    const selFanout = selStrategy === "fanout_batch" || selStrategy === "wave_scheduler";
    const selSource = selections?.[agent.id]?.task_source?.source_step;
    const selParser = selections?.[agent.id]?.task_source?.parser ?? "heading_tasks";
    step.subagents = {
      mode: selFanout ? "fanout" : (agent.strategy ?? "sequential"),
      max_parallel: agent.maxParallel ?? 3,
      ...(selFanout && selSource
        ? {
            task_source: {
              kind: "parsed",
              parser: selParser,
              // Composer node id → compiled step agent id (same mapping as
              // depends_on edges): custom nodes are custom-agent:<instance_id>.
              source_step: selSource,
              ...(selections?.[agent.id]?.task_source?.target
                ? { target: selections[agent.id]!.task_source!.target }
                : {}),
            },
          }
        : {}),
      steps: agent.children!.map((child) => agentToManifestStep(child, selections)),
    };
    // A parent's own top-level `strategy` (distinct from `subagents.mode`) is
    // never set by the canvas — if the loaded step had one (e.g. a
    // hand-authored `strategy: single_shot` sitting alongside a `subagents`
    // block), it already survived via the `...extra` spread above; leave it.
  } else if (!isParent) {
    // Leaf fan-out: emit strategy, task_source, fanout, on_conflict when selected
    const selStrategy = selections?.[agent.id]?.strategy;
    if (selStrategy) {
      step.strategy = selStrategy;
      const ts = selections?.[agent.id]?.task_source;
      if (ts) {
        // Merge selection's task_source with any existing one (to preserve author-only fields like spec_step)
        step.task_source = {
          ...(step.task_source ?? {}),
          kind: ts.kind,
          parser: ts.parser,
          source_step: ts.source_step,
          ...(ts.target ? { target: ts.target } : {}),
        };
      }
      const fanout = selections?.[agent.id]?.fanout;
      if (fanout) {
        step.fanout = fanout;
      }
      const onConflict = selections?.[agent.id]?.on_conflict;
      if (onConflict) {
        step.on_conflict = onConflict;
      }
    } else if (step.strategy === undefined) {
      // Only default when the loaded step didn't already declare its own —
      // a leaf step's `strategy` is otherwise author-only (e.g.
      // `wave_scheduler` + `fanout`/`task_source` on a self-fanout step with
      // no `subagents` block), so unconditionally stamping "single_shot" here
      // would clobber it right back out.
      step.strategy = "single_shot";
    }
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
  // A step that's the "step"-trigger target of ANY route.outcomes entry gets
  // its real predecessor from that route, not raw chain position. Auto-wiring
  // a chain `depends_on` onto it too made the compiler's `_compute_is_leaf`
  // (R-26) treat it as non-leaf regardless of which branch actually fired —
  // so BOTH route targets could execute instead of just the one the decision
  // picked (conditional-gates Composer canvas finding: an English decision
  // still ran the Spanish branch too, because it depended_on the English one
  // purely from sitting next to it in the chain). Dual lookup (prefixed
  // backend id + bare instance_id) mirrors `deriveRouteDecisionProduces`
  // above, since a route's free-text Target may be authored as either form.
  const routeTargetIds = new Set<string>();
  if (topLevel) {
    for (const s of steps) {
      for (const outcome of Object.values(s.route?.outcomes ?? {})) {
        if (outcome.trigger === "step" && outcome.target) routeTargetIds.add(outcome.target);
      }
    }
  }
  steps.forEach((step, i) => {
    if (step.subagents) deriveDependsOn(step.subagents.steps, false);
    if (step.depends_on) return; // an explicit declaration always wins
    const deps: string[] = [];
    if (step.subagents) {
      deps.push(...step.subagents.steps.map(stepAgentId).filter(Boolean));
    }
    if (topLevel && i > 0) {
      const isRouteTarget =
        routeTargetIds.has(stepAgentId(step)) || (!!step.instance_id && routeTargetIds.has(step.instance_id));
      if (!isRouteTarget) {
        const previous = stepAgentId(steps[i - 1]);
        if (previous) deps.push(previous);
      }
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
  selections?: Record<string, StepSelectionWire>,
): ManifestStep[] {
  const steps = deriveRouteDecisionProduces(
    deriveDependsOn(
      agents.map((agent) => agentToManifestStep(agent, selections)),
      true,
    ),
  );
  // task_source.source_step must name a compiled step agent_id — the rail
  // stores the composer node id, which for a custom node is the bare
  // instance_id. Map it here, where every step (and its kind) is known;
  // the compiler's upstream guard rejects the bare form.
  const idByBare = new Map<string, string>();
  const index = (list: ManifestStep[]) => {
    for (const st of list) {
      idByBare.set(st.instance_id ?? st.agent ?? "", stepAgentId(st));
      if (st.subagents?.steps) index(st.subagents.steps);
    }
  };
  index(steps);
  const remap = (list: ManifestStep[]) => {
    for (const st of list) {
      // Parent fanout: remap subagents.task_source.source_step
      const ts = st.subagents?.task_source as { source_step?: string } | undefined;
      if (ts?.source_step) ts.source_step = idByBare.get(ts.source_step) ?? ts.source_step;
      // Leaf fanout: remap step.task_source.source_step
      const leafTs = st.task_source as { source_step?: string } | undefined;
      if (leafTs?.source_step) leafTs.source_step = idByBare.get(leafTs.source_step) ?? leafTs.source_step;
      if (st.subagents?.steps) remap(st.subagents.steps);
    }
  };
  remap(steps);
  return steps;
}

/** Top-level `WorkflowManifest` keys `buildWorkflowManifest` computes itself.
 *  Sibling of `MODELED_STEP_KEYS` above, one level up: everything else on a
 *  loaded manifest (`id`, `display_name`, `icon`, `description`,
 *  `input_providers`, `limits`, `seed_files`, `short_name`, `is_beta`,
 *  `user_launchable`, `version`, ...) is opaque to the canvas and must be
 *  preserved rather than dropped on save. */
const MODELED_MANIFEST_KEYS = new Set([
  "steps",
  "capabilities",
  "deliverable",
  "planner",
  "clarify",
  "context_providers",
  "design_mode",
]);

/** Everything on a loaded manifest that `MODELED_MANIFEST_KEYS` doesn't cover. */
function manifestTopLevelExtra(source?: Record<string, unknown> | null): Record<string, unknown> {
  if (!source) return {};
  const extra: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(source)) {
    if (!MODELED_MANIFEST_KEYS.has(key)) extra[key] = value;
  }
  return extra;
}

/** Build the full `WorkflowManifest` (steps + top-level `capabilities`, R-07)
 *  a save should persist once the composition uses any per-node skill,
 *  custom prompt, or sub-agent tree.
 *
 *  `sourceManifest`, when given, is the RAW manifest this composition was
 *  loaded from (e.g. a saved workflow's `manifest_json`) — every top-level
 *  key on it the canvas doesn't model (see `MODELED_MANIFEST_KEYS`) is
 *  preserved byte-for-byte, the same passthrough `agentToManifestStep` does
 *  per step. Omitted entirely (as before) when there is nothing to load from,
 *  e.g. a brand-new composition. */
export function buildWorkflowManifest(
  agents: AgentDef[],
  capabilities?: WorkflowCapabilities,
  selections?: Record<string, StepSelectionWire>,
  runConfig?: WorkflowRunConfig,
  sourceManifest?: Record<string, unknown> | null,
): WorkflowManifest {
  const manifest: WorkflowManifest = {
    ...manifestTopLevelExtra(sourceManifest),
    steps: agentsToManifestSteps(agents, selections),
  };
  if (capabilities && Object.keys(capabilities).length > 0) {
    manifest.capabilities = capabilities;
  }
  if (runConfig?.deliverable) manifest.deliverable = runConfig.deliverable;
  if (runConfig?.planner) manifest.planner = runConfig.planner;
  if (runConfig?.clarify) manifest.clarify = runConfig.clarify;
  // Context provider (run-wide) + the design-picker family. Both are omitted
  // entirely when no provider is declared, so an existing composition's saved
  // manifest is byte-identical to what it was before these existed.
  if (runConfig?.contextProvider) {
    manifest.context_providers = [runConfig.contextProvider];
    if (runConfig.designMode) manifest.design_mode = runConfig.designMode;
  }
  return manifest;
}

/** Read the run-config levers back off a saved manifest — the inverse of the
 *  `buildWorkflowManifest` tail above. Shared by the three cold-mount /
 *  click-driven restore sites (DashboardLayout's `handleLaunchSaved`, and the
 *  `/workflows/{id}/edit` + `/workflows/{id}/run` effects) so they cannot drift
 *  apart the way three hand-copied object literals would. */
export function runConfigFromManifest(
  manifest?: WorkflowManifest | null,
): WorkflowRunConfig {
  return {
    ...(manifest?.deliverable ? { deliverable: manifest.deliverable } : {}),
    ...(manifest?.planner ? { planner: manifest.planner } : {}),
    ...(manifest?.clarify ? { clarify: manifest.clarify } : {}),
    ...(manifest?.context_providers?.[0]
      ? { contextProvider: manifest.context_providers[0] }
      : {}),
    ...(manifest?.design_mode ? { designMode: manifest.design_mode } : {}),
  };
}

/** The free-text summary a "Save as my version" override stores (ISS-226).
 *
 *  An override row persists `manifest`, and `manifest`/`selections` are mutually
 *  exclusive server-side (both write the one `manifest_json` column), so the
 *  `_wizard` bag "Save workflow" writes cannot ride along with it — and the
 *  manifest's own top-level keys are strict-listed (INV-5), so a brief/template
 *  field cannot be added there without a schema change. `description` is the one
 *  free-text field left, so it carries what was actually on screen instead of a
 *  literal. Capped at the column's 2000 chars so a long brief cannot 422 a save.
 */
export function overrideDescription(parts: {
  brief?: string;
  templateId?: string | null;
  designSystemId?: string | null;
}): string {
  const meta = [
    parts.templateId ? `Template: ${parts.templateId}` : null,
    parts.designSystemId ? `Design system: ${parts.designSystemId}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
  const body = [meta, parts.brief?.trim()].filter(Boolean).join("\n\n");
  return body ? body.slice(0, 2000) : "Your saved version of this workflow.";
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
  agent.mechanical = step.mechanical;
  agent.injects = step.injects && step.injects.length > 0 ? [...step.injects] : undefined;
  // Every key on this step the canvas doesn't model — see `AgentDef.extra`.
  agent.extra = captureStepExtra(step);
  if (isCustom) {
    agent.isCustom = true;
    agent.instance_id = step.instance_id;
    agent.prompt = step.prompt;
  }
  // Spec 014 (R-02/T37): reverse of agentToManifestStep's `step.route` write —
  // reopen fix, this was previously missing, silently dropping the route on
  // save→reopen.
  agent.route = step.route ? { ...step.route } : undefined;
  // ISS-178 — carry `depends_on` from the manifest step onto the AgentDef so
  // graphLayout.ts can use it as a third edge source. Steps authored via the
  // API or a hand-written workflow.yaml declare their real predecessors here;
  // without propagating it, computeRootLayout had no way to see the edge and
  // ranked these steps at column 0.
  agent.depends_on = step.depends_on?.length ? [...step.depends_on] : undefined;
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

/** Reverse of `agentToManifestStep`'s `step.gates = selections[...].gates`
 *  write — `gates` lives on the composer's separate `selections` map, not on
 *  `AgentDef`, so `manifestStepsToAgents` (which reconstructs `route` onto
 *  the agent) never touches it. Without this, reopening a saved workflow
 *  restored the route data but left every step's Review-gate dropdown
 *  showing "Off" and its route editor hidden, even though the gate (e.g.
 *  "conditional") and its outcomes were still intact in the manifest. */
export function manifestStepsToGateSelections(
  steps: ManifestStep[],
): Record<string, StepSelectionWire> {
  const out: Record<string, StepSelectionWire> = {};
  const walk = (list: ManifestStep[], isNested: boolean = false) => {
    for (const step of list) {
      const id = step.agent === "custom-agent" ? step.instance_id : step.agent;
      if (id) {
        const entry: StepSelectionWire = {};
        if (step.gates?.length) entry.gates = [...step.gates];
        // Only carry the two author-editable grants back, and only when the
        // saved manifest actually deviates from the read+write default —
        // otherwise every reopened step would gain a redundant `tools` key.
        const read = step.tools?.read_files ?? true;
        const write = step.tools?.write_files ?? true;
        const packs = step.tools?.tool_sets ?? [];
        if (!read || !write || packs.length > 0) {
          entry.tools = { read_files: read, write_files: write };
          if (packs.length > 0) entry.tools.tool_sets = [...packs];
        }
        // Parent fan-out: reverse of the fan-out write in agentToManifestStep
        if (step.subagents?.mode === "fanout") {
          entry.strategy = "fanout_batch";
          const src = (step.subagents as { task_source?: { source_step?: string; parser?: string } })
            .task_source?.source_step;
          const parser = (step.subagents as { task_source?: { parser?: string } })
            .task_source?.parser;
          if (src) {
            entry.task_source = {
              kind: "parsed",
              parser: parser ?? "heading_tasks",
              source_step: src.replace(/^custom-agent:/, ""),
            };
            const target = (step.subagents as { task_source?: { target?: string } })
              .task_source?.target;
            if (target) {
              entry.task_source.target = target;
            }
          }
        }
        // Leaf fan-out: reverse of the leaf fan-out write in agentToManifestStep
        // Copy the full task_source (including author-only fields like spec_step)
        if (!isNested && !step.subagents && (step.strategy === "fanout_batch" || step.strategy === "wave_scheduler")) {
          entry.strategy = step.strategy as "fanout_batch" | "wave_scheduler";
          if (step.task_source) {
            // The rail's source picker offers BARE composer node ids; the saved
            // manifest carries the compiled `custom-agent:<id>` form (the save
            // path re-prefixes). Strip it here or the picker matches no option
            // and silently shows the first step (QA finding F1).
            const ts = step.task_source as { source_step?: string } & Record<string, unknown>;
            entry.task_source = {
              ...ts,
              ...(typeof ts.source_step === "string"
                ? { source_step: ts.source_step.replace(/^custom-agent:/, "") }
                : {}),
            } as StepSelectionWire["task_source"];
          }
          if (step.fanout) {
            entry.fanout = step.fanout;
          }
          if (step.on_conflict) {
            entry.on_conflict = step.on_conflict;
          }
        }
        // Model hydration
        const model = (step as any).model?.model;
        if (model) {
          entry.model = model;
        }
        if (Object.keys(entry).length > 0) out[id] = entry;
      }
      if (step.subagents?.steps) walk(step.subagents.steps, true);
    }
  };
  walk(steps);
  return out;
}

/** Is this saved workflow one the Composer authored?
 *
 *  Derived from the DATA, not from the stamped `base_pipeline_type`: a manifest
 *  carrying `custom-agent` steps can only have come from the Composer. That
 *  matters because `base_pipeline_type` is immutable after create (PATCH strips
 *  it), so a row stamped with a stale type — the shared-`workflowType` leak —
 *  could never be corrected through the UI and would open in the wrong surface
 *  forever. Routing on the manifest repairs those rows without touching them,
 *  and is immune to the same class of bug recurring.
 *
 *  Falls back to the stamped type, so a Composer workflow with no composed
 *  steps (all built-in agents) still resolves correctly. */
export function isComposerWorkflow(saved: {
  base_pipeline_type?: string;
  manifest?: WorkflowManifest | null;
}): boolean {
  if (saved.base_pipeline_type === "custom") return true;
  const walk = (steps: ManifestStep[] | undefined): boolean =>
    (steps ?? []).some(
      (s) => s.agent === "custom-agent" || walk(s.subagents?.steps),
    );
  return walk(saved.manifest?.steps);
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
