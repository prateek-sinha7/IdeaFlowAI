import { describe, expect, it } from "vitest";
import type { WorkflowSummary } from "@/store/api/workflows";
import type { RootState } from "@/store";
import globalReducer, {
  FALLBACK_WORKFLOW_LABELS,
  fetchWorkflows,
  selectChainIntoIndex,
  selectWorkflowLabel,
  selectWorkflowLabelIndex,
  selectWorkflowShortNameIndex,
  selectWorkflowWizardPath,
} from "./globalSlice";

function makeWorkflow(overrides: Partial<WorkflowSummary> & { id: string }): WorkflowSummary {
  return {
    name: overrides.id,
    description: "",
    step_count: 0,
    steps: [],
    user_launchable: true,
    ...overrides,
  } as WorkflowSummary;
}

/** Builds a RootState slice by running the real reducer with a fulfilled catalog fetch. */
function makeState(workflows: WorkflowSummary[]): RootState {
  const global = globalReducer(undefined, fetchWorkflows.fulfilled(workflows, "request-id", undefined));
  return { global } as unknown as RootState;
}

describe("selectWorkflowLabelIndex", () => {
  it("indexes display names by workflow id", () => {
    const index = selectWorkflowLabelIndex(
      makeState([
        makeWorkflow({ id: "prototype", display_name: "Build a prototype" }),
        makeWorkflow({ id: "ppt", display_name: "Pitch an idea" }),
      ]),
    );

    expect(index).toEqual({ prototype: "Build a prototype", ppt: "Pitch an idea" });
  });

  it("omits workflows whose display name is missing, null or empty", () => {
    const index = selectWorkflowLabelIndex(
      makeState([
        makeWorkflow({ id: "a" }),
        makeWorkflow({ id: "b", display_name: null }),
        makeWorkflow({ id: "c", display_name: "" }),
        makeWorkflow({ id: "d", display_name: "Kept" }),
      ]),
    );

    expect(index).toEqual({ d: "Kept" });
  });

  it("returns an empty index when the catalog is empty", () => {
    expect(selectWorkflowLabelIndex(makeState([]))).toEqual({});
  });

  it("returns the same memoized object for an unchanged catalog", () => {
    const state = makeState([makeWorkflow({ id: "a", display_name: "A" })]);

    expect(selectWorkflowLabelIndex(state)).toBe(selectWorkflowLabelIndex(state));
  });
});

describe("selectWorkflowLabel", () => {
  it("prefers the live catalog display name over the static fallback", () => {
    const state = makeState([makeWorkflow({ id: "ppt", display_name: "Pitch an idea" })]);

    expect(selectWorkflowLabel("ppt")(state)).toBe("Pitch an idea");
  });

  it("falls back to the static label when the type is absent from the catalog", () => {
    const state = makeState([]);

    expect(selectWorkflowLabel("ppt_revision")(state)).toBe("Presentation (Revised)");
  });

  it("falls back to the static label when the catalog entry has no display name", () => {
    const state = makeState([makeWorkflow({ id: "dotnet_to_azure" })]);

    expect(selectWorkflowLabel("dotnet_to_azure")(state)).toBe(".NET Migration");
  });

  it("returns the raw type string when neither the catalog nor the fallback knows it", () => {
    const state = makeState([]);

    expect(selectWorkflowLabel("od_ppt")(state)).toBe("od_ppt");
  });

  it("exposes the full static fallback map", () => {
    expect(FALLBACK_WORKFLOW_LABELS).toEqual({
      user_stories: "User Stories",
      user_stories_revision: "User Stories (Revised)",
      ppt: "Presentation",
      ppt_revision: "Presentation (Revised)",
      prototype: "Prototype",
      prototype_revision: "Prototype (Revised)",
      app_builder: "App Builder",
      app_builder_revision: "App Builder (Revised)",
      mulesoft_to_springboot: "Mulesoft Migration",
      dotnet_to_azure: ".NET Migration",
      reverse_engineer: "Reverse Engineer",
      custom: "Custom Workflow",
    });
  });
});

describe("selectWorkflowShortNameIndex", () => {
  it("indexes the short name by workflow id when one is provided", () => {
    const index = selectWorkflowShortNameIndex(
      makeState([makeWorkflow({ id: "prototype", name: "Prototype", short_name: "Proto" })]),
    );

    expect(index).toEqual({ prototype: "Proto" });
  });

  it("falls back to the plain name when short_name is null or absent", () => {
    const index = selectWorkflowShortNameIndex(
      makeState([
        makeWorkflow({ id: "a", name: "Alpha", short_name: null }),
        makeWorkflow({ id: "b", name: "Beta" }),
      ]),
    );

    expect(index).toEqual({ a: "Alpha", b: "Beta" });
  });

  it("omits workflows that have neither a short name nor a name", () => {
    const index = selectWorkflowShortNameIndex(
      makeState([
        makeWorkflow({ id: "a", name: "", short_name: null }),
        makeWorkflow({ id: "b", name: "Beta" }),
      ]),
    );

    expect(index).toEqual({ b: "Beta" });
  });

  it("returns an empty index when the catalog is empty", () => {
    expect(selectWorkflowShortNameIndex(makeState([]))).toEqual({});
  });
});

