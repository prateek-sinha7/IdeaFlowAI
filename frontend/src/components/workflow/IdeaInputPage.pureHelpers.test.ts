/**
 * Pure, exported helpers of IdeaInputPage.tsx — the brief-intent recommendation
 * engine, the custom-composer deliverable resolver, the FIX-111 `task_loop`
 * gap-filler, and the staged-upload ordering function. ComposerPage imports the
 * same exports (INV-12), so their contracts are pinned here directly with
 * hand-derived literals rather than through a rendered page.
 */
import { describe, expect, it } from "vitest";

import {
  getAgentRecommendations,
  orderedStagedUploadIds,
  resolveDispatchType,
  withPrototypeTaskLoop,
} from "./IdeaInputPage";
import type { AgentDef } from "@/types/index";

function agent(id: string): AgentDef {
  return {
    id,
    name: id,
    role: "",
    description: "",
    pipeline_type: "custom",
    order: 1,
    icon: "",
    estimated_duration: 0,
    has_skill: false,
  };
}

const ids = (list: AgentDef[]) => list.map((a) => a.id);

const STORY_IDS = [
  "domain-analyst",
  "epic-architect",
  "story-estimator",
  "nfr-specialist",
  "backlog-reviewer",
  "backlog-compiler",
];
const PROTOTYPE_IDS = [
  "prototype-specify",
  "prototype-plan",
  "prototype-analyze",
  "prototype-build",
  "prototype-validate",
];
const PPT_IDS = ["ppt-brief-analyst", "ppt-composer", "ppt-validator"];

const LIBRARY: AgentDef[] = [
  ...STORY_IDS,
  ...PROTOTYPE_IDS,
  ...PPT_IDS,
  "market-research-agent",
  "swot-analyst",
  "roadmap-planner",
  "security-auditor",
].map(agent);

describe("getAgentRecommendations", () => {
  it.each([
    ["an empty brief", ""],
    ["a whitespace-padded brief shorter than 10 characters", "   short  "],
  ])("returns no agents when the brief is %s", (_label, brief) => {
    expect(getAgentRecommendations(LIBRARY, brief, new Set())).toEqual([]);
  });

  it("returns no agents when the brief matches no intent", () => {
    expect(getAgentRecommendations(LIBRARY, "Make me a sandwich please now", new Set())).toEqual([]);
  });

  it("recommends the six backlog agents in pipeline order for a user-story brief", () => {
    const result = getAgentRecommendations(LIBRARY, "Write user stories for refunds", new Set());

    expect(ids(result)).toEqual(STORY_IDS);
  });

  it("does not fire the prototype intent when a user-story exclusion word is present", () => {
    const result = getAgentRecommendations(
      LIBRARY,
      "Build an app prototype with user stories",
      new Set(),
    );

    expect(ids(result)).toEqual(STORY_IDS);
  });

  it("orders a priority-2 intent ahead of a priority-3 intent", () => {
    const result = getAgentRecommendations(
      LIBRARY,
      "Create a pitch deck and a security audit",
      new Set(),
    );

    expect(ids(result)).toEqual([...PPT_IDS, "security-auditor"]);
  });

  it("ranks the same-priority intent with more weak-signal hits first", () => {
    // "ppt" fires presentation (weak score 0); "landing page" fires prototype with
    // the weak signal "page" (score 1), so prototype outranks presentation.
    const result = getAgentRecommendations(
      LIBRARY,
      "make a ppt for the landing page",
      new Set(),
    );

    expect(ids(result)).toEqual([...PROTOTYPE_IDS, ...PPT_IDS]);
  });

  it("deduplicates an agent that two intents both recommend", () => {
    const result = getAgentRecommendations(
      LIBRARY,
      "market research and a swot analysis",
      new Set(),
    );

    expect(ids(result)).toEqual(["market-research-agent", "swot-analyst", "roadmap-planner"]);
  });

  it("matches a trailing-space signal such as 'tam ' as a whole word", () => {
    const result = getAgentRecommendations(LIBRARY, "Estimate the TAM for electric scooters", new Set());

    expect(ids(result)).toEqual(["market-research-agent", "swot-analyst"]);
  });

  it("leaves out agents that are already in the pipeline", () => {
    const result = getAgentRecommendations(
      LIBRARY,
      "Write user stories for refunds",
      new Set(["domain-analyst", "backlog-compiler"]),
    );

    expect(ids(result)).toEqual([
      "epic-architect",
      "story-estimator",
      "nfr-specialist",
      "backlog-reviewer",
    ]);
  });

  it("returns no agents when every recommended agent is already in the pipeline", () => {
    expect(
      getAgentRecommendations(LIBRARY, "Write user stories for refunds", new Set(STORY_IDS)),
    ).toEqual([]);
  });

  it("skips recommended ids that are absent from the agent library", () => {
    const partial = LIBRARY.filter((a) => a.id === "epic-architect" || a.id === "backlog-compiler");

    const result = getAgentRecommendations(partial, "Write user stories for refunds", new Set());

    expect(ids(result)).toEqual(["epic-architect", "backlog-compiler"]);
  });
});

