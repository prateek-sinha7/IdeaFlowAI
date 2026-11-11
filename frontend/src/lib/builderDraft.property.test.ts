import fc from "fast-check";
import { describe, expect, it } from "vitest";

import {
  buildWorkflowManifest,
  manifestStepsToAgents,
  manifestStepsToGateSelections,
} from "@/store/api/userWorkflows";
import type { AgentDef, ManifestStep, WorkflowManifest } from "@/types/index";

import {
  computeDraftState,
  draftApplyAction,
  isUnsaved,
  manifestAsPassthrough,
  rebuildDraftAgents,
  type DraftComposerState,
} from "./builderDraft";

// Feature: ai-workflow-builder, Property 33: Applying drafts replaces state and keeps it unsaved
// **Validates: Requirements 7.5, 7.8, 23.16**

// Fixed seed keeps failures reproducible.
const PROPERTY_OPTIONS = { seed: 20260512, numRuns: 200 } as const;

const CUSTOM_IDS = ["draft-a", "draft-b", "draft-c", "draft-d", "draft-e"] as const;
const BUILTIN_IDS = ["ba", "architect"] as const;
const GATES = ["human", "conditional", "auto"] as const;
const MODELS = ["m-small", "m-large"] as const;
const EFFORTS = ["low", "medium", "high"] as const;

/** The agent library the page resolves built-in steps through once it loads. */
function lookup(id: string): AgentDef | undefined {
  if (!(BUILTIN_IDS as readonly string[]).includes(id)) return undefined;
  return {
    id,
    name: `Library ${id}`,
    role: "Library role",
    description: "from the library",
    pipeline_type: "custom",
    order: 0,
    icon: "",
    estimated_duration: 60,
    has_skill: false,
  };
}

const stepArb = (id: string, builtin: boolean): fc.Arbitrary<ManifestStep> =>
  fc
    .record({
      name: fc.option(fc.string({ minLength: 1, maxLength: 12 }), { nil: undefined }),
      prompt: fc.string({ maxLength: 20 }),
      gates: fc.option(fc.uniqueArray(fc.constantFrom(...GATES), { maxLength: 2 }), { nil: undefined }),
      model: fc.option(
        fc.record({
          model: fc.constantFrom(...MODELS),
          effort: fc.option(fc.constantFrom(...EFFORTS), { nil: undefined }),
        }),
        { nil: undefined },
      ),
    })
    .map((f): ManifestStep => {
      const step: ManifestStep = builtin ? { agent: id } : { agent: "custom-agent", instance_id: id };
      if (f.name !== undefined) step.name = f.name;
      if (!builtin) step.prompt = f.prompt;
      if (f.gates?.length) step.gates = f.gates;
      if (f.model) {
        step.model = { model: f.model.model };
        if (f.model.effort) step.model.effort = f.model.effort;
      }
      return step;
    });

/** Steps with unique ids: a subset of the custom pool and of the built-in pool, in any order. */
const stepsArb: fc.Arbitrary<ManifestStep[]> = fc
  .tuple(
    fc.uniqueArray(fc.constantFrom(...CUSTOM_IDS), { maxLength: CUSTOM_IDS.length }),
    fc.uniqueArray(fc.constantFrom(...BUILTIN_IDS), { maxLength: BUILTIN_IDS.length }),
  )
  .chain(([custom, builtin]) =>
    fc
      .shuffledSubarray([...custom, ...builtin], { minLength: custom.length + builtin.length })
      .chain((ids) =>
        fc.tuple(...ids.map((id) => stepArb(id, (BUILTIN_IDS as readonly string[]).includes(id)))),
      ),
  )
  .map((steps) => steps as ManifestStep[]);

/** A draft manifest without the per-draft marker key, which the sequence adds. */
const draftBodyArb: fc.Arbitrary<WorkflowManifest> = fc
  .record({
    steps: stepsArb,
    internet: fc.option(fc.boolean(), { nil: undefined }),
    deliverable: fc.option(
      fc.record({
        strategy: fc.constantFrom("single_file", "multi_file"),
        name: fc.string({ minLength: 1, maxLength: 10 }),
      }),
      { nil: undefined },
    ),
    planner: fc.option(fc.constantFrom("skip" as const, "run" as const), { nil: undefined }),
  })
  .map((f): WorkflowManifest => {
    const manifest: WorkflowManifest = { steps: f.steps };
    if (f.internet !== undefined) manifest.capabilities = { internet: f.internet };
    if (f.deliverable) manifest.deliverable = f.deliverable;
    if (f.planner) manifest.planner = f.planner;
    return manifest;
  });

