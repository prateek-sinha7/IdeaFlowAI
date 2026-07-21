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

// ── 51-06 (FANOUT-01 / D6/D7/D9) — the simple-view fan-out control ───────────────
//
// The AdvancedExpander gains a "Fan out over a list" toggle + a "Source list
// from" picker per agent row, driven by the SAME `updateLever`/`applyLeverPatch`
// reducer (no reducer change). These tests pin the FE guardrails:
//   1. Enabling persists `{ strategy: "fanout_batch", task_source: { source_step } }`
//      and defaults the source to a KNOWN upstream producer.
//   2. The source picker lists ONLY earlier agents (never this row or later ones).
//   3. The toggle is DISABLED for a step with no upstream (first agent) + hint.
//   4. Toggling OFF clears the levers (the selection is omitted when empty, INV-3).
//   5. A NON-blocking warning renders when the chosen source is not a known producer.
describe("AdvancedExpander — 51-06 fan-out control (FANOUT-01)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetCapabilities.mockResolvedValue(PALETTE);
  });

  // `prototype-plan` is a v1 KNOWN `## Task N:` producer; `writer` is not.
  const PRODUCER_THEN_WORKER = [
    { id: "prototype-plan", name: "Plan" },
    { id: "writer", name: "Writer" },
  ];

  async function expandRow(name: RegExp) {
    await userEvent.click(await screen.findByRole("button", { name }));
  }

  it("persists {strategy: 'fanout_batch', task_source.source_step} when enabled, defaulting to a known upstream producer", async () => {
    const onSelectionsChange = vi.fn();
    render(
      <AdvancedExpander
        agents={PRODUCER_THEN_WORKER}
        onSelectionsChange={onSelectionsChange}
      />,
    );
    await expandRow(/advanced — writer/i);

    await userEvent.click(
      screen.getByLabelText(/fan out over a list for writer/i),
    );

    const last = onSelectionsChange.mock.calls.at(-1)?.[0];
    expect(last["writer"]).toMatchObject({
      strategy: "fanout_batch",
      task_source: {
        kind: "parsed",
        parser: "heading_tasks",
        source_step: "prototype-plan", // the known producer, auto-selected
      },
    });
    // A known producer → NO unknown-producer warning.
    expect(
      screen.queryByText(/fans out one worker per/i),
    ).not.toBeInTheDocument();
  });

  it("lists ONLY earlier agents in the source picker (never this row or later)", async () => {
    const THREE = [
      { id: "step-a", name: "Alpha" },
      { id: "step-b", name: "Beta" },
      { id: "step-c", name: "Gamma" },
    ];
    const onSelectionsChange = vi.fn();
    render(
      <AdvancedExpander agents={THREE} onSelectionsChange={onSelectionsChange} />,
    );
    await expandRow(/advanced — gamma/i);
    await userEvent.click(
      screen.getByLabelText(/fan out over a list for gamma/i),
    );

    const source = screen.getByLabelText(/source list for gamma/i);
    // Earlier agents only: Alpha + Beta are offered, Gamma (self) is NOT.
    expect(within(source).getByText("Alpha")).toBeInTheDocument();
    expect(within(source).getByText("Beta")).toBeInTheDocument();
    expect(within(source).queryByText("Gamma")).not.toBeInTheDocument();
    // No known producer upstream → default is the immediately-preceding step.
    const last = onSelectionsChange.mock.calls.at(-1)?.[0];
    expect(last["step-c"].task_source.source_step).toBe("step-b");
  });

  it("disables the fan-out toggle for the first agent (no upstream) with a hint", async () => {
    render(
      <AdvancedExpander
        agents={PRODUCER_THEN_WORKER}
        onSelectionsChange={vi.fn()}
      />,
    );
    await expandRow(/advanced — plan/i);

    const toggle = screen.getByLabelText(/fan out over a list for plan/i);
    expect(toggle).toBeDisabled();
    expect(
      screen.getByText(/add an earlier step that outputs a task list/i),
    ).toBeInTheDocument();
  });

  it("clears the fan-out levers when toggled OFF (selection omitted when empty)", async () => {
    const onSelectionsChange = vi.fn();
    render(
      <AdvancedExpander
        agents={PRODUCER_THEN_WORKER}
        onSelectionsChange={onSelectionsChange}
      />,
    );
    await expandRow(/advanced — writer/i);

    const toggle = screen.getByLabelText(/fan out over a list for writer/i);
    await userEvent.click(toggle); // ON
    expect(onSelectionsChange.mock.calls.at(-1)?.[0]["writer"]).toMatchObject({
      strategy: "fanout_batch",
    });

    await userEvent.click(toggle); // OFF → clears every fan-out lever
    const last = onSelectionsChange.mock.calls.at(-1)?.[0];
    // Nothing else was set on this step → the whole selection is omitted (INV-3).
    expect(last["writer"]).toBeUndefined();
  });

  it("renders a non-blocking warning when the chosen source is not a known producer", async () => {
    const NON_PRODUCER = [
      { id: "researcher", name: "Researcher" },
      { id: "writer", name: "Writer" },
    ];
    const onSelectionsChange = vi.fn();
    render(
      <AdvancedExpander
        agents={NON_PRODUCER}
        onSelectionsChange={onSelectionsChange}
      />,
    );
    await expandRow(/advanced — writer/i);
    await userEvent.click(
      screen.getByLabelText(/fan out over a list for writer/i),
    );

    // `researcher` is not on the known-producer allow-list → steer the user.
    expect(
      screen.getByText(/fans out one worker per/i),
    ).toBeInTheDocument();
    // The lever is still persisted (non-blocking — the server compile is the backstop).
    expect(
      onSelectionsChange.mock.calls.at(-1)?.[0]["writer"].strategy,
    ).toBe("fanout_batch");
  });

  it("offers earlier steps via the priorAgents prop even when rendered for a single agent", async () => {
    // The per-agent config surface renders the expander with ONE agent + the
    // upstream steps as `priorAgents`; the picker must still offer them.
    const onSelectionsChange = vi.fn();
    render(
      <AdvancedExpander
        agents={[{ id: "writer", name: "Writer" }]}
        priorAgents={[{ id: "prototype-plan", name: "Plan" }]}
        onSelectionsChange={onSelectionsChange}
      />,
    );
    await expandRow(/advanced — writer/i);

    const toggle = screen.getByLabelText(/fan out over a list for writer/i);
    expect(toggle).toBeEnabled();
    await userEvent.click(toggle);

    const last = onSelectionsChange.mock.calls.at(-1)?.[0];
    expect(last["writer"].task_source.source_step).toBe("prototype-plan");
    const source = screen.getByLabelText(/source list for writer/i);
    expect(within(source).getByText("Plan")).toBeInTheDocument();
  });
});
