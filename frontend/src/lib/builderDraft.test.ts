import { describe, expect, it } from "vitest";
import {
  aiCopyName,
  BUILDER_DB_TRUST_RUN_NOTE,
  BUILDER_UPDATING_MESSAGE,
  builderRunBlock,
  computeDraftState,
  draftApplyAction,
  draftSaveDefaults,
  isConflictError,
  isUnsaved,
  manifestAsPassthrough,
  nextAiCopyName,
  rebuildDraftAgents,
} from "./builderDraft";
import type { WorkflowManifest } from "@/types/index";

const manifest: WorkflowManifest = {
  steps: [
    {
      agent: "custom-agent",
      instance_id: "draft-a",
      name: "Draft A",
      prompt: "Write it.",
      gates: ["human"],
      model: { model: "claude-sonnet-5-5", effort: "high" },
    },
    { agent: "custom-agent", instance_id: "draft-b", name: "Draft B", prompt: "Check it." },
  ],
  capabilities: { internet: true } as WorkflowManifest["capabilities"],
  deliverable: { strategy: "single_file", name: "out.html" },
  planner: "run",
};

describe("computeDraftState", () => {
  it("replaces agents, selections, capabilities and run config from the manifest", () => {
    const state = computeDraftState(manifest);

    expect(state.pipelineAgents.map((a) => a.id)).toEqual(["draft-a", "draft-b"]);
    expect(state.selections["draft-a"]).toMatchObject({
      gates: ["human"],
      model: "claude-sonnet-5-5",
      effort: "high",
    });
    expect(state.capabilities).toEqual({ internet: true });
    expect(state.runConfig).toEqual({
      deliverable: { strategy: "single_file", name: "out.html" },
      planner: "run",
    });
  });

  it("returns empty capabilities and run config when the manifest omits them", () => {
    const state = computeDraftState({ steps: [] });

    expect(state.pipelineAgents).toEqual([]);
    expect(state.selections).toEqual({});
    expect(state.capabilities).toEqual({});
    expect(state.runConfig).toEqual({});
  });

  it("resolves built-in steps through the lookup", () => {
    const lookup = (id: string) =>
      id === "ba" ? ({ id: "ba", name: "Business Analyst" } as never) : undefined;
    const agents = rebuildDraftAgents({ steps: [{ agent: "ba" }] }, lookup);

    expect(agents[0]?.name).toBe("Business Analyst");
  });
});

describe("draftApplyAction", () => {
  const base = { libraryLoaded: true, agentsBuiltWithLibrary: true };

  it("does nothing without a draft", () => {
    expect(draftApplyAction({ ...base, lastAppliedRevision: null, draftRevision: null })).toBe("none");
  });

  it("applies a revision that was not applied yet", () => {
    expect(draftApplyAction({ ...base, lastAppliedRevision: null, draftRevision: 1 })).toBe("apply");
    expect(draftApplyAction({ ...base, lastAppliedRevision: 1, draftRevision: 2 })).toBe("apply");
  });

  it("does not apply the same revision twice", () => {
    expect(draftApplyAction({ ...base, lastAppliedRevision: 2, draftRevision: 2 })).toBe("none");
  });

  it("rebuilds agents once when the library loads after the draft was applied", () => {
    const input = { lastAppliedRevision: 2, draftRevision: 2, agentsBuiltWithLibrary: false };

    expect(draftApplyAction({ ...input, libraryLoaded: false })).toBe("none");
    expect(draftApplyAction({ ...input, libraryLoaded: true })).toBe("rebuild_agents");
  });
});

describe("isUnsaved", () => {
  it("is false when the snapshot matches the baseline and no draft is pending", () => {
    expect(isUnsaved({ snapshot: "a", baseline: "a", draftDirty: false })).toBe(false);
  });

  it("is true when the snapshot differs from the baseline", () => {
    expect(isUnsaved({ snapshot: "b", baseline: "a", draftDirty: false })).toBe(true);
  });

  it("is true for an applied draft even when the snapshot equals the baseline", () => {
    expect(isUnsaved({ snapshot: "a", baseline: "a", draftDirty: true })).toBe(true);
  });

  it("treats an uncaptured baseline as no difference", () => {
    expect(isUnsaved({ snapshot: "a", baseline: null, draftDirty: false })).toBe(false);
  });
});

