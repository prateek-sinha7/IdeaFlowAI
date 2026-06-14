/**
 * EMP-01 / EMP-04 (D-05/D-07) — the per-agent "Advanced" expander contract.
 *
 * The composer lets a user opt a step (agent ≈ step) into user-allowed
 * capabilities through a collapsed-by-default "Advanced" expander. Selecting a
 * lever feeds a compact per-step selections map
 *   `{ agent_id: { validators?, gates?, model?, retry? } }`
 * reported upward via `onSelectionsChange` — the EXACT shape 22-04 persists in
 * `manifest_json` and `_apply_selections` overlays onto the compiled plan.
 *
 * These tests pin:
 *   1. Collapsed by default; toggling reveals lever rows in the fixed order
 *      Validator → Gate → Model → Retry; `aria-expanded` reflects state.
 *   2. Selecting validator + gate + non-default model + retry updates the
 *      selections map (reported via `onSelectionsChange`).
 *   3. EMP-04: selecting a validator auto-attaches the required `validation`
 *      gate (mirrors selections.py coupling) and renders the auto-attach notice
 *      as a `role="status"` live region.
 *   4. An unselected lever emits NO override (the map omits the key — parity
 *      with the "Default" model semantics).
 *
 * Lever OPTIONS come from the live `/api/capabilities` palette payload
 * (user_allowed caps of the relevant kinds + the model catalog) — NEVER a
 * hardcoded list (SC-001). `getCapabilities` is mocked so the expander renders
 * without a real fetch.
 */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { CapabilitiesPalette } from "@/lib/api";

const mockGetCapabilities = vi.fn();
vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getCapabilities: (token: string) => mockGetCapabilities(token),
}));

import { AdvancedExpander } from "./AgentsPopup";

const PALETTE: CapabilitiesPalette = {
  capabilities: [
    {
      kind: "validator",
      name: "code_test",
      user_allowed: true,
      description: "Runs the generated tests.",
      security_gated: false,
      config_schema: {},
    },
    {
      kind: "gate",
      name: "approval",
      user_allowed: true,
      description: "Human approval gate.",
      security_gated: false,
      config_schema: {},
    },
    {
      kind: "gate",
      name: "security",
      user_allowed: false, // locked — must NOT be offered as a selectable option
      description: "Security review gate.",
      security_gated: true,
      config_schema: {},
    },
  ],
  model_catalog: [
    {
      id: "model-premium",
      label: "Premium Model",
      description: "",
      tier: "enterprise",
      cost_class: "premium",
      provider: "anthropic",
      context_window: 200000,
      user_allowed: true,
    },
  ],
};

const AGENTS = [{ id: "agent-a", name: "Agent A" }];

describe("AdvancedExpander — EMP-01 per-agent levers", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetCapabilities.mockResolvedValue(PALETTE);
  });

  it("is collapsed by default and toggles to reveal levers in order Validator → Gate → Model → Retry", async () => {
    render(<AdvancedExpander agents={AGENTS} onSelectionsChange={vi.fn()} />);

    const toggle = await screen.findByRole("button", { name: /advanced/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    // Levers are not in the DOM while collapsed.
    expect(screen.queryByLabelText(/validator/i)).not.toBeInTheDocument();

    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");

    // Lever rows present in the fixed order.
    const validator = screen.getByLabelText(/validator/i);
    const gate = screen.getByLabelText(/^gate/i);
    const model = screen.getByLabelText(/model/i);
    const retry = screen.getByLabelText(/retry/i);
    const order = [validator, gate, model, retry];
    for (let i = 1; i < order.length; i++) {
      // Each later lever follows the previous one in document order.
      expect(
        order[i - 1].compareDocumentPosition(order[i]) &
          Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
    }
  });

  it("feeds the selections map when a validator, gate, model and retry are picked", async () => {
    const onSelectionsChange = vi.fn();
    render(
      <AdvancedExpander agents={AGENTS} onSelectionsChange={onSelectionsChange} />,
    );
    await userEvent.click(await screen.findByRole("button", { name: /advanced/i }));

    await userEvent.selectOptions(screen.getByLabelText(/validator/i), "code_test");
    await userEvent.selectOptions(screen.getByLabelText(/^gate/i), "approval");
    await userEvent.selectOptions(screen.getByLabelText(/model/i), "model-premium");
    await userEvent.selectOptions(screen.getByLabelText(/retry/i), "2");

    const last = onSelectionsChange.mock.calls.at(-1)?.[0];
    expect(last["agent-a"]).toMatchObject({
      validators: ["code_test"],
      // EMP-04 auto-attached `validation`, plus the explicitly picked `approval`.
      gates: expect.arrayContaining(["validation", "approval"]),
      model: "model-premium",
      retry: 2,
    });
  });

  it("auto-attaches the validation gate and announces it (EMP-04) when a validator is selected", async () => {
    const onSelectionsChange = vi.fn();
    render(
      <AdvancedExpander agents={AGENTS} onSelectionsChange={onSelectionsChange} />,
    );
    await userEvent.click(await screen.findByRole("button", { name: /advanced/i }));

    await userEvent.selectOptions(screen.getByLabelText(/validator/i), "code_test");

    // The auto-attach notice is a polite live region with the UI-SPEC copy.
    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent(/added required validation gate/i);

    // The selections map carries the auto-attached gate.
    const last = onSelectionsChange.mock.calls.at(-1)?.[0];
    expect(last["agent-a"].gates).toContain("validation");
  });

  it("emits no override for an unselected lever (the map omits the key)", async () => {
    const onSelectionsChange = vi.fn();
    render(
      <AdvancedExpander agents={AGENTS} onSelectionsChange={onSelectionsChange} />,
    );
    await userEvent.click(await screen.findByRole("button", { name: /advanced/i }));

    // Pick ONLY a model; validators/gates/retry stay at "Default" (unselected).
    await userEvent.selectOptions(screen.getByLabelText(/model/i), "model-premium");

    const last = onSelectionsChange.mock.calls.at(-1)?.[0];
    expect(last["agent-a"]).toEqual({ model: "model-premium" });
    expect(last["agent-a"]).not.toHaveProperty("validators");
    expect(last["agent-a"]).not.toHaveProperty("gates");
    expect(last["agent-a"]).not.toHaveProperty("retry");
  });

  it("does not offer a locked (user_allowed=false) gate as a selectable option", async () => {
    render(<AdvancedExpander agents={AGENTS} onSelectionsChange={vi.fn()} />);
    await userEvent.click(await screen.findByRole("button", { name: /advanced/i }));

    const gate = screen.getByLabelText(/^gate/i);
    // `security` is user_allowed=false → never an <option> in the lever select.
    expect(within(gate).queryByText("security")).not.toBeInTheDocument();
    // `approval` (user_allowed=true) IS offered.
    expect(within(gate).getByText("approval")).toBeInTheDocument();
  });
});
