/**
 * Regression: a Composer save must not strip the manifest keys the canvas has
 * no editor for.
 *
 * Observed on the saved "PDF to Prototype v2" row: opening it in the Composer
 * and saving rewrote `manifest_json` through `agentsToManifestSteps`, which at
 * the time emitted only the keys the canvas models. Three `wave_scheduler`
 * steps collapsed to `single_shot` (losing `fanout`, `task_source`,
 * `injects`), `depends_on` was wiped on five steps, and every
 * `consumes`/`produces`/`validators`/`fix`/`require_render` contract was
 * dropped — a row that could no longer run.
 *
 * The fix is `AgentDef.extra`: `manifestStepToAgent` captures every key
 * outside `MODELED_STEP_KEYS` verbatim, and `agentToManifestStep` re-spreads
 * it FIRST so canvas-owned fields still win on conflict. These tests pin that
 * a load → save cycle that touches nothing is byte-identical.
 */
import { describe, it, expect } from "vitest";
import {
  agentsToManifestSteps,
  manifestStepsToAgents,
  manifestStepsToGateSelections,
} from "./userWorkflows";
import { PDF_TO_PROTOTYPE_MANIFEST_FIXTURE } from "./__fixtures__/pdfToPrototypeManifest";
import type { ManifestStep } from "@/types/index";

/** The author-only keys (`fanout`, `task_source`, `consumes`, `validators`,
 *  `fix`, `compaction`, `injects`, `on_conflict`, `redoable`,
 *  `require_render`, ...) are deliberately NOT on `ManifestStep`: the canvas
 *  treats them as opaque and carries them through `AgentDef.extra`. Widen only
 *  here, in the test that reads them, rather than teaching the product type
 *  about fields it must never interpret. */
type AuthoredStep = ManifestStep & Record<string, unknown>;

const FIXTURE_STEPS = PDF_TO_PROTOTYPE_MANIFEST_FIXTURE.steps as AuthoredStep[];

/** Load → save with no edit in between, exactly what "open it and press Save"
 *  does. Gates travel on the separate selections channel, not on `AgentDef`,
 *  so the real save path (`ComposerPage`) threads them back through the second
 *  argument — model that here or the comparison is unfaithful. */
function roundTrip(steps: ManifestStep[]): AuthoredStep[] {
  return agentsToManifestSteps(
    manifestStepsToAgents(steps),
    manifestStepsToGateSelections(steps),
  ) as AuthoredStep[];
}

function byId(steps: ManifestStep[], instanceId: string): AuthoredStep {
  const hit = steps.find((s) => s.instance_id === instanceId);
  if (!hit) throw new Error(`no step ${instanceId} in ${steps.map((s) => s.instance_id).join(", ")}`);
  return hit as AuthoredStep;
}