describe("manifestAsPassthrough", () => {
  it("copies every key, including ones the canvas does not model", () => {
    const withExtra = { ...manifest, limits: { max_steps: 3 } } as WorkflowManifest;

    expect(manifestAsPassthrough(withExtra)).toEqual(withExtra);
    expect(manifestAsPassthrough(withExtra)).not.toBe(withExtra);
  });
});

describe("builderRunBlock", () => {
  it("blocks while a turn runs, whatever the trust or dirtiness", () => {
    for (const draftTrust of [null, "user", "db"] as const) {
      for (const dirty of [false, true]) {
        expect(builderRunBlock({ turnRunning: true, draftTrust, dirty })).toBe("turn_running");
      }
    }
  });
  it("blocks a dirty canvas whose latest draft is at db trust", () => {
    expect(builderRunBlock({ turnRunning: false, draftTrust: "db", dirty: true })).toBe(
      "db_trust_unsaved",
    );
  });
  it("does not block a saved db canvas, a user-trust draft, or no draft", () => {
    expect(builderRunBlock({ turnRunning: false, draftTrust: "db", dirty: false })).toBeNull();
    expect(builderRunBlock({ turnRunning: false, draftTrust: "user", dirty: true })).toBeNull();
    expect(builderRunBlock({ turnRunning: false, draftTrust: null, dirty: true })).toBeNull();
  });
  it("exposes the user-facing texts", () => {
    expect(BUILDER_UPDATING_MESSAGE).toBe("The builder is updating this workflow.");
    expect(BUILDER_DB_TRUST_RUN_NOTE).toMatch(/^An unsaved canvas runs at user trust\./);
  });
});

describe("draftSaveDefaults (Req 10.2)", () => {
  it("takes the manifest name and description", () => {
    expect(draftSaveDefaults({ name: "Blog", description: "Writes posts" })).toEqual({
      name: "Blog",
      description: "Writes posts",
    });
  });
  it("falls back to the id when the name is absent or blank", () => {
    expect(draftSaveDefaults({ id: "blog-pipeline", name: "  " }).name).toBe("blog-pipeline");
    expect(draftSaveDefaults({ id: "blog-pipeline" }).name).toBe("blog-pipeline");
  });
  it("returns no name and an empty description when neither is present", () => {
    expect(draftSaveDefaults({ steps: [] })).toEqual({ name: undefined, description: "" });
  });
  it("ignores non-string values", () => {
    expect(draftSaveDefaults({ name: 42, description: null })).toEqual({
      name: undefined,
      description: "",
    });
  });
});

describe("aiCopyName and nextAiCopyName (G-34)", () => {
  it("pre-fills the copy name as '<name> (AI)'", () => {
    expect(aiCopyName("Blog")).toBe("Blog (AI)");
  });
  it("moves from the stem to ' 2', ' 3' and so on", () => {
    expect(nextAiCopyName("Blog (AI)", "Blog (AI)")).toBe("Blog (AI) 2");
    expect(nextAiCopyName("Blog (AI) 2", "Blog (AI)")).toBe("Blog (AI) 3");
    expect(nextAiCopyName("Blog (AI) 9", "Blog (AI)")).toBe("Blog (AI) 10");
  });
  it("leaves a name it did not pre-fill alone", () => {
    expect(nextAiCopyName("Other", "Blog (AI)")).toBeNull();
    expect(nextAiCopyName("Blog (AI) x", "Blog (AI)")).toBeNull();
    expect(nextAiCopyName("Blog (AI) 1", "Blog (AI)")).toBeNull();
    expect(nextAiCopyName("Blog (AI) 2 more", "Blog (AI)")).toBeNull();
  });
});

describe("isConflictError", () => {
  it("is true only for an error carrying status 409", () => {
    expect(isConflictError(Object.assign(new Error("dup"), { status: 409 }))).toBe(true);
    expect(isConflictError(Object.assign(new Error("bad"), { status: 422 }))).toBe(false);
    expect(isConflictError(new Error("network"))).toBe(false);
    expect(isConflictError("409")).toBe(false);
    expect(isConflictError(null)).toBe(false);
  });
});
