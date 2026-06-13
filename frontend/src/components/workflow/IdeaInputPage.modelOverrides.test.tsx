/**
 * ISS-014 (MODEL-03) — wiring assertion: the relocated per-agent model picker
 * (now in AgentsPopup, reported up via `onModelOverridesChange`) threads a
 * selection into the run_pipeline payload as `model_overrides`, and an EMPTY
 * selection leaves the payload byte-identical (no `model_overrides` key) so
 * existing runs are unchanged (INV-3).
 *
 * Strategy: mock `./AgentsPopup` with a tiny test double that surfaces the
 * `onModelOverridesChange` callback as a button. Driving that button simulates
 * the user picking a per-agent model. We then click Run and assert exactly what
 * `IdeaInputPage` passes to `onRun(..., extraParams)` — the contract the
 * DashboardLayout → useWorkflow `Object.assign(payload, context)` merge relies
 * on to land `model_overrides` in the `run_pipeline` payload.
 */

import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { IdeaInputPage } from "./IdeaInputPage";
import { SkillsHooksProvider } from "@/context/SkillsHooksContext";

// Speech recognition is browser-only; stub it so jsdom renders cleanly.
vi.mock("@/hooks/useSpeechRecognition", () => ({
  useSpeechRecognition: () => ({
    isListening: false,
    transcript: "",
    startListening: vi.fn(),
    stopListening: vi.fn(),
    isSupported: false,
  }),
}));

// Test double for AgentsPopup: it does not render the real model picker (which
// would fetch /api/capabilities). Instead it exposes the relocation contract —
// the `onModelOverridesChange` prop — as a button so the test can drive a
// per-agent model selection deterministically.
vi.mock("./AgentsPopup", () => ({
  AgentsPopup: ({
    onModelOverridesChange,
  }: {
    onModelOverridesChange?: (o: Record<string, string>) => void;
  }) => (
    <button
      type="button"
      data-testid="pick-model"
      onClick={() =>
        onModelOverridesChange?.({ "market-research-agent": "claude-sonnet-x" })
      }
    >
      pick model
    </button>
  ),
}));

// ReviewGatesSection reports gate selection; keep it inert so it never sends
// `gate_agent_ids` (we want to isolate the model_overrides path).
vi.mock("./ReviewGatesSection", () => ({
  ReviewGatesSection: () => null,
}));

function renderPage(onRun = vi.fn()) {
  render(
    <SkillsHooksProvider>
      <IdeaInputPage workflowType="user_stories" onBack={vi.fn()} onRun={onRun} />
    </SkillsHooksProvider>,
  );
  return { onRun };
}

describe("IdeaInputPage — MODEL-03 model_overrides wiring (ISS-014)", () => {
  it("threads a selected per-agent model into onRun extraParams.model_overrides", async () => {
    const user = userEvent.setup();
    const { onRun } = renderPage();

    // The user types a brief, picks a per-agent model, then runs.
    await user.type(screen.getByRole("textbox"), "Analyse the market.");
    await user.click(screen.getByTestId("pick-model"));
    await user.click(screen.getByRole("button", { name: /run workflow/i }));

    expect(onRun).toHaveBeenCalledTimes(1);
    const [message, agentIds, resolvedType, extraParams] = onRun.mock.calls[0];
    expect(message).toBe("Analyse the market.");
    expect(Array.isArray(agentIds)).toBe(true);
    expect(resolvedType).toBe("user_stories");
    // The selection lands as model_overrides — the exact key the backend
    // (_validate_model_overrides) reads off the run_pipeline payload.
    expect(extraParams).toEqual({
      model_overrides: { "market-research-agent": "claude-sonnet-x" },
    });
  });

  it("omits model_overrides entirely when nothing is picked (byte-identical payload, INV-3)", async () => {
    const user = userEvent.setup();
    const { onRun } = renderPage();

    await user.type(screen.getByRole("textbox"), "Analyse the market.");
    // No model pick, no gate touch → extraParams must be undefined.
    await user.click(screen.getByRole("button", { name: /run workflow/i }));

    expect(onRun).toHaveBeenCalledTimes(1);
    const [, , , extraParams] = onRun.mock.calls[0];
    expect(extraParams).toBeUndefined();
  });
});
