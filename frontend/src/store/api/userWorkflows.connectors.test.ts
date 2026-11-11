/**
 * Connected Apps persistence (design 4.5): `tools.connectors` must survive the
 * load -> edit -> save round trip. Selections own the grant; the copy of
 * `agent.tools` captured at load must never resurrect a tool switched off.
 */
import { describe, expect, it } from "vitest";

import type { AgentDef, ManifestStep } from "@/types/index";

import {
  agentsToManifestSteps,
  manifestStepsToAgents,
  manifestStepsToGateSelections,
} from "./userWorkflows";

const JIRA_SEARCH = "jira__search_issues";
const JIRA_COMMENT = "jira__add_comment";
const GITHUB_ISSUE = "github__get_issue";

function customStep(over: Partial<ManifestStep> = {}): ManifestStep {
  return { agent: "custom-agent", instance_id: "writer", name: "Writer", prompt: "Write.", ...over };
}

function loadedAgent(step: ManifestStep): AgentDef {
  return manifestStepsToAgents([step])[0];
}

describe("manifestStepsToGateSelections - connectors", () => {
  it("copies the connector names onto the selection with the default file grants", () => {
    const steps = [customStep({ tools: { connectors: [JIRA_SEARCH, GITHUB_ISSUE] } })];

    expect(manifestStepsToGateSelections(steps).writer).toEqual({
      tools: { read_files: true, write_files: true, connectors: [JIRA_SEARCH, GITHUB_ISSUE] },
    });
  });

  it("keeps a saved file-grant restriction and tool packs next to the connectors", () => {
    const steps = [
      customStep({
        tools: { read_files: true, write_files: false, tool_sets: ["playwright"], connectors: [JIRA_SEARCH] },
      }),
    ];

    expect(manifestStepsToGateSelections(steps).writer.tools).toEqual({
      read_files: true,
      write_files: false,
      tool_sets: ["playwright"],
      connectors: [JIRA_SEARCH],
    });
  });

  it("adds no tools entry when the step has no connectors and default grants", () => {
    const steps = [customStep({ tools: { read_files: true, write_files: true, exec: false } })];

    expect(manifestStepsToGateSelections(steps).writer).toBeUndefined();
  });

  it("adds no tools entry when the connector list is empty", () => {
    const steps = [customStep({ tools: { connectors: [] } })];

    expect(manifestStepsToGateSelections(steps).writer).toBeUndefined();
  });

  it("reads connectors from a nested step", () => {
    const steps = [
      customStep({
        instance_id: "parent",
        subagents: {
          mode: "parallel",
          steps: [customStep({ instance_id: "child", tools: { connectors: [JIRA_COMMENT] } })],
        },
      }),
    ];

    expect(manifestStepsToGateSelections(steps).child.tools?.connectors).toEqual([JIRA_COMMENT]);
  });

  it("copies the list so later edits to the selection cannot change the manifest", () => {
    const connectors = [JIRA_SEARCH];
    const selection = manifestStepsToGateSelections([customStep({ tools: { connectors } })]).writer;

    selection.tools?.connectors?.push(GITHUB_ISSUE);

    expect(connectors).toEqual([JIRA_SEARCH]);
  });
});

describe("agentsToManifestSteps - connectors", () => {
  it("emits the connector names from the selection", () => {
    const [step] = agentsToManifestSteps([loadedAgent(customStep())], {
      writer: { tools: { read_files: true, write_files: true, connectors: [JIRA_SEARCH, GITHUB_ISSUE] } },
    });

    expect(step.tools?.connectors).toEqual([JIRA_SEARCH, GITHUB_ISSUE]);
  });

  it("omits the key when the selection has no connectors", () => {
    const [step] = agentsToManifestSteps([loadedAgent(customStep())], {
      writer: { tools: { read_files: true, write_files: true } },
    });

    expect(step.tools).not.toHaveProperty("connectors");
  });

  it("omits the key when the selection list is empty", () => {
    const [step] = agentsToManifestSteps([loadedAgent(customStep())], {
      writer: { tools: { connectors: [] } },
    });

    expect(step.tools).not.toHaveProperty("connectors");
  });

  it("drops a loaded connector that the selection no longer carries", () => {
    const agent = loadedAgent(customStep({ tools: { connectors: [JIRA_SEARCH, JIRA_COMMENT] } }));

    const [step] = agentsToManifestSteps([agent], {
      writer: { tools: { read_files: true, write_files: true, connectors: [JIRA_SEARCH] } },
    });

    expect(step.tools?.connectors).toEqual([JIRA_SEARCH]);
  });

  it("drops every loaded connector when the author switched them all off", () => {
    const agent = loadedAgent(customStep({ tools: { connectors: [JIRA_SEARCH] } }));

    const [step] = agentsToManifestSteps([agent], { writer: { tools: { read_files: true, write_files: true } } });

    expect(step.tools).not.toHaveProperty("connectors");
  });

  it("keeps the other loaded tool keys and the pack list next to the connectors", () => {
    const agent = loadedAgent(
      customStep({ tools: { spawn_subagents: true, mcp: ["srv"], connectors: [JIRA_SEARCH] } } as Partial<ManifestStep>),
    );

    const [step] = agentsToManifestSteps([agent], {
      writer: { tools: { tool_sets: ["file_extract"], connectors: [GITHUB_ISSUE] } },
    });

    expect(step.tools).toEqual({
      spawn_subagents: true,
      mcp: ["srv"],
      read_files: true,
      write_files: true,
      exec: false,
      tool_sets: ["file_extract"],
      connectors: [GITHUB_ISSUE],
    });
  });

  it("copies the list so later edits to the manifest cannot change the selection", () => {
    const connectors = [JIRA_SEARCH];

    const [step] = agentsToManifestSteps([loadedAgent(customStep())], { writer: { tools: { connectors } } });
    step.tools?.connectors?.push(GITHUB_ISSUE);

    expect(connectors).toEqual([JIRA_SEARCH]);
  });
});

describe("connectors round trip", () => {
  it("saves a loaded step with its connectors unchanged", () => {
    const original = customStep({ tools: { read_files: true, write_files: true, connectors: [JIRA_SEARCH, GITHUB_ISSUE] } });

    const [saved] = agentsToManifestSteps(manifestStepsToAgents([original]), manifestStepsToGateSelections([original]));

    expect(saved.tools).toMatchObject({ connectors: [JIRA_SEARCH, GITHUB_ISSUE] });
  });

  it("saves a connector-free step without a connectors key", () => {
    const original = customStep({ tools: { read_files: true, write_files: true } });

    const [saved] = agentsToManifestSteps(manifestStepsToAgents([original]), manifestStepsToGateSelections([original]));

    expect(saved.tools).not.toHaveProperty("connectors");
  });
});
