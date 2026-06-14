/**
 * WR-01 (LAUNCH-EXISTING-PATH §4.6) — the AgentModelPicker MERGE contract.
 *
 * On launch-replay of a saved workflow the picker is seeded with the persisted
 * per-agent overrides (`initialOverrides`). Because `onChange` emits the picker's
 * WHOLE internal map, a picker that started EMPTY would, on the first edit of any
 * agent, replace the seeded overrides wholesale — silently dropping the persisted
 * models for the other agents (the correctness regression WR-01 flagged).
 *
 * These tests pin both branches:
 *   1. Seeded override for agent A SURVIVES changing agent B's model (merge).
 *   2. No-seed default is unchanged — every select shows "Default", and a single
 *      pick emits just that agent (no regression on compose-from-scratch).
 *
 * `getCapabilities` is mocked so the picker renders without a real
 * /api/capabilities fetch.
 */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { CapabilityModelEntry } from "@/lib/api";

const mockGetCapabilities = vi.fn();
vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getCapabilities: (token: string) => mockGetCapabilities(token),
}));

import { AgentModelPicker } from "./AgentModelPicker";

const MODELS: CapabilityModelEntry[] = [
  {
    id: "model-x", label: "Model X", description: "", tier: "enterprise",
    cost_class: "standard", provider: "anthropic", context_window: 200000,
    user_allowed: true,
  },
  {
    id: "model-y", label: "Model Y", description: "", tier: "enterprise",
    cost_class: "standard", provider: "anthropic", context_window: 200000,
    user_allowed: true,
  },
];

const AGENTS = [
  { id: "agent-a", name: "Agent A" },
  { id: "agent-b", name: "Agent B" },
];

describe("AgentModelPicker — WR-01 seeded-override merge", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetCapabilities.mockResolvedValue({ model_catalog: MODELS });
  });

  it("merges (does NOT replace) a seeded override when another agent's model changes", async () => {
    const onChange = vi.fn();
    render(
      <AgentModelPicker
        agents={AGENTS}
        onChange={onChange}
        initialOverrides={{ "agent-a": "model-x" }}
      />,
    );

    // The seeded select reflects the persisted model on mount.
    const selects = await waitFor(() => {
      const found = screen.getAllByRole("combobox");
      expect(found.length).toBe(2);
      return found;
    });
    const [selectA, selectB] = selects as HTMLSelectElement[];
    expect(selectA.value).toBe("model-x"); // seeded, not "Default"
    expect(selectB.value).toBe(""); // unseeded → Default

    // Change agent B's model → onChange must emit BOTH (merge), not just B.
    await userEvent.selectOptions(selectB, "model-y");

    expect(onChange).toHaveBeenLastCalledWith({
      "agent-a": "model-x", // the seeded override SURVIVES
      "agent-b": "model-y",
    });
  });

  it("with no seed, defaults every agent to 'Default' and emits only the picked agent", async () => {
    const onChange = vi.fn();
    render(<AgentModelPicker agents={AGENTS} onChange={onChange} />);

    const selects = (await waitFor(() => {
      const found = screen.getAllByRole("combobox");
      expect(found.length).toBe(2);
      return found;
    })) as HTMLSelectElement[];
    expect(selects[0].value).toBe(""); // "Default"
    expect(selects[1].value).toBe("");

    await userEvent.selectOptions(selects[0], "model-x");
    expect(onChange).toHaveBeenLastCalledWith({ "agent-a": "model-x" });
  });
});
