import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { CapabilityModelEntry } from "@/lib/api";
import type { BuilderModelsResponse } from "@/types/workflowBuilder";

import { BuilderModelPicker, type BuilderModelPickerProps } from "./BuilderModelPicker";

function entry(
  id: string,
  label: string,
  reasoning_mode: CapabilityModelEntry["reasoning_mode"],
  reasoning_levels: string[],
): CapabilityModelEntry {
  return {
    id,
    label,
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

const response: BuilderModelsResponse = {
  models: [
    entry("sonnet", "Sonnet", "adaptive", ["low", "high"]),
    entry("opus", "Opus", "budget", ["none", "on"]),
    entry("plain", "Plain", "none", []),
  ],
  default_model_id: "sonnet",
  default_efforts: { sonnet: "low", opus: "on", plain: null },
};

function setup(overrides: Partial<BuilderModelPickerProps> = {}) {
  const props: BuilderModelPickerProps = {
    state: { status: "ready", response },
    choice: { modelId: "sonnet", effort: "low" },
    note: null,
    onModelChange: vi.fn(),
    onEffortChange: vi.fn(),
    onRetry: vi.fn(),
    ...overrides,
  };
  render(<BuilderModelPicker {...props} />);
  return props;
}

describe("BuilderModelPicker", () => {
  it("offers the server's models and the model's thinking levels in labelled selects", () => {
    setup();
    const model = screen.getByRole("combobox", { name: "Model" });
    expect(within(model).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Sonnet",
      "Opus",
      "Plain",
    ]);
    const thinking = screen.getByRole("combobox", { name: "Thinking" });
    expect(within(thinking).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Low",
      "High",
    ]);
  });

  it("offers exactly Off and On for a none/on model", () => {
    setup({ choice: { modelId: "opus", effort: "on" } });
    const thinking = screen.getByRole("combobox", { name: "Thinking" });
    expect(within(thinking).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Off",
      "On",
    ]);
  });

  it("hides the Thinking select for a model with reasoning_mode none", () => {
    setup({ choice: { modelId: "plain", effort: null } });
    expect(screen.getByRole("combobox", { name: "Model" })).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Thinking" })).toBeNull();
  });

  it("reports model and effort changes", async () => {
    const user = userEvent.setup();
    const props = setup();
    await user.selectOptions(screen.getByRole("combobox", { name: "Model" }), "opus");
    await user.selectOptions(screen.getByRole("combobox", { name: "Thinking" }), "high");
    expect(props.onModelChange).toHaveBeenCalledWith("opus");
    expect(props.onEffortChange).toHaveBeenCalledWith("high");
  });

  it("disables both selects when disabled", () => {
    setup({ disabled: true });
    expect(screen.getByRole("combobox", { name: "Model" })).toBeDisabled();
    expect(screen.getByRole("combobox", { name: "Thinking" })).toBeDisabled();
  });

  it("shows an error with Retry when the list failed to load", async () => {
    const user = userEvent.setup();
    const props = setup({ state: { status: "error" }, choice: null });
    expect(screen.getByRole("alert")).toHaveTextContent("Could not load the model list");
    expect(screen.queryByRole("combobox")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(props.onRetry).toHaveBeenCalledOnce();
  });

  it("shows a loading status while the list loads", () => {
    setup({ state: { status: "loading" }, choice: null });
    expect(screen.getByRole("status")).toHaveTextContent("Loading models");
  });

  it("says when no model is offered", () => {
    setup({ state: { status: "ready", response: { ...response, models: [] } }, choice: null });
    expect(screen.getByText(/No models are available/)).toBeInTheDocument();
  });

  it("explains a stored model that is no longer offered", () => {
    setup({ note: { kind: "stored_model_unavailable", storedModelId: "gone" } });
    expect(screen.getByText(/no longer available. Using Sonnet/)).toBeInTheDocument();
  });
});