describe("Composer round trip preserves author-only manifest keys", () => {
  it("an untouched load → save loses no key and changes no value", () => {
    // The one tolerated difference is an ADDED `depends_on: []` on a step that
    // declared no dependencies. `deriveDependsOn` always emits the key, and the
    // compiler reads it as `depends_on or []`, so an empty list and an absent
    // key are the same plan. Anything else — a dropped key, or a key whose
    // value changed — is the regression this file exists to catch.
    const after = roundTrip(FIXTURE_STEPS);

    const compare = (before: AuthoredStep[], got: AuthoredStep[], path: string) => {
      expect(got.map((s) => s.instance_id ?? s.agent)).toEqual(
        before.map((s) => s.instance_id ?? s.agent),
      );
      before.forEach((beforeStep, i) => {
        const gotStep = got[i];
        const where = `${path}${beforeStep.instance_id ?? beforeStep.agent}`;

        for (const key of Object.keys(beforeStep)) {
          if (key === "subagents") continue; // walked recursively below
          expect({ where, key, value: gotStep[key] }).toEqual({
            where,
            key,
            value: beforeStep[key],
          });
        }

        const added = Object.keys(gotStep).filter((k) => !(k in beforeStep));
        expect({ where, added }).toEqual({
          where,
          added: added.filter((k) => k === "depends_on" && (gotStep.depends_on ?? []).length === 0),
        });

        if (beforeStep.subagents || gotStep.subagents) {
          expect(gotStep.subagents?.mode).toEqual(beforeStep.subagents?.mode);
          expect(gotStep.subagents?.max_parallel).toEqual(beforeStep.subagents?.max_parallel);
          compare(
            (beforeStep.subagents?.steps ?? []) as AuthoredStep[],
            (gotStep.subagents?.steps ?? []) as AuthoredStep[],
            `${where} > `,
          );
        }
      });
    };

    compare(FIXTURE_STEPS, after, "");
  });

  it("a wave_scheduler step keeps its strategy, fanout and task_source", () => {
    // The headline regression: this step has no `subagents` block, so the
    // pre-fix serialiser rebuilt it as a plain leaf and it became single_shot.
    const before = byId(FIXTURE_STEPS, "screen-builder");
    const after = byId(roundTrip(FIXTURE_STEPS), "screen-builder");

    expect(before.strategy).toBe("wave_scheduler");
    expect(after.strategy).toBe("wave_scheduler");
    expect(after.fanout).toEqual(before.fanout);
    expect(after.task_source).toEqual(before.task_source);
    expect(after.on_conflict).toEqual(before.on_conflict);
  });

  it("artifact contracts and validators survive", () => {
    const before = byId(FIXTURE_STEPS, "plan-lead");
    const after = byId(roundTrip(FIXTURE_STEPS), "plan-lead");

    expect(after.consumes).toEqual(before.consumes);
    expect(after.produces).toEqual(before.produces);
    expect(after.validators).toEqual(before.validators);
    expect(after.fix).toEqual(before.fix);
    expect(after.redoable).toEqual(before.redoable);
  });

  it("compaction and injects survive", () => {
    const before = byId(FIXTURE_STEPS, "shell-builder");
    const after = byId(roundTrip(FIXTURE_STEPS), "shell-builder");

    expect(after.compaction).toEqual(before.compaction);
    expect(after.injects).toEqual(before.injects);
  });

  it("an explicit depends_on is not wiped", () => {
    // `depends_on` is derived by the canvas for ordinary chains, but a
    // hand-authored one must not be replaced by an empty list.
    const withDeps = FIXTURE_STEPS.filter(
      (s) => Array.isArray(s.depends_on) && s.depends_on.length > 0,
    );
    expect(withDeps.length).toBeGreaterThan(0);

    const after = roundTrip(FIXTURE_STEPS);
    for (const before of withDeps) {
      expect(byId(after, before.instance_id as string).depends_on).toEqual(before.depends_on);
    }
  });

  it("a route keeps default_next and loop_max_iterations", () => {
    const before = byId(FIXTURE_STEPS, "coverage-check");
    const after = byId(roundTrip(FIXTURE_STEPS), "coverage-check");

    expect(after.route).toEqual(before.route);
  });

  it("a parent keeps spawn_subagents rather than being forced off", () => {
    const before = byId(FIXTURE_STEPS, "synthesizer");
    const after = byId(roundTrip(FIXTURE_STEPS), "synthesizer");

    expect(before.tools?.spawn_subagents).toBe(true);
    expect(after.tools?.spawn_subagents).toBe(true);
  });

  it("a mechanical step preserves its kind and loses no fields on round-trip", () => {
    // Mechanical steps have no prompt, tools, or strategy — just agent/instance_id/mechanical/gates.
    const mechanicalStep: ManifestStep = {
      agent: "custom-agent",
      instance_id: "pb-assemble",
      mechanical: "assemble_prototype",
      name: "Assemble Prototype",
      gates: [],
      depends_on: ["custom-agent:pb-design"],
    };
    const after = agentsToManifestSteps(
      manifestStepsToAgents([mechanicalStep]),
      manifestStepsToGateSelections([mechanicalStep]),
    );
    const afterStep = after[0];
    expect(afterStep.mechanical).toBe("assemble_prototype");
    expect(afterStep.tools).toBeUndefined();
    expect(afterStep.prompt).toBeUndefined();
    expect(afterStep.gates).toEqual([]);
  });

  it("a changed parser on a leaf wave step is emitted on save", () => {
    // Start with json_tasks, change to screen_plan.
    const waveStep: AuthoredStep = {
      agent: "custom-agent",
      instance_id: "screen-builder",
      name: "Screen Builder",
      strategy: "wave_scheduler",
      task_source: {
        kind: "parsed",
        parser: "json_tasks",
        source_step: "custom-agent:pb-design",
      },
      fanout: { agent: "self", mode: "parallel", max_parallel: 6 },
      depends_on: [],
      gates: [],
    };
    const agents = manifestStepsToAgents([waveStep]);
    // Simulate changing the parser in the UI.
    const selections = {
      "screen-builder": {
        strategy: "wave_scheduler" as const,
        task_source: {
          kind: "parsed" as const,
          parser: "screen_plan",
          target: "build/screens.json",
          source_step: "pb-design",
        },
      },
    };
    const after = agentsToManifestSteps(agents, selections);
    const afterStep = after[0] as AuthoredStep;
    expect(afterStep.strategy).toBe("wave_scheduler");
    expect(afterStep.task_source?.parser).toBe("screen_plan");
    expect(afterStep.task_source?.target).toBe("build/screens.json");
  });
});

