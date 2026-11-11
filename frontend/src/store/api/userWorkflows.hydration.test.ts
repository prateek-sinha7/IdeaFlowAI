/**
 * Task 18.4 — effort hydration (R-12, Req 7.9) and `compiledRootIds` (Req 10.9).
 */
import { describe, it, expect } from "vitest";
import { compiledRootIds, manifestStepsToGateSelections } from "./userWorkflows";
import type { ManifestStep } from "@/types";

describe("manifestStepsToGateSelections — model + effort hydration", () => {
  it("copies model and effort from the step's model policy", () => {
    const steps: ManifestStep[] = [
      {
        agent: "custom-agent",
        instance_id: "a",
        model: { model: "global.openai.gpt-5.6-sol", effort: "xhigh" },
      },
    ];
    expect(manifestStepsToGateSelections(steps).a).toEqual({
      model: "global.openai.gpt-5.6-sol",
      effort: "xhigh",
    });
  });

  it("copies effort alone and model alone", () => {
    const steps: ManifestStep[] = [
      { agent: "custom-agent", instance_id: "a", model: { effort: "high" } },
      { agent: "custom-agent", instance_id: "b", model: { model: "m" } },
    ];
    const out = manifestStepsToGateSelections(steps);
    expect(out.a).toEqual({ effort: "high" });
    expect(out.b).toEqual({ model: "m" });
  });

  it("adds no entry for a step without a model policy", () => {
    const steps: ManifestStep[] = [{ agent: "custom-agent", instance_id: "a" }];
    expect(manifestStepsToGateSelections(steps).a).toBeUndefined();
  });

  it("hydrates effort on nested steps", () => {
    const steps: ManifestStep[] = [
      {
        agent: "custom-agent",
        instance_id: "parent",
        subagents: {
          mode: "parallel",
          steps: [{ agent: "custom-agent", instance_id: "child", model: { effort: "on" } }],
        },
      } as ManifestStep,
    ];
    expect(manifestStepsToGateSelections(steps).child).toEqual({ effort: "on" });
  });
});

describe("compiledRootIds (port of export_manifest.compiled_root_ids)", () => {
  it("prefixes custom steps and keeps built-in ids bare", () => {
    expect(
      compiledRootIds({
        steps: [
          { agent: "research" },
          { agent: "custom-agent", instance_id: "writer" },
        ],
      }),
    ).toEqual(["research", "custom-agent:writer"]);
  });

  it("uses the bare agent when a custom step has no instance id", () => {
    expect(compiledRootIds({ steps: [{ agent: "custom-agent" }] })).toEqual(["custom-agent"]);
  });

  it("skips steps with no agent and ignores nested steps", () => {
    expect(
      compiledRootIds({
        steps: [
          { name: "no agent" },
          {
            agent: "a",
            subagents: { mode: "parallel", steps: [{ agent: "child" }] },
          } as ManifestStep,
        ],
      }),
    ).toEqual(["a"]);
  });

  it("returns an empty list for missing or null steps", () => {
    expect(compiledRootIds({})).toEqual([]);
    expect(compiledRootIds({ steps: null })).toEqual([]);
  });
});
