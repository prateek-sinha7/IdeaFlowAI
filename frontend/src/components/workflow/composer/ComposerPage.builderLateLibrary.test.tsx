/**
 * AI Workflow Builder: the agent library loading after a draft was saved
 * (task 20.3). The rebuild that fills in the built-in steps' definitions renames
 * them, and it must not make a saved composer report unsaved work.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, waitFor } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";
import type { AgentDef, WorkflowManifest, WorkflowType } from "@/types/index";
import type { ComposerBuilderBinding } from "@/types/workflowBuilder";
import { saveUserWorkflow } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getCapabilities: vi.fn().mockResolvedValue({ capabilities: [], model_catalog: [] }),
  saveUserWorkflow: vi.fn(),
  getWorkflowDetail: vi.fn().mockResolvedValue({ steps: [] }),
  getAgentPrompt: vi.fn().mockResolvedValue({ prompt_body: "", override: null, has_override: false }),
  saveAgentPromptOverride: vi.fn(),
  deleteAgentPromptOverride: vi.fn(),
}));

// The library the page sees. Tests swap `library.agents` and re-render, which is
// what the Redux library fetch does when it finishes late.
const library = vi.hoisted(() => ({ agents: [] as unknown[] }));
vi.mock("@/hooks/useAgentLibrary", () => ({
  useAgentLibrary: () => ({
    libraryAgents: library.agents,
    customAgents: [],
    allAgents: library.agents,
  }),
}));

import { ComposerPage } from "./ComposerPage";

const AGENT: AgentDef = {
  id: "domain-analyst",
  name: "Domain Discovery Agent",
  role: "Market & Persona Research",
  description: "Research market and personas",
  pipeline_type: "user_stories",
  order: 1,
  icon: "🔍",
  estimated_duration: 60,
  has_skill: false,
};

// A built-in step: without the library it is named by its id, with it by the
// library definition.
const DRAFT = {
  steps: [{ agent: AGENT.id }],
  name: "Research flow",
  description: "Researches a domain",
} as unknown as WorkflowManifest;

const mockSave = vi.mocked(saveUserWorkflow);

function page(builder: ComposerBuilderBinding, onUnsavedChange: (dirty: boolean) => void) {
  return (
    <ComposerPage
      workflowType={"custom" as WorkflowType}
      onBack={() => {}}
      onRun={vi.fn()}
      onUnsavedChange={onUnsavedChange}
      builder={builder}
    />
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  library.agents = [];
});

describe("ComposerPage builder draft — library loads after a save", () => {
  it("reports no unsaved work when the library renames the built-in steps of a saved draft", async () => {
    const user = userEvent.setup();
    const onUnsavedChange = vi.fn();
    const registerCanvasApi = vi.fn<NonNullable<ComposerBuilderBinding["registerCanvasApi"]>>();
    const builder: ComposerBuilderBinding = {
      draft: { revision: 1, manifest: DRAFT, targetTrust: "user" },
      turnRunning: false,
      panelOpen: false,
      aiButtonVisible: false,
      onAiButton: vi.fn(),
      registerCanvasApi,
      onSaved: vi.fn(),
    };
    mockSave.mockResolvedValue({ id: "wf-new" } as Awaited<ReturnType<typeof saveUserWorkflow>>);
    const view = renderWithProviders(page(builder, onUnsavedChange));
    await user.click(await screen.findByRole("button", { name: /Save workflow/i }));
    await waitFor(() => expect(builder.onSaved).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(onUnsavedChange).toHaveBeenLastCalledWith(false));

    const registeredBefore = registerCanvasApi.mock.calls.length;

    library.agents = [AGENT];
    view.rerender(page(builder, onUnsavedChange));

    // The rebuild renames the step, which re-registers the canvas getters.
    await waitFor(() => expect(registerCanvasApi.mock.calls.length).toBeGreaterThan(registeredBefore));
    const api = registerCanvasApi.mock.calls.at(-1)?.[0];
    expect(api?.isDirty()).toBe(false);
    await waitFor(() => expect(onUnsavedChange).toHaveBeenLastCalledWith(false));
  });
});
