import { describe, it, expect } from "vitest";
import {
  parseFailedAgentIds,
  buildAgentNameById,
  resolveAgentNames,
} from "./parseFailedAgents";

describe("parseFailedAgentIds", () => {
  it("should parse a single failed agent from error message", () => {
    const error = "Something went wrong: agent(s) failed: build-agent";
    const ids = parseFailedAgentIds(error);
    expect(ids).toEqual(["build-agent"]);
  });

  it("should parse multiple failed agents separated by commas", () => {
    const error = "Error: agent(s) failed: prototype-build, app-sdlc-governance, content-reviewer";
    const ids = parseFailedAgentIds(error);
    expect(ids).toEqual(["prototype-build", "app-sdlc-governance", "content-reviewer"]);
  });

  it("should handle agents with extra whitespace", () => {
    const error = "agent(s) failed:   agent-1  ,  agent-2  ,  agent-3  ";
    const ids = parseFailedAgentIds(error);
    expect(ids).toEqual(["agent-1", "agent-2", "agent-3"]);
  });

  it("should return undefined when marker is not present", () => {
    const error = "Some other error message";
    const ids = parseFailedAgentIds(error);
    expect(ids).toBeUndefined();
  });

  it("should return undefined when error is undefined", () => {
    const ids = parseFailedAgentIds(undefined);
    expect(ids).toBeUndefined();
  });

  it("should return undefined when error is empty string", () => {
    const ids = parseFailedAgentIds("");
    expect(ids).toBeUndefined();
  });

  it("should handle case-insensitive marker", () => {
    const error = "Agent(s) Failed: my-agent";
    const ids = parseFailedAgentIds(error);
    expect(ids).toEqual(["my-agent"]);
  });

  it("should return undefined when marker exists but has no agents after colon", () => {
    const error = "agent(s) failed: ";
    const ids = parseFailedAgentIds(error);
    expect(ids).toBeUndefined();
  });

  it("should handle agent IDs with special characters (hyphens, underscores)", () => {
    const error = "agent(s) failed: build_agent-v2, test-runner_3, deploy-prod_backup";
    const ids = parseFailedAgentIds(error);
    expect(ids).toEqual(["build_agent-v2", "test-runner_3", "deploy-prod_backup"]);
  });

  it("should ignore empty strings from split when filtering", () => {
    const error = "agent(s) failed: agent1, , agent2, ";
    const ids = parseFailedAgentIds(error);
    expect(ids).toEqual(["agent1", "agent2"]);
  });

  it("should work with marker at the end of the error string", () => {
    const error = "Failed at step 5: agent(s) failed: failed-agent";
    const ids = parseFailedAgentIds(error);
    expect(ids).toEqual(["failed-agent"]);
  });
});

describe("buildAgentNameById", () => {
  it("should build a map from agents with id and name", () => {
    const agents = [
      { id: "build", name: "Build Agent" },
      { id: "test", name: "Test Runner" },
    ];
    const map = buildAgentNameById(agents);
    expect(map).toEqual({
      build: "Build Agent",
      test: "Test Runner",
    });
  });

  it("should return empty object when agents is undefined", () => {
    const map = buildAgentNameById(undefined);
    expect(map).toEqual({});
  });

  it("should return empty object when agents array is empty", () => {
    const map = buildAgentNameById([]);
    expect(map).toEqual({});
  });

  it("should skip agents without a name", () => {
    const agents = [
      { id: "build", name: "Build Agent" },
      { id: "test" },
      { id: "deploy", name: "Deploy Service" },
    ];
    const map = buildAgentNameById(agents);
    expect(map).toEqual({
      build: "Build Agent",
      deploy: "Deploy Service",
    });
  });

  it("should skip agents with null name", () => {
    const agents = [
      { id: "build", name: "Build Agent" },
      { id: "test", name: null },
      { id: "deploy", name: "Deploy" },
    ];
    const map = buildAgentNameById(agents);
    expect(map).toEqual({
      build: "Build Agent",
      deploy: "Deploy",
    });
  });

  it("should skip agents with missing id", () => {
    const agents = [
      { id: "build", name: "Build Agent" },
      { id: "deploy", name: "Deploy" },
    ];
    const map = buildAgentNameById(agents);
    expect(map).toEqual({
      build: "Build Agent",
      deploy: "Deploy",
    });
  });

  it("should handle last agent in the list", () => {
    const agents = [
      { id: "agent1", name: "First" },
      { id: "agent2", name: "Second" },
    ];
    const map = buildAgentNameById(agents);
    expect(map.agent2).toBe("Second");
  });

  it("should skip null/falsy agents in array", () => {
    const agents = [
      { id: "build", name: "Build" },
      { id: "test", name: "Test" },
    ];
    const map = buildAgentNameById(agents);
    expect(map).toEqual({
      build: "Build",
      test: "Test",
    });
  });
});

describe("resolveAgentNames", () => {
  it("should resolve agent IDs to names using lookup map", () => {
    const ids = ["build", "test"];
    const nameById = { build: "Build Agent", test: "Test Runner" };
    const names = resolveAgentNames(ids, nameById);
    expect(names).toEqual(["Build Agent", "Test Runner"]);
  });

  it("should fall back to ID when name is not in map", () => {
    const ids = ["build", "unknown", "test"];
    const nameById = { build: "Build Agent", test: "Test Runner" };
    const names = resolveAgentNames(ids, nameById);
    expect(names).toEqual(["Build Agent", "unknown", "Test Runner"]);
  });

  it("should return empty array when ids is undefined", () => {
    const nameById = { build: "Build Agent" };
    const names = resolveAgentNames(undefined, nameById);
    expect(names).toEqual([]);
  });

  it("should return empty array when ids is empty", () => {
    const nameById = { build: "Build Agent" };
    const names = resolveAgentNames([], nameById);
    expect(names).toEqual([]);
  });

  it("should return raw IDs when nameById is undefined", () => {
    const ids = ["build", "test"];
    const names = resolveAgentNames(ids, undefined);
    expect(names).toEqual(["build", "test"]);
  });

  it("should return raw IDs when nameById is empty", () => {
    const ids = ["build", "test"];
    const names = resolveAgentNames(ids, {});
    expect(names).toEqual(["build", "test"]);
  });

  it("should preserve order of input IDs", () => {
    const ids = ["deploy", "build", "test"];
    const nameById = {
      build: "Build",
      test: "Test",
      deploy: "Deploy",
    };
    const names = resolveAgentNames(ids, nameById);
    expect(names).toEqual(["Deploy", "Build", "Test"]);
  });

  it("should handle mixed known and unknown agents", () => {
    const ids = ["known1", "unknown1", "known2", "unknown2"];
    const nameById = { known1: "Known Agent 1", known2: "Known Agent 2" };
    const names = resolveAgentNames(ids, nameById);
    expect(names).toEqual(["Known Agent 1", "unknown1", "Known Agent 2", "unknown2"]);
  });
});
