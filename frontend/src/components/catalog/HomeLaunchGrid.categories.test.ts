import { describe, expect, it } from "vitest";
import { isExampleWorkflow } from "./HomeLaunchGrid";

describe("isExampleWorkflow — dashboard Engine examples bucket", () => {
  it("classifies engine fixtures by id prefix", () => {
    for (const id of ["ex_A1_loop", "ex_A3_b_spanish", "sample_subagents_parallel", "sc001_demo"]) {
      expect(isExampleWorkflow(id)).toBe(true);
    }
  });

  it("leaves product workflows in the main grid", () => {
    for (const id of ["prototype", "prototype_v2", "ppt_v2", "custom", "user_stories", "app_builder"]) {
      expect(isExampleWorkflow(id)).toBe(false);
    }
  });
});
