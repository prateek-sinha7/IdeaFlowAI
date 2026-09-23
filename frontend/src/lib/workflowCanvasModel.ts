/**
 * The ONE conversion from a workflow manifest to the canvas's data model.
 *
 * `CanvasView` does not take a manifest — it takes `AgentDef[]` (a tree, nesting
 * carried on `.children`) plus a `SelectionsMap` (where per-step gates live).
 * Something must bridge the two, and that bridge is what used to be copied:
 * `ComposerPage` did it correctly from `initialManifestSteps`, while the Advanced
 * popup was handed the launch ROSTER instead — a flat list built for
 * "which agents will run", which has no tree to render. Same canvas, different
 * input, so the popup drew a fan-out parent with an empty "+ Sub-agent" slot.
 *
 * Both surfaces now call this. A fix here reaches both by construction.
 *
 * NOTE ON IDS — this returns the COMPOSER's convention, where a custom step is
 * keyed by its bare `instance_id` ("page"), because that is what `CanvasView`,
 * `SelectionsMap` and the composer's edit handlers have always used. It is NOT
 * the launch roster's node-id convention ("custom-agent:page"), which is what
 * `agent_ids` is built from at launch. Do not feed this model to a launch
 * payload; it is for rendering and editing the graph.
 */

import { manifestStepsToAgents, manifestStepsToGateSelections } from "@/store/api/userWorkflows";
import type { AgentDef, ManifestStep } from "@/types";

export type SelectionsMap = Record<string, Record<string, unknown>>;

export interface WorkflowCanvasModel {
  /** The step tree, with a fan-out parent's sub-agents on `.children`. */
  agents: AgentDef[];
  /** Per-step levers; `gates` are seeded from the manifest's declarations. */
  selections: SelectionsMap;
}

/**
 * Build the canvas model from a manifest's raw steps.
 *
 * @param steps          `manifest_json.steps` / `WorkflowDetail.manifest_steps`.
 * @param libraryAgents  the agent library, for hydrating a built-in step's
 *                       icon/description. May be empty (it loads async at
 *                       sign-in) — every caller should re-run once it fills, or
 *                       built-in steps render with placeholder presentation.
 * @param baseSelections levers already chosen by the user. Manifest-declared
 *                       `gates` win per step; every other key is preserved.
 */
export function workflowCanvasModel(
  steps: ManifestStep[] | undefined | null,
  libraryAgents: AgentDef[] = [],
  baseSelections?: SelectionsMap,
): WorkflowCanvasModel {
  if (!steps?.length) return { agents: [], selections: { ...(baseSelections ?? {}) } };

  const agents = manifestStepsToAgents(steps, (id) =>
    libraryAgents.find((a) => a.id === id),
  );

  const selections: SelectionsMap = { ...(baseSelections ?? {}) };
  for (const [agentId, patch] of Object.entries(manifestStepsToGateSelections(steps))) {
    selections[agentId] = { ...selections[agentId], ...patch };
  }

  return { agents, selections };
}
