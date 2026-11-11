import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CapabilityModelEntry } from "@/lib/api";
import type { BuilderModelsResponse } from "@/types/workflowBuilder";

const getBuilderModels = vi.fn();
const getToken = vi.fn();

vi.mock("@/lib/workflowBuilderApi", () => ({
  getBuilderModels: (token: string) => getBuilderModels(token),
}));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  getToken: () => getToken(),
}));

import { useBuilderModelPicker } from "./useBuilderModelPicker";

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

const response: BuilderModelsResponse = {
  models: [entry("sonnet", "adaptive", ["low", "high"]), entry("opus", "budget", ["none", "on"])],
  default_model_id: "sonnet",
  default_efforts: { sonnet: "low", opus: "on" },
};

describe("useBuilderModelPicker", () => {
  beforeEach(() => {
    getBuilderModels.mockReset();
    getToken.mockReset().mockReturnValue("tok");
  });

  it("loads the list from GET /models and preselects the default", async () => {
    getBuilderModels.mockResolvedValue(response);
    const { result } = renderHook(() => useBuilderModelPicker());
    expect(result.current.state.status).toBe("loading");
    await waitFor(() => expect(result.current.state.status).toBe("ready"));
    expect(getBuilderModels).toHaveBeenCalledWith("tok");
    expect(result.current.choice).toEqual({ modelId: "sonnet", effort: "low" });
  });

  it("applies modelChangePatch rules when the model changes", async () => {
    getBuilderModels.mockResolvedValue(response);
    const { result } = renderHook(() => useBuilderModelPicker());
    await waitFor(() => expect(result.current.state.status).toBe("ready"));
    act(() => result.current.onModelChange("opus"));
    expect(result.current.choice).toEqual({ modelId: "opus", effort: "on" });
    act(() => result.current.onEffortChange("none"));
    expect(result.current.choice).toEqual({ modelId: "opus", effort: "none" });
  });

  it("preselects the stored model and effort", async () => {
    getBuilderModels.mockResolvedValue(response);
    const { result } = renderHook(() =>
      useBuilderModelPicker({ stored: { modelId: "opus", effort: "none" } }),
    );
    await waitFor(() => expect(result.current.state.status).toBe("ready"));
    expect(result.current.choice).toEqual({ modelId: "opus", effort: "none" });
  });

  it("reports an error and reloads on retry", async () => {
    getBuilderModels.mockRejectedValueOnce(new Error("boom")).mockResolvedValueOnce(response);
    const { result } = renderHook(() => useBuilderModelPicker());
    await waitFor(() => expect(result.current.state.status).toBe("error"));
    expect(result.current.choice).toBeNull();
    act(() => result.current.onRetry());
    expect(result.current.state.status).toBe("loading");
    await waitFor(() => expect(result.current.state.status).toBe("ready"));
    expect(getBuilderModels).toHaveBeenCalledTimes(2);
  });

  it("reports an error without a token and sends no request", async () => {
    getToken.mockReturnValue(null);
    const { result } = renderHook(() => useBuilderModelPicker());
    await waitFor(() => expect(result.current.state.status).toBe("error"));
    expect(getBuilderModels).not.toHaveBeenCalled();
  });
});
