/**
 * ISS-876 / workflow-gaps gap 2: a built-in canvas "Save as copy" must carry the
 * built-in's top-level manifest keys (limits, input_providers, seed_files,
 * capabilities, pass-through keys) from GET /api/workflows/{id} into the saved copy.
 */
import { describe, it, expect } from "vitest";
import { builtinAuthoringSeed, buildWorkflowManifest } from "./userWorkflows";
import type { WorkflowAuthoringManifest } from "@/lib/api";

const PROTOTYPE_V2: WorkflowAuthoringManifest = {
  limits: { max_subagents: 200, max_depth: 2, wall_clock_seconds: 10800 },
  input_providers: ["run_images"],
  seed_files: { "README.md": "seed" },
  capabilities: { internet: false },
  allowed_workers: ["prototype-build"],
};

describe("builtinAuthoringSeed", () => {
  it("returns no manifest when the payload carries none", () => {
    expect(builtinAuthoringSeed(null)).toEqual({ manifest: null, runConfig: {} });
    expect(builtinAuthoringSeed(undefined)).toEqual({ manifest: null, runConfig: {} });
  });

  it("returns a copy of the authoring manifest with no identity key", () => {
    const { manifest } = builtinAuthoringSeed(PROTOTYPE_V2);
    expect(manifest).toEqual(PROTOTYPE_V2);
    expect(manifest).not.toBe(PROTOTYPE_V2);
    expect(manifest).not.toHaveProperty("id");
  });

  it("seeds the opendesign provider and design mode, which are recomputed on save", () => {
    const { runConfig } = builtinAuthoringSeed({
      context_providers: ["opendesign", "chain_context"],
      design_mode: "web",
    });
    expect(runConfig).toEqual({ contextProvider: "opendesign", designMode: "web" });
  });

  it("seeds no provider when the built-in declares none the composer models", () => {
    const { runConfig } = builtinAuthoringSeed({
      context_providers: ["chain_context"],
      design_mode: "web",
    });
    expect(runConfig).toEqual({});
  });
});

describe("buildWorkflowManifest for a built-in copy", () => {
  it("round-trips limits, input_providers, seed_files and pass-through keys from the seed", () => {
    const { manifest: source } = builtinAuthoringSeed(PROTOTYPE_V2);

    const saved = {
      ...buildWorkflowManifest([], PROTOTYPE_V2.capabilities, undefined, undefined, source),
    } as Record<string, unknown>;

    expect(saved.limits).toEqual(PROTOTYPE_V2.limits);
    expect(saved.input_providers).toEqual(["run_images"]);
    expect(saved.seed_files).toEqual({ "README.md": "seed" });
    expect(saved.allowed_workers).toEqual(["prototype-build"]);
    expect(saved.capabilities).toEqual({ internet: false });
    expect(saved).not.toHaveProperty("id");
  });
});