type Event =
  | { kind: "draft"; manifest: WorkflowManifest; redeliver: boolean }
  | { kind: "library" }
  | { kind: "save" };

const eventArb: fc.Arbitrary<Event> = fc.oneof(
  { weight: 5, arbitrary: draftBodyArb.map((manifest): Event => ({ kind: "draft", manifest, redeliver: false })) },
  { weight: 1, arbitrary: draftBodyArb.map((manifest): Event => ({ kind: "draft", manifest, redeliver: true })) },
  { weight: 1, arbitrary: fc.constant<Event>({ kind: "library" }) },
  { weight: 2, arbitrary: fc.constant<Event>({ kind: "save" }) },
);

/** The composer fields that a draft replaces and that Save reads. */
interface ComposerModel extends DraftComposerState {
  /** Name, which a draft never touches. */
  name: string;
  draftSource: WorkflowManifest | null;
  draftDirty: boolean;
  baseline: string;
  appliedRevision: number | null;
  agentsBuiltWithLibrary: boolean;
  libraryLoaded: boolean;
  /** The draft the host currently hands to the page (`builder.draft`). */
  hostDraft: { revision: number; manifest: WorkflowManifest } | null;
  lastSaved: { manifest: WorkflowManifest } | null;
  revisionCounter: number;
}

function snapshotOf(model: Pick<ComposerModel, "name" | "pipelineAgents">): string {
  return `${model.name}\u0000${model.pipelineAgents.map((a) => `${a.id}:${a.name}`).join(",")}`;
}

function unsavedOf(model: ComposerModel): boolean {
  return isUnsaved({ snapshot: snapshotOf(model), baseline: model.baseline, draftDirty: model.draftDirty });
}

function mountedComposer(): ComposerModel {
  const model: ComposerModel = {
    pipelineAgents: [],
    selections: {},
    capabilities: {},
    runConfig: {},
    name: "My workflow",
    draftSource: null,
    draftDirty: false,
    baseline: "",
    appliedRevision: null,
    agentsBuiltWithLibrary: false,
    libraryLoaded: false,
    hostDraft: null,
    lastSaved: null,
    revisionCounter: 0,
  };
  model.baseline = snapshotOf(model);
  return model;
}

/** What the page's apply effect does for the current `builder.draft` and library. */
function runApplyEffect(model: ComposerModel): void {
  const action = draftApplyAction({
    lastAppliedRevision: model.appliedRevision,
    draftRevision: model.hostDraft?.revision ?? null,
    libraryLoaded: model.libraryLoaded,
    agentsBuiltWithLibrary: model.agentsBuiltWithLibrary,
  });
  if (action === "none" || !model.hostDraft) return;
  const lookupNow = model.libraryLoaded ? lookup : undefined;
  if (action === "apply") {
    const next = computeDraftState(model.hostDraft.manifest, lookupNow);
    model.pipelineAgents = next.pipelineAgents;
    model.selections = next.selections;
    model.capabilities = next.capabilities;
    model.runConfig = next.runConfig;
    model.draftSource = model.hostDraft.manifest;
    model.draftDirty = true;
    model.appliedRevision = model.hostDraft.revision;
  } else {
    // The page re-captures its baseline when nothing was unsaved before the rebuild.
    const wasClean = !unsavedOf(model);
    model.pipelineAgents = rebuildDraftAgents(model.hostDraft.manifest, lookupNow);
    if (wasClean) model.baseline = snapshotOf(model);
  }
  model.agentsBuiltWithLibrary = model.libraryLoaded;
}

/** The save manifest, as `getManifest` builds it. */
function saveManifest(model: ComposerModel): WorkflowManifest {
  return buildWorkflowManifest(
    model.pipelineAgents,
    model.capabilities,
    model.selections,
    model.runConfig,
    model.draftSource ? manifestAsPassthrough(model.draftSource) : null,
  );
}

function step(model: ComposerModel, event: Event): void {
  if (event.kind === "draft") {
    // Each draft gets a marker key only it carries, so passthrough leaks are visible.
    const revision = event.redeliver && model.hostDraft ? model.hostDraft.revision : ++model.revisionCounter;
    const manifest =
      event.redeliver && model.hostDraft
        ? model.hostDraft.manifest
        : { ...event.manifest, [`marker_${revision}`]: revision };
    model.hostDraft = { revision, manifest };
    runApplyEffect(model);
  } else if (event.kind === "library") {
    model.libraryLoaded = true;
    runApplyEffect(model);
  } else {
    // A successful save: the draft is persisted, and the page re-captures its baseline.
    model.lastSaved = { manifest: saveManifest(model) };
    model.draftDirty = false;
    model.baseline = snapshotOf(model);
  }
}

