/**
 * AI Workflow Builder gates in `ComposerPage` (task 20.4, design §3.10.7 items
 * 4, 5 and 7): the read-only canvas during a turn, the Save and Run once gates,
 * the Run once note at `db` trust, the AI header button and the switch to Canvas
 * view when the panel opens.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";
import type { ReactElement, ReactNode } from "react";
import type { WorkflowType, WorkflowManifest } from "@/types/index";
import type { ComposerBuilderBinding } from "@/types/workflowBuilder";

vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getCapabilities: vi.fn().mockResolvedValue({ capabilities: [], model_catalog: [] }),
  saveUserWorkflow: vi.fn(),
  getWorkflowDetail: vi.fn().mockResolvedValue({ steps: [] }),
  getAgentPrompt: vi.fn().mockResolvedValue({ prompt_body: "", override: null, has_override: false }),
  saveAgentPromptOverride: vi.fn(),
  deleteAgentPromptOverride: vi.fn(),
}));

import { ComposerPage } from "./ComposerPage";

const AGENT = {
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

const MANIFEST: WorkflowManifest = {
  steps: [{ agent: "custom-agent", instance_id: "draft-a", name: "Draft A", prompt: "Write it." }],
};

const UPDATING = "The builder is updating this workflow.";
const DB_NOTE = /An unsaved canvas runs at user trust/;

function binding(overrides: Partial<ComposerBuilderBinding> = {}): ComposerBuilderBinding {
  return {
    draft: null,
    turnRunning: false,
    panelOpen: false,
    aiButtonVisible: false,
    onAiButton: vi.fn(),
    registerCanvasApi: vi.fn(),
    onSaved: vi.fn(),
    ...overrides,
  };
}

function composer(
  builder: ComposerBuilderBinding | undefined,
  onRun = vi.fn(),
  builderPanel?: ReactNode,
): ReactElement {
  return (
    <ComposerPage
      workflowType={"custom" as WorkflowType}
      onBack={() => {}}
      initialAgentIds={[AGENT.id]}
      initialName="My flow"
      onRun={onRun}
      builder={builder}
      builderPanel={builderPanel}
    />
  );
}

function renderComposer(
  builder: ComposerBuilderBinding | undefined,
  onRun = vi.fn(),
  builderPanel?: ReactNode,
) {
  return renderWithProviders(composer(builder, onRun, builderPanel), {
    preloadedState: {
      agents: {
        agents: [AGENT],
        totalCount: 1,
        pipelines: {},
        status: "succeeded",
        error: null,
      },
    },
  });
}

/** Type a brief long enough for Run once, in whichever view shows a brief box. */
async function typeBrief(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: /^Simple$/ }));
  await user.type(await screen.findByPlaceholderText(/Describe what you want/i), "Build a thing");
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ComposerPage builder gates — running turn", () => {
  it("makes the body inert, disables Save and Run once, and shows the banner", () => {
    renderComposer(binding({ turnRunning: true }));

    expect(screen.getByTestId("canvas-view").closest("[inert]")).not.toBeNull();
    expect(screen.getByRole("button", { name: /Save workflow/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Run once/i })).toBeDisabled();
    expect(screen.getByText(UPDATING)).toBeInTheDocument();
  });

  it("leaves the canvas editable and shows no banner when no turn runs", () => {
    renderComposer(binding({ turnRunning: false }));

    expect(screen.getByTestId("canvas-view").closest("[inert]")).toBeNull();
    expect(screen.getByRole("button", { name: /Save workflow/i })).toBeEnabled();
    expect(screen.queryByText(UPDATING)).not.toBeInTheDocument();
  });

  it("changes nothing without a builder binding", () => {
    renderComposer(undefined);

    expect(screen.getByTestId("canvas-view").closest("[inert]")).toBeNull();
    expect(screen.getByRole("button", { name: /Save workflow/i })).toBeEnabled();
    expect(screen.queryByRole("button", { name: /Build with AI/i })).not.toBeInTheDocument();
  });

  it("does not launch from the Cmd/Ctrl+Enter shortcut while a turn runs", async () => {
    const user = userEvent.setup();
    const onRun = vi.fn();
    const { rerender } = renderComposer(binding(), onRun);
    await typeBrief(user);

    rerender(composer(binding({ turnRunning: true }), onRun));
    await user.type(screen.getByPlaceholderText(/Describe what you want/i), "{Control>}{Enter}{/Control}");

    expect(onRun).not.toHaveBeenCalled();
  });
});

