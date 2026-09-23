import { describe, it, expect } from "vitest";
import { agentsFromManifest } from "./manifestAgents";

describe("agentsFromManifest keeps fan-out children", () => {
  it("maps subagents.steps to agent.children", () => {
    const detail = {
      id: "sample_subagents_parallel",
      name: "Parallel Sub-agents",
      description: "",
      planner: "skip",
      clarify_mode: "skip",
      clarify_defaults: [],
      context_providers: [],
      deliverable: { strategy: "single_file", name: "page.html" },
      steps: [
        { agent_id: "custom-agent:page", name: "Page Builder", role: "r", order: 1, strategy: "parallel_group", gates: [], validators: [], skills: [] },
        { agent_id: "custom-agent:apple", name: "Apple Writer", role: "r", order: 2, strategy: "single_shot", gates: [], validators: [], skills: [] },
      ],
      manifest_steps: [
        {
          agent: "custom-agent", instance_id: "page", name: "Page Builder", prompt: "p", gates: [],
          tools: { read_files: true, write_files: true, exec: false, spawn_subagents: true },
          subagents: {
            mode: "parallel", max_parallel: 3,
            steps: [
              { agent: "custom-agent", instance_id: "apple", name: "Apple Writer", prompt: "a", gates: [], strategy: "single_shot", skills: ["joke"] },
              { agent: "custom-agent", instance_id: "ball",  name: "Ball Writer",  prompt: "b", gates: ["human"], strategy: "single_shot" },
              { agent: "custom-agent", instance_id: "cat",   name: "Cat Writer",   prompt: "c", gates: [], strategy: "single_shot" },
            ],
          },
        },
      ],
      is_overridden: false, has_override: false, override_id: null, showing_original: false,
    } as never;

    const proj = agentsFromManifest(detail, "sample_subagents_parallel");
    expect(proj.agents).toHaveLength(1);
    const parent = proj.agents[0];
    expect(parent.id).toBe("custom-agent:page");
    expect(parent.strategy).toBe("parallel");
    expect(parent.maxParallel).toBe(3);
    expect(parent.children?.map((c) => c.name)).toEqual(["Apple Writer", "Ball Writer", "Cat Writer"]);
    // a nested child's declared gate must reach selections
    expect(proj.selections?.["custom-agent:ball"]).toEqual({ gates: ["human"] });
  });
});
