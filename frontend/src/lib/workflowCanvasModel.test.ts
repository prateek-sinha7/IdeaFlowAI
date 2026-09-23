import { describe, it, expect } from "vitest";
import { workflowCanvasModel } from "./workflowCanvasModel";
import type { ManifestStep } from "@/types";

const SAMPLE: ManifestStep[] = [
  {
    agent: "custom-agent", instance_id: "page", name: "Page Builder", prompt: "p", gates: [],
    tools: { read_files: true, write_files: true, exec: false, spawn_subagents: true },
    subagents: {
      mode: "parallel", max_parallel: 3,
      steps: [
        { agent: "custom-agent", instance_id: "apple", name: "Apple Writer", prompt: "a", gates: [], strategy: "single_shot", skills: ["joke"] },
        { agent: "custom-agent", instance_id: "ball", name: "Ball Writer", prompt: "b", gates: ["human"], strategy: "single_shot" },
        { agent: "custom-agent", instance_id: "cat", name: "Cat Writer", prompt: "c", gates: [], strategy: "single_shot" },
      ],
    },
  } as ManifestStep,
];

describe("workflowCanvasModel", () => {
  it("nests a fan-out parent's sub-agents as children", () => {
    const { agents } = workflowCanvasModel(SAMPLE);
    expect(agents).toHaveLength(1);
    expect(agents[0].name).toBe("Page Builder");
    expect(agents[0].strategy).toBe("parallel");
    expect(agents[0].maxParallel).toBe(3);
    expect(agents[0].children?.map((c) => c.name)).toEqual([
      "Apple Writer", "Ball Writer", "Cat Writer",
    ]);
  });

  it("seeds gates declared on a NESTED child into selections", () => {
    const { selections } = workflowCanvasModel(SAMPLE);
    expect(selections["ball"]).toMatchObject({ gates: ["human"] });
  });

  it("preserves other levers the user already set", () => {
    const { selections } = workflowCanvasModel(SAMPLE, [], {
      page: { validators: ["html_static"] },
    });
    expect(selections["page"]).toMatchObject({ validators: ["html_static"] });
  });

  it("is empty and safe with no steps", () => {
    expect(workflowCanvasModel(undefined)).toEqual({ agents: [], selections: {} });
    expect(workflowCanvasModel([])).toEqual({ agents: [], selections: {} });
  });
});