it("a leaf wave step's saved custom-agent: source_step hydrates as the bare node id and saves back prefixed", () => {
  const steps: ManifestStep[] = [
    { agent: "custom-agent", instance_id: "pb-design", name: "Architect", prompt: "x", tools: { read_files: true, write_files: true, exec: false }, gates: [] },
    {
      agent: "custom-agent", instance_id: "pb-build", name: "Builders", prompt: "y",
      tools: { read_files: true, write_files: true, exec: false }, gates: [],
      strategy: "wave_scheduler",
      task_source: { kind: "parsed", parser: "screen_plan", target: "build/screens.json", source_step: "custom-agent:pb-design" },
      fanout: { agent: "self", mode: "parallel", max_parallel: 6 },
    },
  ];
  const selections = manifestStepsToGateSelections(steps);
  expect(selections["pb-build"]?.task_source?.source_step).toBe("pb-design");
  expect(selections["pb-build"]?.task_source?.parser).toBe("screen_plan");
  const agents = manifestStepsToAgents(steps);
  const saved = agentsToManifestSteps(agents, selections as never);
  const build = saved.find((s) => s.instance_id === "pb-build") as ManifestStep & { task_source?: { source_step?: string } };
  expect(build.task_source?.source_step).toBe("custom-agent:pb-design");
});

it("a wave step's custom path survives load → save, and a switch back to a parser drops the path", () => {
  const steps: ManifestStep[] = [
    { agent: "custom-agent", instance_id: "plan", name: "Planner", prompt: "x", tools: { read_files: true, write_files: true, exec: false }, gates: [] },
    {
      agent: "custom-agent", instance_id: "write", name: "Writers", prompt: "y",
      tools: { read_files: true, write_files: true, exec: false }, gates: [],
      strategy: "wave_scheduler",
      task_source: { kind: "custom_path", parser: "json_tasks", path: "revisions/{revision_n}/tasks.json", source_step: "custom-agent:plan" },
      fanout: { agent: "self", mode: "parallel", max_parallel: 6 },
    },
  ];
  type Saved = ManifestStep & { task_source?: Record<string, unknown> };
  const selections = manifestStepsToGateSelections(steps);
  expect(selections["write"]?.task_source).toMatchObject({ kind: "custom_path", path: "revisions/{revision_n}/tasks.json" });
  const agents = manifestStepsToAgents(steps);
  const saved = agentsToManifestSteps(agents, selections as never).find((s) => s.instance_id === "write") as Saved;
  expect(saved.task_source).toEqual({
    kind: "custom_path", parser: "json_tasks", path: "revisions/{revision_n}/tasks.json", source_step: "custom-agent:plan",
  });

  const toParser = { write: { ...selections["write"], task_source: { kind: "parsed", parser: "json_tasks", source_step: "plan" } } };
  const reverted = agentsToManifestSteps(agents, toParser as never).find((s) => s.instance_id === "write") as Saved;
  expect(reverted.task_source?.kind).toBe("parsed");
  expect(reverted.task_source).not.toHaveProperty("path");
});

it("a step with injects survives manifest → AgentDef → manifest unchanged and is not in extra", () => {
  const step: ManifestStep = {
    agent: "custom-agent",
    instance_id: "writer",
    name: "Writer",
    prompt: "Write content",
    tools: { read_files: true, write_files: true, exec: false },
    gates: [],
    injects: ["design_system", "template"],
  };
  const agents = manifestStepsToAgents([step]);
  expect(agents[0].injects).toEqual(["design_system", "template"]);
  expect(agents[0].extra).toBeUndefined();
  const saved = agentsToManifestSteps(agents);
  const savedStep = saved[0] as AuthoredStep;
  expect(savedStep.injects).toEqual(["design_system", "template"]);
  expect((savedStep as { extra?: unknown }).extra).toBeUndefined();
});
