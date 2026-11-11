/**
 * Task 18.5 — effort survives hydration (R-12).
 *
 * Reopening a saved workflow, or applying a builder draft, reads each step's
 * model policy into the composer's `selections` through
 * `manifestStepsToGateSelections`; saving writes it back through
 * `agentsToManifestSteps` (which calls `agentToManifestStep`, not exported).
 * Before the fix the effort was not copied, so it showed as unset.
 *
 * `manifestStepToAgent` also keeps `model` verbatim in `AgentDef.extra`, which
 * can mask a hydration gap. The second property therefore drops that
 * passthrough, so only the hydrated selections can supply the policy.
 */
import fc from "fast-check";
import { describe, expect, it } from "vitest";

import {
  agentsToManifestSteps,
  manifestStepsToAgents,
  manifestStepsToGateSelections,
} from "./userWorkflows";
import type { AgentDef, ManifestStep } from "@/types/index";

// Feature: ai-workflow-builder, Property 32: Effort survives hydration
// **Validates: Requirements 7.9**

const PROPERTY_OPTIONS = { numRuns: 100 } as const;

type Policy = { model?: string; effort?: string };

const token = fc.stringMatching(/^[a-z][a-z0-9._:-]{0,24}$/);

/** A model policy with a model, an effort, or both (never empty). */
const policyArb: fc.Arbitrary<Policy> = fc
  .record({ model: fc.option(token, { nil: undefined }), effort: fc.option(token, { nil: undefined }) })
  .filter((p) => p.model !== undefined || p.effort !== undefined)
  .map((p) => ({
    ...(p.model !== undefined ? { model: p.model } : {}),
    ...(p.effort !== undefined ? { effort: p.effort } : {}),
  }));

interface Shape {
  id: string;
  custom: boolean;
  policy: Policy;
  children: Shape[];
}

/** Top-level steps; a custom step may be a parent with one level of children. */
const shapesArb: fc.Arbitrary<Shape[]> = fc
  .array(
    fc.record({
      custom: fc.boolean(),
      policy: policyArb,
      childPolicies: fc.array(policyArb, { maxLength: 2 }),
    }),
    { minLength: 1, maxLength: 8 },
  )
  // Ids are index-based so they are unique across the whole tree.
  .map((rows) =>
    rows.map<Shape>((row, i) => ({
      id: `n${i}`,
      custom: row.custom,
      policy: row.policy,
      children: row.custom
        ? row.childPolicies.map((policy, c) => ({
            id: `n${i}-c${c}`,
            custom: true,
            policy,
            children: [],
          }))
        : [],
    })),
  );

function toStep(shape: Shape): ManifestStep {
  const step: ManifestStep = shape.custom
    ? { agent: "custom-agent", instance_id: shape.id, name: shape.id, prompt: "p" }
    : { agent: shape.id };
  step.model = { ...shape.policy };
  if (shape.children.length > 0) {
    step.subagents = {
      mode: "parallel",
      max_parallel: 2,
      steps: shape.children.map(toStep),
    } as ManifestStep["subagents"];
  }
  return step;
}

/** Selection key of a step: instance id for a custom step, agent id otherwise. */
function stepKey(step: ManifestStep): string {
  return step.agent === "custom-agent" ? (step.instance_id ?? "") : (step.agent ?? "");
}

function policiesByKey(steps: ManifestStep[], out = new Map<string, unknown>()) {
  for (const step of steps) {
    out.set(stepKey(step), step.model);
    if (step.subagents?.steps) policiesByKey(step.subagents.steps, out);
  }
  return out;
}

function withoutModelPassthrough(agents: AgentDef[]): AgentDef[] {
  return agents.map((agent) => {
    const { model: _dropped, ...rest } = (agent.extra ?? {}) as Record<string, unknown>;
    void _dropped;
    return {
      ...agent,
      extra: Object.keys(rest).length > 0 ? rest : undefined,
      children: agent.children ? withoutModelPassthrough(agent.children) : agent.children,
    };
  });
}

describe("Property 32: Effort survives hydration", () => {
  it("hydrates both the model and the effort of every step's policy", () => {
    fc.assert(
      fc.property(shapesArb, (shapes) => {
        const steps = shapes.map(toStep);
        const selections = manifestStepsToGateSelections(steps);
        for (const [key, policy] of policiesByKey(steps)) {
          const p = policy as Policy;
          expect(selections[key]?.model).toBe(p.model);
          expect(selections[key]?.effort).toBe(p.effort);
        }
      }),
      PROPERTY_OPTIONS,
    );
  });

  it("keeps model and effort through hydration then save, with no passthrough to lean on", () => {
    fc.assert(
      fc.property(shapesArb, (shapes) => {
        const steps = shapes.map(toStep);
        const selections = manifestStepsToGateSelections(steps);
        const agents = withoutModelPassthrough(manifestStepsToAgents(steps));
        const saved = agentsToManifestSteps(agents, selections);
        const before = policiesByKey(steps);
        const after = policiesByKey(saved);
        for (const [key, policy] of before) {
          expect(after.get(key)).toEqual(policy);
        }
      }),
      PROPERTY_OPTIONS,
    );
  });
});
