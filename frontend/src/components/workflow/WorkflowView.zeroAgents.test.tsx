/**
 * ISS-328 — the legacy `/workflow` builder's "Run Workflow" button must stay
 * disabled while zero agents are attached, even when the idea textarea has
 * text. `WorkflowView.tsx:473` currently gates `disabled` on
 * `!ideaInput.trim()` alone, ignoring `pipelineAgents.length` — the same
 * count rendered right next to the button as "Workflow Agents (0)".
 *
 * Redux's agents slice starts empty by default, so a plain render with no
 * preloaded agents reproduces the zero-agents condition validated in the
 * ISS-328 card.
 */
import { describe, it, expect, vi } from "vitest";
import { renderWithProviders, screen } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";
import { WorkflowView } from "./WorkflowView";

vi.mock("@/hooks/useSpeechRecognition", () => ({
  useSpeechRecognition: () => ({
    isListening: false,
    transcript: "",
    startListening: vi.fn(),
    stopListening: vi.fn(),
    isSupported: false,
  }),
}));

describe("WorkflowView — zero agents (ISS-328)", () => {
  // `it.fails` is vitest's xfail(strict=True) — it must fail now (ISS-328
  // unfixed) and flip to a loud failure the moment the disabled-gate fix lands,
  // so the marker can be removed.
  it.fails("ISS-328 — keeps Run Workflow disabled when 0 agents are attached, regardless of brief text", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <WorkflowView pipelineType="user_stories" userMessage="" onClose={vi.fn()} />
    );

    // Confirm the zero-agents precondition the card validated.
    expect(screen.getByText("Workflow Agents")).toBeInTheDocument();
    expect(screen.getByText("(0)")).toBeInTheDocument();

    const textarea = screen.getByPlaceholderText(/describe what you want to build/i);
    await user.type(textarea, "zz-hunt brief with zero agents attached");

    const runButton = screen.getByRole("button", { name: /run workflow/i });
    expect(runButton).toBeDisabled();
  });
});
