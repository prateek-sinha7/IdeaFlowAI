/**
 * Round-trip regression for the bug measured against the live DB row
 * `workflows.id = f4994856-7b61-45d7-8c57-9e538f745e36` ("PDF to Prototype
 * v2"): saving a workflow the canvas loaded from a hand-authored manifest
 * silently dropped every key the canvas doesn't model — `strategy:
 * wave_scheduler`, `fanout`, `task_source`, `produces`/`consumes`,
 * `validators`, `redoable`, `fix`, `compaction`, `injects`, an explicit
 * parent-level `depends_on`/`strategy`, `tools.spawn_subagents`, and most of
 * the top-level manifest (`input_providers`, `limits`, `seed_files`, `id`,
 * `display_name`, `icon`, `description`, `version`, `user_launchable`).
 *
 * This test loads a trimmed, structurally-faithful copy of the real
 * `pdf_to_prototype/workflow.yaml` (see `__fixtures__/pdfToPrototypeManifest`
 * for why it's JSON, not the YAML file itself), converts it to the canvas
 * model, renames ONE step, converts back, and asserts the ONLY difference
 * from a no-op round trip is that rename.
 *
 * Comparing against a NO-OP round trip (rather than the raw fixture) is a
 * deliberate choice: `deriveDependsOn`/`deriveRouteDecisionProduces` always
 * emit an explicit `depends_on`/`gates` (even `[]`) where the hand-authored
 * YAML simply omits the key for a step with no upstream (e.g.
 * `journey-designer`, reached only via a route target, never chain
 * position). That normalisation is pre-existing, deliberate canvas behaviour
 * unrelated to this bug — diffing rename-vs-no-op isolates exactly the
 * regression this test guards, instead of also asserting on that unrelated
 * quirk.
 */
import { describe, it, expect } from "vitest";
import { buildWorkflowManifest, mapAgentInTree, runConfigFromManifest } from "./userWorkflows";
import { workflowCanvasModel } from "@/lib/workflowCanvasModel";
import type { ManifestStep, WorkflowCapabilities, WorkflowManifest } from "@/types/index";
import { PDF_TO_PROTOTYPE_MANIFEST_FIXTURE } from "./__fixtures__/pdfToPrototypeManifest";

/** Load the fixture → canvas model → back to a full manifest, optionally
 *  renaming one step's `name` along the way. Mirrors ComposerPage's actual
 *  save call (`buildWorkflowManifest(pipelineAgents, capabilities,
 *  selections, runConfig, ...)`), plus the `sourceManifest` passthrough arg. */
function roundTrip(rename?: { instanceId: string; name: string }): WorkflowManifest {
  const source = structuredClone(PDF_TO_PROTOTYPE_MANIFEST_FIXTURE);
  const steps = source.steps as unknown as ManifestStep[];
  const model = workflowCanvasModel(steps);
  const agents = rename
    ? mapAgentInTree(model.agents, rename.instanceId, (a) => ({ ...a, name: rename.name }))
    : model.agents;
  const capabilities = source.capabilities as WorkflowCapabilities;
  const runConfig = runConfigFromManifest(source as unknown as WorkflowManifest);
  return buildWorkflowManifest(agents, capabilities, model.selections, runConfig, source);
}

describe("pdf_to_prototype manifest round trip (canvas load -> rename -> save)", () => {
  it("changes only the renamed step's name relative to a no-op round trip", () => {
    const baseline = roundTrip();
    const renamed = roundTrip({ instanceId: "journey-designer", name: "Journey Designer Renamed" });

    const expected = structuredClone(baseline);
    const jd = expected.steps.find((s) => s.instance_id === "journey-designer")!;
    jd.name = "Journey Designer Renamed";

    expect(renamed).toEqual(expected);
  });

  it("screen-builder's wave-scheduler shape survives (strategy/fanout/task_source)", () => {
    const manifest = roundTrip();
    const screenBuilder = manifest.steps.find((s) => s.instance_id === "screen-builder")!;
    expect(screenBuilder.strategy).toBe("wave_scheduler");
    expect((screenBuilder as unknown as Record<string, unknown>).fanout).toEqual({
      agent: "self",
      max_parallel: 5,
      mode: "parallel",
    });
    expect((screenBuilder as unknown as Record<string, unknown>).task_source).toEqual({
      kind: "parsed",
      parser: "json_tasks",
      source_step: "custom-agent:plan-lead",
      spec_step: "custom-agent:journey-designer",
      target: "tasks.json",
    });
  });

  it("plan-lead's validators survive", () => {
    const manifest = roundTrip();
    const planLead = manifest.steps.find((s) => s.instance_id === "plan-lead")!;
    expect((planLead as unknown as Record<string, unknown>).validators).toEqual(["spec_plan_coverage"]);
  });

  it("the top-level input_providers survives", () => {
    const manifest = roundTrip();
    expect((manifest as unknown as Record<string, unknown>).input_providers).toEqual(["pdf_pages"]);
  });

  it("synthesizer keeps its explicit depends_on, top-level strategy, and tools.spawn_subagents", () => {
    const manifest = roundTrip();
    const synthesizer = manifest.steps.find((s) => s.instance_id === "synthesizer")!;
    expect(synthesizer.depends_on).toEqual(["custom-agent:reading-planner"]);
    expect(synthesizer.strategy).toBe("single_shot");
    expect(synthesizer.tools?.spawn_subagents).toBe(true);
    expect(synthesizer.subagents?.steps.map((s) => s.instance_id)).toEqual(["reader-1", "reader-2"]);
  });
});
