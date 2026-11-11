import { describe, it, expect, expectTypeOf } from "vitest";
import { isKnownWorkflowType } from "./index";
import type { KnownWorkflowType, WorkflowType } from "./index";

describe("WorkflowType", () => {
  it("accepts a manifest id the catalog returns at runtime without a cast", () => {
    // `ex_A1_loop` and `sample_fanout` are manifests with no entry in the known list.
    const fromCatalog: string = "ex_A1_loop";
    const ids: WorkflowType[] = [fromCatalog, "sample_fanout", "prototype_v2"];
    expect(ids).toHaveLength(3);
  });

  it("keeps every known identifier assignable to WorkflowType", () => {
    expectTypeOf<KnownWorkflowType>().toExtend<WorkflowType>();
  });

  it("does not collapse into a plain string for known-only consumers", () => {
    expectTypeOf<string>().not.toExtend<KnownWorkflowType>();
  });
});

describe("isKnownWorkflowType", () => {
  it("returns true for an identifier the frontend has dedicated handling for", () => {
    expect(isKnownWorkflowType("prototype_v2_feature_revision")).toBe(true);
  });

  it("returns false for a manifest-discovered identifier", () => {
    expect(isKnownWorkflowType("ex_A1_loop")).toBe(false);
  });

  it("narrows to KnownWorkflowType so a Record lookup type-checks", () => {
    const labels: Record<KnownWorkflowType, string> = {
      user_stories: "", user_stories_revision: "", ppt: "", ppt_v2: "", ppt_revision: "",
      prototype: "", prototype_v2: "", prototype_revision: "", prototype_large_revision: "",
      prototype_feature_revision: "", prototype_v2_revision: "", prototype_v2_feature_revision: "", goal_v2: "", prototype_from_template: "", prototype_from_template_revision: "",
      app_builder: "", app_builder_revision: "", custom: "", custom_revision: "",
      backlog: "", backlog_revision: "", migration: "", mulesoft_to_springboot: "", dotnet_to_azure: "",
    };
    const id: WorkflowType = "ppt";
    expect(isKnownWorkflowType(id) ? labels[id] : undefined).toBe("");
    // Every key of the exhaustive map is recognised by the runtime guard.
    for (const key of Object.keys(labels)) expect(isKnownWorkflowType(key)).toBe(true);
  });
});
