import { describe, expect, it } from "vitest";

import type { CapabilityModelEntry } from "@/lib/api";

import { changeModel, defaultEffortFor, preselect, thinkingOptions } from "./modelPicker";

function entry(
  id: string,
  reasoning_mode: CapabilityModelEntry["reasoning_mode"],
  reasoning_levels: string[],
): CapabilityModelEntry {
  return {
    id,
    label: id,
    description: "",
    tier: "standard",
    cost_class: "standard",
    provider: "anthropic",
    context_window: 200000,
    user_allowed: true,
    reasoning_mode,
    reasoning_levels,
  };
}

const response = {
  models: [
    entry("sonnet", "adaptive", ["low", "medium", "high"]),
    entry("opus", "budget", ["none", "high"]),
    entry("plain", "none", []),
  ],
  default_model_id: "sonnet",
  default_efforts: { sonnet: "medium", opus: "high", plain: null },
};

describe("thinkingOptions", () => {
  it("labels the selected model's levels with effortLabel", () => {
    expect(thinkingOptions("opus", response.models)).toEqual([
      { value: "none", label: "Off" },
      { value: "high", label: "High" },
    ]);
  });

  it("returns no options for reasoning_mode none", () => {
    expect(thinkingOptions("plain", response.models)).toEqual([]);
  });
});

describe("changeModel", () => {
  it("keeps the effort when the new model accepts it", () => {
    expect(changeModel("opus", "high", response)).toEqual({ modelId: "opus", effort: "high" });
  });

  it("uses the new model's default effort when the old one is not accepted", () => {
    expect(changeModel("sonnet", "none", response)).toEqual({
      modelId: "sonnet",
      effort: "medium",
    });
  });

  it("sends null effort for a model without levels", () => {
    expect(changeModel("plain", "high", response)).toEqual({ modelId: "plain", effort: null });
  });
});

describe("defaultEffortFor", () => {
  it("falls back to the first level when default_efforts has no usable entry", () => {
    expect(defaultEffortFor("sonnet", { ...response, default_efforts: {} })).toBe("low");
  });
});

describe("preselect", () => {
  it("prefers the stored model and effort", () => {
    expect(
      preselect({
        response,
        stored: { modelId: "opus", effort: "none" },
        preferredModelId: "sonnet",
      }),
    ).toEqual({ choice: { modelId: "opus", effort: "none" }, note: null });
  });

  it("falls back to the preference, with a note, when the stored model is gone", () => {
    expect(
      preselect({
        response,
        stored: { modelId: "retired", effort: "high" },
        preferredModelId: "opus",
      }),
    ).toEqual({
      choice: { modelId: "opus", effort: "high" },
      note: { kind: "stored_model_unavailable", storedModelId: "retired" },
    });
  });

  it("uses the default model when there is no stored model and the preference is not offered", () => {
    expect(preselect({ response, stored: null, preferredModelId: "gpt" })).toEqual({
      choice: { modelId: "sonnet", effort: "medium" },
      note: null,
    });
  });

  it("uses the first offered model when the default is not offered", () => {
    expect(preselect({ response: { ...response, default_model_id: "gone" } })).toEqual({
      choice: { modelId: "sonnet", effort: "medium" },
      note: { kind: "default_unavailable", defaultModelId: "gone" },
    });
  });

  it("returns no choice when no model is offered", () => {
    expect(preselect({ response: { ...response, models: [] } })).toEqual({
      choice: null,
      note: null,
    });
  });
});
