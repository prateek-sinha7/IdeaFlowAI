/**
 * effortHelpers.test.tsx — spec 020, the three helpers both authoring surfaces
 * share (`AgentsPopup` levers list and `CanvasConfigRail`).
 *
 * These are tested once, here, because both surfaces import them: the canvas
 * rail's own behaviour is covered end to end in
 * `composer/CanvasConfigRail.effort.test.tsx`, and this file is what stops the
 * levers list quietly growing a second copy of the same rules. That is exactly
 * how the pipeline-label map FIX-584 fixed came to disagree with itself.
 */

import { describe, it, expect } from "vitest";
import type { CapabilityModelEntry } from "@/lib/api";
import { effortLevelsFor, effortLabel, modelChangePatch } from "./AgentsPopup";

const GPT_LEVELS = ["none", "low", "medium", "high", "xhigh", "max"];
const CLAUDE_LEVELS = ["none", "on"];

const MODELS = [
  { id: "gpt", label: "GPT-5.6 Luna", reasoning_mode: "effort", reasoning_levels: GPT_LEVELS },
  { id: "claude", label: "Claude Haiku 4.5", reasoning_mode: "budget", reasoning_levels: CLAUDE_LEVELS },
  { id: "no-reasoning", label: "No-Reasoning Model", reasoning_mode: "none", reasoning_levels: [] },
  // An older backend that predates spec 020 sends neither field.
  { id: "legacy", label: "Legacy" },
] as CapabilityModelEntry[];

describe("effortLevelsFor", () => {
  it("returns the selected model's own levels", () => {
    expect(effortLevelsFor("gpt", MODELS)).toEqual(GPT_LEVELS);
    expect(effortLevelsFor("claude", MODELS)).toEqual(CLAUDE_LEVELS);
  });

  it("returns nothing for a model with no reasoning control", () => {
    expect(effortLevelsFor("no-reasoning", MODELS)).toEqual([]);
  });

  it("returns nothing when no model is selected — the workflow default applies", () => {
    // The surface cannot know the workflow model's levels, and guessing would
    // offer a scale the step may not honour.
    expect(effortLevelsFor(undefined, MODELS)).toEqual([]);
    expect(effortLevelsFor("", MODELS)).toEqual([]);
  });

  it("returns nothing for an unknown id or a payload without the field", () => {
    // Degrades to "no control", never throws: an older backend must not blank
    // the whole config surface.
    expect(effortLevelsFor("nope", MODELS)).toEqual([]);
    expect(effortLevelsFor("legacy", MODELS)).toEqual([]);
  });
});

describe("effortLabel", () => {
  it("reads 'none' as None on GPT and Off on Claude", () => {
    // Same wire value, different promise — on GPT it is the bottom of a scale,
    // on Claude it turns extended thinking off.
    expect(effortLabel("none", "effort")).toBe("None");
    expect(effortLabel("none", "budget")).toBe("Off");
    expect(effortLabel("none", "adaptive")).toBe("Off");
    expect(effortLabel("none", undefined)).toBe("Off");
  });

  it("keeps xHigh's internal capital", () => {
    expect(effortLabel("xhigh", "effort")).toBe("xHigh");
  });

  it("title-cases every other level", () => {
    expect(["low", "medium", "high", "max"].map((l) => effortLabel(l, "effort")))
      .toEqual(["Low", "Medium", "High", "Max"]);
    expect(effortLabel("on", "budget")).toBe("On");
  });
});

describe("modelChangePatch", () => {
  it("drops an effort the new model does not accept", () => {
    expect(modelChangePatch("claude", "xhigh", MODELS)).toEqual({ model: "claude", effort: "" });
  });

  it("keeps an effort both models accept", () => {
    // Clearing indiscriminately would silently re-enable thinking on a step the
    // user had turned it off for.
    expect(modelChangePatch("gpt", "none", MODELS)).toEqual({ model: "gpt", effort: "none" });
  });

  it("clears the effort when the new model has no reasoning control at all", () => {
    expect(modelChangePatch("no-reasoning", "high", MODELS)).toEqual({ model: "no-reasoning", effort: "" });
  });

  it("clears the effort when switching back to the workflow default", () => {
    expect(modelChangePatch("", "high", MODELS)).toEqual({ model: "", effort: "" });
  });

  it("leaves an unset effort unset", () => {
    expect(modelChangePatch("gpt", undefined, MODELS)).toEqual({ model: "gpt", effort: "" });
  });
});
