/**
 * AI Workflow Builder draft effort in `ComposerPage` (task 20.9; Req 7.5, 49.9,
 * R-12): a draft step that sets a model and an effort shows that effort in the
 * config rail, and changing the step's model moves the effort the way
 * `modelChangePatch` says (kept when the new model accepts it, cleared when not).
 *
 * The page, the canvas and the config rail are real. Only `@/lib/api` is
 * replaced, with a capability palette whose model entries carry the reasoning
 * levels, so no model or level list is written into the assertions by hand: the
 * expected effort is computed from the same palette through `modelChangePatch`.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, waitFor } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";
import type { CapabilitiesPalette } from "@/lib/api";
import { saveUserWorkflow } from "@/lib/api";
import type { WorkflowManifest, WorkflowType } from "@/types/index";
import type { ComposerBuilderBinding } from "@/types/workflowBuilder";
import { modelChangePatch } from "@/components/workflow/AgentsPopup";

const mockGetCapabilities = vi.fn();
vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getCapabilities: (token: string) => mockGetCapabilities(token),
  saveUserWorkflow: vi.fn(),
  getWorkflowDetail: vi.fn().mockResolvedValue({ steps: [] }),
  getAgentPrompt: vi.fn().mockResolvedValue({ prompt_body: "", override: null, has_override: false }),
  saveAgentPromptOverride: vi.fn(),
  deleteAgentPromptOverride: vi.fn(),
}));

vi.mock("@/hooks/useSkillsCatalog", () => ({
  useSkillsCatalog: () => ({ skills: [], categories: [] }),
}));

import { ComposerPage } from "./ComposerPage";

const GPT = "global.openai.gpt-5.6-luna";
const CLAUDE = "eu.anthropic.claude-haiku-4-5-20251001-v1:0";

const PALETTE: CapabilitiesPalette = {
  capabilities: [],
  model_catalog: [
    { id: GPT, label: "GPT-5.6 Luna", description: "", tier: "fast", cost_class: "cheap", provider: "bedrock", context_window: 1000000, user_allowed: true, reasoning_mode: "effort", reasoning_levels: ["none", "low", "medium", "high", "xhigh", "max"] },
    { id: CLAUDE, label: "Claude Haiku 4.5", description: "", tier: "fast", cost_class: "cheap", provider: "bedrock", context_window: 200000, user_allowed: true, reasoning_mode: "budget", reasoning_levels: ["none", "on"] },
  ],
};

function manifestWith(model: string, effort: string): WorkflowManifest {
  return {
    steps: [
      {
        agent: "custom-agent",
        instance_id: "writer",
        name: "Writer",
        prompt: "Write it.",
        model: { model, effort },
      },
    ],
  } as unknown as WorkflowManifest;
}

function binding(manifest: WorkflowManifest): ComposerBuilderBinding {
  return {
    draft: { revision: 1, manifest, targetTrust: "user" },
    turnRunning: false,
    panelOpen: false,
    aiButtonVisible: false,
    onAiButton: vi.fn(),
    registerCanvasApi: vi.fn(),
    onSaved: vi.fn(),
  };
}

/** Render the composer with a draft applied, then open the Config tab of its one step. */
async function openAppliedStep(manifest: WorkflowManifest) {
  renderWithProviders(
    <ComposerPage
      workflowType={"custom" as WorkflowType}
      onBack={() => {}}
      initialName="My flow"
      onRun={vi.fn()}
      builder={binding(manifest)}
    />,
  );
  await userEvent.click(await screen.findByTestId("canvas-node-writer"));
  await userEvent.click(await screen.findByRole("tab", { name: /config/i }));
  await screen.findByLabelText(/^Model$/i);
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGetCapabilities.mockResolvedValue(PALETTE);
});

describe("ComposerPage builder draft — step effort", () => {
  it("shows_theDraftModelAndEffort_whenTheStepIsOpenedInTheConfigRail", async () => {
    await openAppliedStep(manifestWith(GPT, "xhigh"));

    await waitFor(() => expect(screen.getByLabelText("Model")).toHaveValue(GPT));
    expect(screen.getByLabelText("Effort")).toHaveValue("xhigh");
  });

  it("clearsTheEffort_whenTheNewModelDoesNotAcceptIt", async () => {
    await openAppliedStep(manifestWith(GPT, "xhigh"));
    await waitFor(() => expect(screen.getByLabelText("Effort")).toHaveValue("xhigh"));
    const expected = modelChangePatch(CLAUDE, "xhigh", PALETTE.model_catalog);

    await userEvent.selectOptions(screen.getByLabelText("Model"), CLAUDE);

    await waitFor(() => expect(screen.getByLabelText("Model")).toHaveValue(expected.model));
    expect(screen.getByLabelText("Effort")).toHaveValue(expected.effort);
    expect(expected.effort).toBe("");
  });

  it("keepsTheEffort_whenTheNewModelAcceptsIt", async () => {
    await openAppliedStep(manifestWith(CLAUDE, "none"));
    await waitFor(() => expect(screen.getByLabelText("Effort")).toHaveValue("none"));
    const expected = modelChangePatch(GPT, "none", PALETTE.model_catalog);

    await userEvent.selectOptions(screen.getByLabelText("Model"), GPT);

    await waitFor(() => expect(screen.getByLabelText("Model")).toHaveValue(expected.model));
    expect(screen.getByLabelText("Effort")).toHaveValue(expected.effort);
    expect(expected.effort).toBe("none");
  });

  it("savesTheNewModel_whenTheModelChangedAfterTheDraftWasApplied", async () => {
    vi.mocked(saveUserWorkflow).mockResolvedValue({ id: "wf-1" } as Awaited<
      ReturnType<typeof saveUserWorkflow>
    >);
    await openAppliedStep(manifestWith(GPT, "xhigh"));
    await waitFor(() => expect(screen.getByLabelText("Effort")).toHaveValue("xhigh"));

    await userEvent.selectOptions(screen.getByLabelText("Model"), CLAUDE);
    await waitFor(() => expect(screen.getByLabelText("Model")).toHaveValue(CLAUDE));
    await userEvent.click(screen.getByRole("button", { name: /Save workflow/i }));

    await waitFor(() => expect(saveUserWorkflow).toHaveBeenCalledTimes(1));
    const body = vi.mocked(saveUserWorkflow).mock.calls[0][2] as unknown as {
      manifest: { steps: Array<{ model?: { model?: string; effort?: string } }> };
    };
    expect(body.manifest.steps[0].model?.model).toBe(CLAUDE);
    // Haiku does not accept the draft's "xhigh", so the rail cleared it and it is not saved.
    expect(body.manifest.steps[0].model?.effort).toBeUndefined();
  });
});
