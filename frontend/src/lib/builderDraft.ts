/**
 * Pure state computation for applying an AI-builder draft to the Composer
 * (design §3.10.7, Req 7.2 to 7.8).
 *
 * `ComposerPage` owns the React state; this module owns the arithmetic, so the
 * "a draft replaces state and stays unsaved" rules can be tested without
 * rendering the page.
 */

import {
  manifestStepsToAgents,
  manifestStepsToGateSelections,
  runConfigFromManifest,
} from "@/store/api/userWorkflows";
import type { AgentDef, WorkflowCapabilities, WorkflowManifest, WorkflowRunConfig } from "@/types/index";
import type { TargetTrust } from "@/types/workflowBuilder";

/** Per-step selections as `manifestStepsToGateSelections` returns them. */
export type DraftSelections = ReturnType<typeof manifestStepsToGateSelections>;

/** Resolves a built-in step's full `AgentDef` from the agent library. */
export type AgentLookup = (id: string) => AgentDef | undefined;

/** The composer state a draft replaces (Req 7.5: a draft is a full replacement). */
export interface DraftComposerState {
  pipelineAgents: AgentDef[];
  selections: DraftSelections;
  capabilities: WorkflowCapabilities;
  runConfig: WorkflowRunConfig;
}

/** Compute every piece of composer state that a draft replaces. */
export function computeDraftState(manifest: WorkflowManifest, lookup?: AgentLookup): DraftComposerState {
  return {
    pipelineAgents: manifestStepsToAgents(manifest.steps, lookup),
    selections: manifestStepsToGateSelections(manifest.steps),
    capabilities: manifest.capabilities ?? {},
    runConfig: runConfigFromManifest(manifest),
  };
}

/** Rebuild only the agent tree, used when the agent library loads after the draft was applied. */
export function rebuildDraftAgents(manifest: WorkflowManifest, lookup?: AgentLookup): AgentDef[] {
  return manifestStepsToAgents(manifest.steps, lookup);
}

/** What the apply effect should do for the current draft. */
export type DraftApplyAction = "none" | "apply" | "rebuild_agents";

/**
 * Decide the apply step. A draft is applied once per revision. When it was
 * applied while the library was still empty, the agents are rebuilt once the
 * library has loaded (the built-in steps then resolve their full definitions).
 */
export function draftApplyAction(input: {
  lastAppliedRevision: number | null;
  draftRevision: number | null;
  libraryLoaded: boolean;
  agentsBuiltWithLibrary: boolean;
}): DraftApplyAction {
  const { lastAppliedRevision, draftRevision, libraryLoaded, agentsBuiltWithLibrary } = input;
  if (draftRevision === null) return "none";
  if (draftRevision !== lastAppliedRevision) return "apply";
  return libraryLoaded && !agentsBuiltWithLibrary ? "rebuild_agents" : "none";
}

/**
 * The unsaved-work rule (Req 7.8): the roster/name snapshot differs from the
 * baseline, or a draft was applied and not yet saved. A `null` baseline means
 * "not captured yet", which is not a difference.
 */
export function isUnsaved(input: {
  snapshot: string;
  baseline: string | null;
  draftDirty: boolean;
}): boolean {
  const { snapshot, baseline, draftDirty } = input;
  return (baseline !== null && snapshot !== baseline) || draftDirty;
}

/**
 * Copy a typed manifest into the loose record `buildWorkflowManifest` takes as
 * its passthrough source, without a cast.
 */
export function manifestAsPassthrough(manifest: WorkflowManifest): Record<string, unknown> {
  return { ...manifest };
}

/** Banner shown while a builder turn is running (Req 9.3, 9.4). */
export const BUILDER_UPDATING_MESSAGE = "The builder is updating this workflow.";

/** Note shown when Run once is held back at `db` trust (Req 7.12). */
export const BUILDER_DB_TRUST_RUN_NOTE =
  "An unsaved canvas runs at user trust. Save the workflow to run it at the trust it needs.";

/** Why the builder holds Run once back: a running turn, or an unsaved `db` draft. */
export type BuilderRunBlock = "turn_running" | "db_trust_unsaved" | null;

/**
 * Decide whether the builder blocks Run once (design §3.10.7 items 4 and 5).
 * A running turn wins over the trust note, because nothing can run while the
 * canvas is changing. The trust note applies only when the most recently
 * applied draft was checked at `db` trust and the canvas has unsaved changes.
 */
export function builderRunBlock(input: {
  turnRunning: boolean;
  draftTrust: TargetTrust | null;
  dirty: boolean;
}): BuilderRunBlock {
  if (input.turnRunning) return "turn_running";
  if (input.draftTrust === "db" && input.dirty) return "db_trust_unsaved";
  return null;
}

/**
 * The name and description a draft pre-fills into the Save fields (Req 10.2).
 * The name is the manifest's `name`, or its `id` when `name` is absent. Both
 * are read from the wire manifest, because `WorkflowManifest` does not model
 * them. `name` is `undefined` when the draft has neither, so the caller keeps
 * the name it already has.
 */
export function draftSaveDefaults(manifest: Readonly<Record<string, unknown>>): {
  name: string | undefined;
  description: string;
} {
  const text = (value: unknown): string | undefined =>
    typeof value === "string" && value.trim() !== "" ? value : undefined;
  return {
    name: text(manifest.name) ?? text(manifest.id),
    description: text(manifest.description) ?? "",
  };
}

/** The pre-filled name for "Save as new" on a saved row: "<name> (AI)" (Req 10.10, G-34). */
export function aiCopyName(rowName: string): string {
  return `${rowName} (AI)`;
}

/**
 * The name to try after a 409 on "Save as new" (G-34): "<stem>" becomes
 * "<stem> 2", then "<stem> 3", and so on. Returns `null` when the current name
 * is neither the stem nor a numbered form of it, so a name the user typed is
 * left alone.
 */
export function nextAiCopyName(current: string, stem: string): string | null {
  if (current === stem) return `${stem} 2`;
  const prefix = `${stem} `;
  if (!current.startsWith(prefix)) return null;
  const digits = current.slice(prefix.length);
  if (!/^\d+$/.test(digits)) return null;
  const number = Number(digits);
  return number >= 2 ? `${stem} ${number + 1}` : null;
}

/** True for an HTTP 409 (duplicate name) raised by the save request. */
export function isConflictError(error: unknown): boolean {
  return typeof error === "object" && error !== null && "status" in error && error.status === 409;
}