describe("ComposerPage builder gates — Run once at db trust", () => {
  it("disables Run once with the note while a db draft is unsaved", async () => {
    const user = userEvent.setup();
    renderComposer(
      binding({ draft: { revision: 1, manifest: MANIFEST, targetTrust: "db" } }),
    );
    await typeBrief(user);

    expect(screen.getByRole("button", { name: /Run once/i })).toBeDisabled();
    expect(screen.getByText(DB_NOTE)).toBeInTheDocument();
  });

  it("keeps Run once enabled for a user-trust draft", async () => {
    const user = userEvent.setup();
    renderComposer(
      binding({ draft: { revision: 1, manifest: MANIFEST, targetTrust: "user" } }),
    );
    await typeBrief(user);

    expect(screen.getByRole("button", { name: /Run once/i })).toBeEnabled();
    expect(screen.queryByText(DB_NOTE)).not.toBeInTheDocument();
  });
});

describe("ComposerPage builder gates — header button and panel", () => {
  it("renders the AI button only when aiButtonVisible, and calls onAiButton", async () => {
    const user = userEvent.setup();
    const onAiButton = vi.fn();
    const { rerender } = renderComposer(binding({ aiButtonVisible: false, onAiButton }));
    expect(screen.queryByRole("button", { name: /Build with AI/i })).not.toBeInTheDocument();

    rerender(composer(binding({ aiButtonVisible: true, onAiButton })));
    await user.click(screen.getByRole("button", { name: /Build with AI/i }));

    expect(onAiButton).toHaveBeenCalledTimes(1);
  });

  it("keeps the AI button usable while a turn runs", () => {
    renderComposer(binding({ aiButtonVisible: true, turnRunning: true }));

    expect(screen.getByRole("button", { name: /Build with AI/i })).toBeEnabled();
  });

  it("reports on the AI button whether the panel is open, and which element it controls", () => {
    const { rerender } = renderComposer(
      binding({ aiButtonVisible: true, panelOpen: false, panelId: "builder-panel" }),
    );
    const button = screen.getByRole("button", { name: /Build with AI/i });
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(button).not.toHaveAttribute("aria-controls");
    expect(button).not.toHaveAttribute("aria-haspopup");

    rerender(composer(binding({ aiButtonVisible: true, panelOpen: true, panelId: "builder-panel" })));
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(button).toHaveAttribute("aria-controls", "builder-panel");
  });

  it("places the builder panel under the header, left of the canvas and outside the inert body", () => {
    renderComposer(
      binding({ turnRunning: true, panelOpen: true }),
      vi.fn(),
      <aside aria-label="AI workflow builder">
        <button type="button">Stop</button>
      </aside>,
    );

    const panel = screen.getByRole("complementary", { name: "AI workflow builder" });
    const canvas = screen.getByTestId("canvas-view");
    expect(canvas.closest("[inert]")).not.toBeNull();
    expect(panel.closest("[inert]")).toBeNull();
    expect(screen.getByRole("button", { name: "Stop" })).toBeEnabled();
    // Header first, then the panel, then the canvas.
    const name = screen.getByRole("textbox", { name: "Workflow name" });
    expect(name.compareDocumentPosition(panel) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(panel.compareDocumentPosition(canvas) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("switches to Canvas view when the panel opens, and Simple view still works after", async () => {
    const user = userEvent.setup();
    const { rerender } = renderComposer(binding({ panelOpen: false }));
    await user.click(screen.getByRole("button", { name: /^Simple$/ }));
    expect(screen.queryByTestId("canvas-view")).not.toBeInTheDocument();

    rerender(composer(binding({ panelOpen: true })));
    expect(await screen.findByTestId("canvas-view")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^Simple$/ }));
    expect(screen.queryByTestId("canvas-view")).not.toBeInTheDocument();
  });
});
