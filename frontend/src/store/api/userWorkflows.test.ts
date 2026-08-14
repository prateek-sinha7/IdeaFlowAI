/**
 * Spec 012 (T30) — UI persistence round-trip.
 *
 * `backend/app/api/user_workflows.py::_project` shape-overloads
 * `manifest_json`: either the compact EMP-03 `{agent_id: {...}}` selections
 * map, or a full `{"steps": [...]}` manifest once a node carries a per-node
 * skill, a custom prompt, or a sub-agent tree (sniffed by the presence of the
 * `"steps"` key). These tests pin the FE-side half of that contract: the
 * composer's node tree (`AgentDef[]`, with `children`/`skills`/`prompt`/
 * `strategy`) converts losslessly to and from that manifest shape, so adding
 * a child, renaming it, attaching a skill, and choosing a strategy all
 * survive a save → reload round trip.
 */
import { describe, it, expect } from "vitest";
import {
  agentsToManifestSteps,
  buildWorkflowManifest,
  collectAgentIds,
  generateInstanceId,
  isValidInstanceId,
  manifestStepsToAgents,
} from "./userWorkflows";
import type { AgentDef } from "@/types/index";

function mkAgent(over: Partial<AgentDef> & { id: string; name: string }): AgentDef {
  return {
    role: "Does a thing",
    description: "",
    pipeline_type: "custom",
    order: 1,
    icon: "",
    estimated_duration: 60,
    has_skill: false,
    ...over,
  };
}

describe("generateInstanceId / isValidInstanceId (R-03)", () => {
  it("generates an id matching ^[a-z0-9][a-z0-9-]*$", () => {
    const id = generateInstanceId([]);
    expect(isValidInstanceId(id)).toBe(true);
  });

  it("never collides with an existing id", () => {
    const first = generateInstanceId([]);
    const second = generateInstanceId([first]);
    expect(second).not.toBe(first);
    expect(isValidInstanceId(second)).toBe(true);
  });

  it("collectAgentIds walks nested children too", () => {
    const tree: AgentDef[] = [
      mkAgent({
        id: "root",
        name: "Root",
        children: [mkAgent({ id: "child-1", name: "Child" })],
      }),
    ];
    expect(collectAgentIds(tree)).toEqual(["root", "child-1"]);
  });
});

describe("agentsToManifestSteps / manifestStepsToAgents — lossless round trip (R-01..R-05)", () => {
  it("a built-in step round-trips as agent_id with no instance_id", () => {
    const steps = agentsToManifestSteps([mkAgent({ id: "researcher", name: "Researcher" })]);
    expect(steps).toEqual([
      {
        agent_id: "researcher",
        depends_on: [],
        gates: [],
        strategy: "single_shot",
        tools: { read_files: true, write_files: true, exec: false },
      },
    ]);
  });

  it("a custom-agent step compiles to agent: 'custom-agent' + a stable instance_id (R-03a)", () => {
    const agent = mkAgent({
      id: "agent-1",
      name: "My Agent",
      isCustom: true,
      instance_id: "agent-1",
      prompt: "Write a report.",
    });
    const [step] = agentsToManifestSteps([agent]);
    expect(step).toMatchObject({
      agent: "custom-agent",
      instance_id: "agent-1",
      name: "My Agent",
      prompt: "Write a report.",
    });
  });

  it("renaming a node changes only `name` in the manifest — instance_id is stable (R-03)", () => {
    const before = mkAgent({ id: "agent-1", name: "Old Name", isCustom: true, instance_id: "agent-1" });
    const after = { ...before, name: "New Name" };
    const [stepBefore] = agentsToManifestSteps([before]);
    const [stepAfter] = agentsToManifestSteps([after]);
    expect(stepBefore.instance_id).toBe(stepAfter.instance_id);
    expect(stepAfter.name).toBe("New Name");
  });

  it("skills persist as a plain id list", () => {
    const [step] = agentsToManifestSteps([
      mkAgent({ id: "researcher", name: "Researcher", skills: ["market-research", "seo-audit"] }),
    ]);
    expect(step.skills).toEqual(["market-research", "seo-audit"]);
  });

  it("a node with children compiles subagents.mode/max_parallel/steps (R-04)", () => {
    const parent = mkAgent({
      id: "parent-1",
      name: "Parent",
      isCustom: true,
      instance_id: "parent-1",
      strategy: "parallel",
      maxParallel: 5,
      children: [
        mkAgent({ id: "child-1", name: "Child A", isCustom: true, instance_id: "child-1" }),
        mkAgent({ id: "child-2", name: "Child B", isCustom: true, instance_id: "child-2" }),
      ],
    });
    const [step] = agentsToManifestSteps([parent]);
    expect(step.subagents).toMatchObject({
      mode: "parallel",
      max_parallel: 5,
    });
    expect(step.subagents?.steps).toHaveLength(2);
    expect(step.subagents?.steps[0].instance_id).toBe("child-1");
  });

  it("buildWorkflowManifest carries top-level capabilities (R-07)", () => {
    const manifest = buildWorkflowManifest(
      [mkAgent({ id: "researcher", name: "Researcher" })],
      { internet: true },
    );
    expect(manifest).toEqual({
      steps: [
        {
          agent_id: "researcher",
          depends_on: [],
          gates: [],
          strategy: "single_shot",
          tools: { read_files: true, write_files: true, exec: false },
        },
      ],
      capabilities: { internet: true },
    });
  });

  it("omits capabilities entirely when none are set", () => {
    const manifest = buildWorkflowManifest([mkAgent({ id: "researcher", name: "Researcher" })]);
    expect(manifest.capabilities).toBeUndefined();
  });

  it("a full tree (parent + children + grandchild) round-trips through manifestStepsToAgents", () => {
    const tree: AgentDef[] = [
      mkAgent({
        id: "parent-1",
        name: "Parent",
        isCustom: true,
        instance_id: "parent-1",
        strategy: "sequential",
        skills: ["market-research"],
        children: [
          mkAgent({
            id: "child-1",
            name: "Child",
            isCustom: true,
            instance_id: "child-1",
            prompt: "Do research.",
            children: [
              mkAgent({
                id: "grandchild-1",
                name: "Grandchild",
                isCustom: true,
                instance_id: "grandchild-1",
              }),
            ],
          }),
        ],
      }),
    ];
    const steps = agentsToManifestSteps(tree);
    const restored = manifestStepsToAgents(steps);

    expect(restored[0].name).toBe("Parent");
    expect(restored[0].instance_id).toBe("parent-1");
    expect(restored[0].skills).toEqual(["market-research"]);
    expect(restored[0].strategy).toBe("sequential");

    const child = restored[0].children![0];
    expect(child.name).toBe("Child");
    expect(child.instance_id).toBe("child-1");
    expect(child.prompt).toBe("Do research.");

    const grandchild = child.children![0];
    expect(grandchild.name).toBe("Grandchild");
    expect(grandchild.instance_id).toBe("grandchild-1");
  });

  it("a built-in step resolves its full AgentDef via the lookup callback on reload", () => {
    const library: AgentDef = mkAgent({ id: "researcher", name: "Researcher", role: "Digs up facts" });
    const steps = agentsToManifestSteps([
      mkAgent({ id: "researcher", name: "Researcher", skills: ["market-research"] }),
    ]);
    const restored = manifestStepsToAgents(steps, (id) => (id === "researcher" ? library : undefined));
    expect(restored[0].role).toBe("Digs up facts");
    expect(restored[0].skills).toEqual(["market-research"]);
  });
});