function stepId(s: ManifestStep): string {
  return s.agent === "custom-agent" ? (s.instance_id ?? "") : (s.agent ?? "");
}

describe("Property 33: applying drafts replaces state and keeps it unsaved", () => {
  it("after any sequence the composer equals the last applied draft's state", () => {
    fc.assert(
      fc.property(fc.array(eventArb, { minLength: 1, maxLength: 12 }), (events) => {
        const model = mountedComposer();
        for (const event of events) step(model, event);

        const applied = model.hostDraft;
        if (!applied) {
          // No draft arrived: nothing was replaced.
          expect(model.pipelineAgents).toEqual([]);
          expect(model.draftSource).toBeNull();
          return;
        }
        const last = applied.manifest;
        const expected = computeDraftState(last, model.libraryLoaded ? lookup : undefined);

        expect(model.draftSource).toBe(last);
        expect(model.pipelineAgents.map((a) => a.id)).toEqual(last.steps.map(stepId));
        expect(model.pipelineAgents).toEqual(expected.pipelineAgents);
        expect(model.selections).toEqual(manifestStepsToGateSelections(last.steps));
        expect(model.selections).toEqual(expected.selections);
        expect(model.capabilities).toEqual(last.capabilities ?? {});
        expect(model.runConfig).toEqual({
          ...(last.deliverable ? { deliverable: last.deliverable } : {}),
          ...(last.planner ? { planner: last.planner } : {}),
        });
      }),
      PROPERTY_OPTIONS,
    );
  });

  it("the save manifest carries the last draft's passthrough keys and none of the earlier ones", () => {
    fc.assert(
      fc.property(fc.array(eventArb, { minLength: 1, maxLength: 12 }), (events) => {
        const model = mountedComposer();
        for (const event of events) step(model, event);
        const last = model.hostDraft;
        fc.pre(last !== null);
        if (!last) return;

        const saved: Record<string, unknown> = { ...saveManifest(model) };
        const markers = Object.keys(saved).filter((k) => k.startsWith("marker_"));

        expect(markers).toEqual([`marker_${last.revision}`]);
        expect(saved.steps).toEqual(
          buildWorkflowManifest(
            manifestStepsToAgents(last.manifest.steps, model.libraryLoaded ? lookup : undefined),
            model.capabilities,
            manifestStepsToGateSelections(last.manifest.steps),
            model.runConfig,
          ).steps,
        );
      }),
      PROPERTY_OPTIONS,
    );
  });

  it("reports unsaved work after every apply and until a save succeeds", () => {
    fc.assert(
      fc.property(fc.array(eventArb, { minLength: 1, maxLength: 12 }), (events) => {
        const model = mountedComposer();
        let expectUnsaved = false;
        for (const event of events) {
          const before = model.appliedRevision;
          step(model, event);
          const applied = model.appliedRevision !== before;
          if (event.kind === "save") expectUnsaved = false;
          else if (applied) expectUnsaved = true;

          // The baseline is never reset by an apply, and a save only clears the report.
          expect(model.draftDirty).toBe(expectUnsaved);
          if (expectUnsaved) {
            expect(unsavedOf(model)).toBe(true);
          } else {
            // No pending draft and no edit: a library load after a save renames built-in
            // steps, and that must not read as unsaved work.
            expect(unsavedOf(model)).toBe(false);
          }
        }
      }),
      PROPERTY_OPTIONS,
    );
  });

  it("applies each revision once: a redelivered draft keeps manual edits and the report", () => {
    fc.assert(
      fc.property(draftBodyArb, draftBodyArb, (first, edited) => {
        const model = mountedComposer();
        step(model, { kind: "draft", manifest: first, redeliver: false });
        // A manual edit after the apply.
        model.pipelineAgents = manifestStepsToAgents(edited.steps);
        const editedAgents = model.pipelineAgents;

        step(model, { kind: "draft", manifest: first, redeliver: true });

        expect(model.pipelineAgents).toBe(editedAgents);
        expect(model.draftDirty).toBe(true);
      }),
      PROPERTY_OPTIONS,
    );
  });

  it("a draft equal to the saved canvas still reports unsaved work", () => {
    fc.assert(
      fc.property(draftBodyArb, (body) => {
        const model = mountedComposer();
        step(model, { kind: "draft", manifest: body, redeliver: false });
        step(model, { kind: "save" });
        expect(unsavedOf(model)).toBe(false);

        // The same content again as a new revision.
        step(model, { kind: "draft", manifest: body, redeliver: false });

        expect(snapshotOf(model)).toBe(model.baseline);
        expect(unsavedOf(model)).toBe(true);
      }),
      PROPERTY_OPTIONS,
    );
  });
});