describe("selectChainIntoIndex", () => {
  it("returns an empty index when the catalog is empty", () => {
    expect(selectChainIntoIndex(makeState([]))).toEqual({});
  });

  it("treats a workflow without chained_from as having no incoming edges", () => {
    const index = selectChainIntoIndex(makeState([makeWorkflow({ id: "chat" })]));

    expect(index).toEqual({});
  });

  it("copies the target's icon, display name and short name onto the derived entry", () => {
    const index = selectChainIntoIndex(
      makeState([
        makeWorkflow({
          id: "app_builder",
          name: "App Builder",
          display_name: "Build the app",
          short_name: "Builder",
          icon: "hammer",
          chained_from: [{ id: "prototype", beta: false, text: "Ship the code" }],
        }),
      ]),
    );

    expect(index.prototype).toEqual([
      {
        id: "app_builder",
        label: "App Builder",
        beta: false,
        text: "Ship the code",
        display_name: "Build the app",
        short_name: "Builder",
        icon: "hammer",
      },
    ]);
  });

  it("omits the icon key when the target has no icon", () => {
    const index = selectChainIntoIndex(
      makeState([
        makeWorkflow({
          id: "app_builder",
          icon: null,
          chained_from: [{ id: "prototype", beta: false, text: "Ship" }],
        }),
      ]),
    );

    expect(index.prototype[0]).not.toHaveProperty("icon");
  });

  it.each([
    ["ppt", "/workflow/create?mode=ppt"],
    ["ppt_v2", "/workflow/create?mode=ppt_v2"],
    ["prototype", "/workflow/create?mode=prototype"],
    ["prototype_v2", "/workflow/create?mode=prototype_v2"],
  ])("adds the wizard path for target %s", (targetId, expectedPath) => {
    const index = selectChainIntoIndex(
      makeState([
        makeWorkflow({
          id: targetId,
          chained_from: [{ id: "user_stories", beta: false, text: "Go" }],
        }),
      ]),
    );

    expect(index.user_stories[0].wizard_path).toBe(expectedPath);
  });

  it("omits the wizard path for a target that fires directly", () => {
    const index = selectChainIntoIndex(
      makeState([
        makeWorkflow({
          id: "app_builder",
          chained_from: [{ id: "user_stories", beta: false, text: "Go" }],
        }),
      ]),
    );

    expect(index.user_stories[0]).not.toHaveProperty("wizard_path");
  });

  it("labels the entry with the target name, then display name, then id", () => {
    const index = selectChainIntoIndex(
      makeState([
        makeWorkflow({
          id: "t1",
          name: "Named",
          display_name: "Display 1",
          chained_from: [{ id: "src", beta: false, text: "x" }],
        }),
        {
          ...makeWorkflow({
            id: "t2",
            display_name: "Display 2",
            chained_from: [{ id: "src", beta: false, text: "x" }],
          }),
          name: undefined,
        } as unknown as WorkflowSummary,
        {
          ...makeWorkflow({
            id: "t3",
            chained_from: [{ id: "src", beta: false, text: "x" }],
          }),
          name: undefined,
        } as unknown as WorkflowSummary,
      ]),
    );

    expect(index.src.map((target) => target.label)).toEqual(["Named", "Display 2", "t3"]);
  });

  it("passes unknown backend fields from the edge through to the entry", () => {
    const index = selectChainIntoIndex(
      makeState([
        makeWorkflow({
          id: "app_builder",
          name: "App Builder",
          chained_from: [{ id: "prototype", beta: true, text: "Ship", tooltip: "Beta feature" }],
        }),
      ]),
    );

    expect(index.prototype).toEqual([
      { id: "app_builder", label: "App Builder", beta: true, text: "Ship", tooltip: "Beta feature" },
    ]);
  });

  it("groups several targets under the same source in catalog order", () => {
    const index = selectChainIntoIndex(
      makeState([
        makeWorkflow({ id: "first", chained_from: [{ id: "src", beta: false, text: "one" }] }),
        makeWorkflow({ id: "second", chained_from: [{ id: "src", beta: false, text: "two" }] }),
      ]),
    );

    expect(index.src.map((target) => [target.id, target.text])).toEqual([
      ["first", "one"],
      ["second", "two"],
    ]);
  });

  it("returns the same memoized object for an unchanged catalog", () => {
    const state = makeState([
      makeWorkflow({ id: "t", chained_from: [{ id: "src", beta: false, text: "x" }] }),
    ]);

    expect(selectChainIntoIndex(state)).toBe(selectChainIntoIndex(state));
  });
});

describe("selectWorkflowWizardPath", () => {
  it.each([
    ["ppt", "/workflow/create?mode=ppt"],
    ["ppt_v2", "/workflow/create?mode=ppt_v2"],
    ["prototype", "/workflow/create?mode=prototype"],
  ])("returns the wizard route for %s", (id, expectedPath) => {
    expect(selectWorkflowWizardPath(id)).toBe(expectedPath);
  });

  it("returns undefined for a workflow that fires directly", () => {
    expect(selectWorkflowWizardPath("app_builder")).toBeUndefined();
  });
});
