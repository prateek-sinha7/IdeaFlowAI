import fc from "fast-check";
import { describe, expect, it } from "vitest";

import { canonicalize } from "@/lib/canonicalManifest";
import { computeDraftState, manifestAsPassthrough } from "@/lib/builderDraft";
import type { ManifestStep, WorkflowManifest } from "@/types/index";

import { buildWorkflowManifest, compiledRootIds } from "./userWorkflows";

// Feature: ai-workflow-builder, Property 31: Render-and-save round trip
// **Validates: Requirements 7.3, 7.4, 10.9, 49.8**

const PROPERTY_OPTIONS = { seed: 20260513, numRuns: 100 } as const;

const IDS = ["analyze", "write", "polish", "review", "plan", "merge", "worker"] as const;
const CHILD_IDS = ["kid-a", "kid-b", "kid-c"] as const;
const GATES = ["human", "conditional", "before-human"] as const;
const PREFIX = "custom-agent:";

const unknownKeyArb = fc
  .tuple(fc.constantFrom("x_note", "x_owner", "x_flag", "x_meta"), fc.string({ maxLength: 8 }))
  .map(([key, value]) => ({ [key]: value }));

/** A leaf step built from patterns 1, 2, 5, 6, 7, 8 and 10 plus unknown keys. */
const leafArb = (id: string): fc.Arbitrary<ManifestStep> =>
  fc
    .record({
      name: fc.option(fc.string({ minLength: 1, maxLength: 10 }), { nil: undefined }),
      prompt: fc.string({ minLength: 1, maxLength: 24 }),
      gates: fc.uniqueArray(fc.constantFrom(...GATES), { maxLength: 2 }),
      read: fc.option(fc.boolean(), { nil: undefined }),
      write: fc.option(fc.boolean(), { nil: undefined }),
      reply: fc.boolean(),
      produces: fc.option(fc.constantFrom("outline", "route_decision"), { nil: undefined }),
      redoable: fc.boolean(),
      effort: fc.option(fc.constantFrom("low", "medium", "high"), { nil: undefined }),
      unknown: fc.option(unknownKeyArb, { nil: undefined }),
      explicitDeps: fc.boolean(),
    })
    .map((f): ManifestStep => {
      const step: ManifestStep & Record<string, unknown> = { agent: "custom-agent", instance_id: id, gates: f.gates };
      if (f.name !== undefined) step.name = f.name;
      step.prompt = f.prompt;
      if (f.read !== undefined || f.write !== undefined) {
        step.tools = { read_files: f.read ?? true, write_files: f.write ?? true };
      }
      if (f.reply) step.reply = "last_message";
      if (f.produces) step.produces = [f.produces];
      if (f.redoable) step.redoable = true;
      if (f.effort) step.model = { model: "m-large", effort: f.effort };
      if (f.unknown) Object.assign(step, f.unknown);
      return step;
    });

/** A step with sub-agents (patterns 3 and 4). */
const parentArb = (id: string): fc.Arbitrary<ManifestStep> =>
  fc
    .tuple(
      leafArb(id),
      fc.constantFrom("parallel", "sequential"),
      fc.uniqueArray(fc.constantFrom(...CHILD_IDS), { minLength: 1, maxLength: 3 }),
      // Absent, 3 and another value are three different workflows (the runtime cap is 5).
      fc.constantFrom<number | undefined>(3, 4, undefined),
    )
    .chain(([parent, mode, kids, maxParallel]) =>
      fc.tuple(...kids.map((kid) => leafArb(`${id}-${kid}`))).map((children): ManifestStep => ({
        ...parent,
        subagents: {
          mode,
          ...(maxParallel === undefined ? {} : { max_parallel: maxParallel }),
          steps: children as ManifestStep[],
        },
      })),
    );

const stepsArb: fc.Arbitrary<ManifestStep[]> = fc
  .uniqueArray(fc.constantFrom(...IDS), { minLength: 1, maxLength: 5 })
  .chain((ids) =>
    fc.tuple(...ids.map((id) => fc.oneof({ weight: 3, arbitrary: leafArb(id) }, { weight: 1, arbitrary: parentArb(id) }))),
  )
  .map((steps) => steps as ManifestStep[])
  .map((steps) =>
    // Half of the drafts spell out the sequential depends_on, as the skill's examples do.
    steps.map((step, index) =>
      index > 0 && step.instance_id && step.instance_id.length % 2 === 0
        ? { ...step, depends_on: [`${PREFIX}${steps[index - 1].instance_id}`] }
        : step,
    ),
  );

const draftArb: fc.Arbitrary<WorkflowManifest> = fc
  .record({
    steps: stepsArb,
    internet: fc.option(fc.boolean(), { nil: undefined }),
    deliverable: fc.option(
      fc.record({ strategy: fc.constantFrom("single_file", "streamed_text"), name: fc.constantFrom("a.md", "page.html") }),
      { nil: undefined },
    ),
    planner: fc.option(fc.constantFrom("skip" as const, "run" as const), { nil: undefined }),
    topUnknown: fc.option(
      fc.record({
        id: fc.constantFrom("wf-one", "wf-two"),
        description: fc.string({ maxLength: 12 }),
        limits: fc.constant({ max_subagents: 8 }),
        chained_from: fc.constant([{ id: "user_stories", text: "Plan" }]),
      }),
      { nil: undefined },
    ),
  })
  .map((f): WorkflowManifest => {
    const manifest: WorkflowManifest = { ...(f.topUnknown ?? {}), steps: f.steps };
    if (f.internet !== undefined) manifest.capabilities = { internet: f.internet };
    if (f.deliverable) manifest.deliverable = f.deliverable;
    if (f.planner) manifest.planner = f.planner;
    return manifest;
  });

/** Apply a draft to the composer state and build the Save payload with no edits. */
function renderAndSave(draft: WorkflowManifest) {
  const state = computeDraftState(draft);
  const manifest = buildWorkflowManifest(
    state.pipelineAgents,
    state.capabilities,
    state.selections,
    state.runConfig,
    manifestAsPassthrough(draft),
  );
  return {
    base_pipeline_type: "custom" as const,
    agent_ids: compiledRootIds(manifest),
    manifest,
  };
}

describe("Property 31: render-and-save round trip", () => {
  it("keeps the base, the agent_ids and the canonical manifest of the draft", () => {
    fc.assert(
      fc.property(draftArb, (draft) => {
        const payload = renderAndSave(draft);

        expect(payload.base_pipeline_type).toBe("custom");
        expect(payload.agent_ids).toEqual(compiledRootIds(draft));
        expect(canonicalize({ ...payload.manifest })).toEqual(canonicalize({ ...draft }));
      }),
      PROPERTY_OPTIONS,
    );
  });

  it("carries unknown top-level and step keys through unchanged", () => {
    fc.assert(
      fc.property(draftArb, (draft) => {
        const saved: Record<string, unknown> = { ...renderAndSave(draft).manifest };
        for (const key of ["id", "description", "limits", "chained_from"]) {
          if (key in draft) expect(saved[key]).toEqual((draft as unknown as Record<string, unknown>)[key]);
        }
        draft.steps.forEach((draftStep, index) => {
          const step = draftStep as unknown as Record<string, unknown>;
          const savedStep = (saved.steps as Record<string, unknown>[])[index];
          for (const key of Object.keys(step).filter((k) => k.startsWith("x_"))) {
            expect(savedStep[key]).toBe(step[key]);
          }
        });
      }),
      PROPERTY_OPTIONS,
    );
  });
});