describe("resolveDispatchType", () => {
  it("returns the base type unchanged and no override when the base type is not custom", () => {
    const result = resolveDispatchType([agent("prototype-build")], "user_stories");

    expect(result).toEqual({ type: "user_stories" });
  });

  it("returns a single-file prototype.html override when any prototype agent is selected", () => {
    const result = resolveDispatchType([agent("prototype-validate")], "custom");

    expect(result).toEqual({
      type: "custom",
      deliverableOverride: { strategy: "single_file", name: "prototype.html", mimetype: "text/html" },
    });
  });

  it("returns a streamed markdown user_stories.md override when a backlog agent is selected", () => {
    const result = resolveDispatchType([agent("epic-architect")], "custom");

    expect(result).toEqual({
      type: "custom",
      deliverableOverride: {
        strategy: "streamed_text",
        name: "user_stories.md",
        mimetype: "text/markdown",
      },
    });
  });

  it("returns a single-file presentation.html override when a presentation agent is selected", () => {
    const result = resolveDispatchType([agent("ppt-composer")], "custom");

    expect(result).toEqual({
      type: "custom",
      deliverableOverride: {
        strategy: "single_file",
        name: "presentation.html",
        mimetype: "text/html",
      },
    });
  });

  it("lets the first matching deliverable group win when agents from several groups are selected", () => {
    const result = resolveDispatchType([agent("epic-architect"), agent("prototype-build")], "custom");

    expect(result.deliverableOverride?.name).toBe("prototype.html");
  });

  it.each([
    ["an empty roster", [] as AgentDef[]],
    ["agents outside every group", [agent("security-auditor")]],
  ])("returns custom with no override for %s", (_label, agents) => {
    expect(resolveDispatchType(agents, "custom")).toEqual({ type: "custom" });
  });
});

describe("withPrototypeTaskLoop", () => {
  const buildAgents = [agent("prototype-specify"), agent("prototype-build")];

  it("adds the task_loop strategy for prototype-build under the prototype.html deliverable", () => {
    const selections = { "other-step": { retry: 2 } };

    const result = withPrototypeTaskLoop(selections, buildAgents, "prototype.html");

    expect(result).toEqual({
      "other-step": { retry: 2 },
      "prototype-build": { strategy: "task_loop" },
    });
    expect(selections).toEqual({ "other-step": { retry: 2 } });
  });

  it("keeps the other fields of an existing prototype-build entry that has no strategy", () => {
    const result = withPrototypeTaskLoop(
      { "prototype-build": { model: "model-x" } },
      buildAgents,
      "prototype.html",
    );

    expect(result).toEqual({ "prototype-build": { model: "model-x", strategy: "task_loop" } });
  });

  it("returns the selections untouched when the composer already chose a strategy", () => {
    const selections = { "prototype-build": { strategy: "fanout_batch" } };

    expect(withPrototypeTaskLoop(selections, buildAgents, "prototype.html")).toBe(selections);
  });

  it.each([
    ["a different deliverable name", buildAgents, "presentation.html"],
    ["no deliverable name", buildAgents, undefined],
    ["no prototype-build agent", [agent("prototype-specify")], "prototype.html"],
  ])("returns the selections untouched for %s", (_label, agents, deliverableName) => {
    const selections = { x: { retry: 1 } };

    expect(withPrototypeTaskLoop(selections, agents, deliverableName)).toBe(selections);
  });
});

describe("orderedStagedUploadIds", () => {
  it("returns stage ids sorted by attach order, not by arrival order", () => {
    const arrival = [
      { name: "b.pdf", stageId: "stage-b", attachIndex: 2 },
      { name: "a.pdf", stageId: "stage-a", attachIndex: 0 },
      { name: "c.pdf", stageId: "stage-c", attachIndex: 1 },
    ];

    expect(orderedStagedUploadIds(arrival)).toEqual(["stage-a", "stage-c", "stage-b"]);
    expect(arrival.map((s) => s.stageId)).toEqual(["stage-b", "stage-a", "stage-c"]);
  });

  it("returns an empty list when nothing was staged", () => {
    expect(orderedStagedUploadIds([])).toEqual([]);
  });
});
