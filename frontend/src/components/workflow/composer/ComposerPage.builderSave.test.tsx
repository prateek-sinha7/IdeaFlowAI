/**
 * AI Workflow Builder Save in `ComposerPage` (task 20.5, design §3.10.7 item 6
 * and §3.10.8; Req 10.1 to 10.11): a draft is the save source, an unlinked
 * session pre-fills the Save fields from the draft, a linked row with a
 * non-custom base is saved as a new row, a 409 on "Save as new" moves the name
 * to the next free copy, and the session is reported to the host after a save.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, waitFor } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";
import type { WorkflowType, WorkflowManifest } from "@/types/index";
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

// A draft carries top-level keys the canvas does not model (`name`, `description`,
// `limits`). They reach Save through the passthrough source. `WorkflowManifest`
// does not type `name` or `description`, so the literal is cast.
const DRAFT = {
  steps: [{ agent: "custom-agent", instance_id: "draft-a", name: "Draft A", prompt: "Write it." }],
  name: "Blog pipeline",
  description: "Writes posts",
  limits: { max_turns: 5 },
} as unknown as WorkflowManifest;

const CONFLICT = "A workflow with this name already exists.";

function conflict(): Error {
  return Object.assign(new Error(CONFLICT), { status: 409 });
}

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

interface Seed {
  initialName?: string;
  initialUserWorkflowId?: string;
  builder: ComposerBuilderBinding;
}

function renderComposer({ initialName, initialUserWorkflowId, builder }: Seed) {
  return renderWithProviders(
    <ComposerPage
      workflowType={"custom" as WorkflowType}
      onBack={() => {}}
      initialAgentIds={[AGENT.id]}
      initialName={initialName}
      initialUserWorkflowId={initialUserWorkflowId}
      onRun={vi.fn()}
      builder={builder}
    />,
    {
      preloadedState: {
        agents: {
          agents: [AGENT],
          totalCount: 1,
          pipelines: {},
          status: "succeeded",
          error: null,
        },
      },
    },
  );
}

const mockSave = vi.mocked(saveUserWorkflow);

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ComposerPage builder Save — draft as the source", () => {
  it("pre-fills the name and description from the draft, then saves its manifest and compiled ids", async () => {
    const user = userEvent.setup();
    const builder = binding({ draft: { revision: 1, manifest: DRAFT, targetTrust: "user" } });
    mockSave.mockResolvedValue({ id: "wf-new" } as Awaited<ReturnType<typeof saveUserWorkflow>>);
    renderComposer({ builder });

    expect(await screen.findByDisplayValue("Blog pipeline")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Save workflow/i }));

    await waitFor(() => expect(mockSave).toHaveBeenCalledTimes(1));
    const [token, targetId, body] = mockSave.mock.calls[0];
    expect(token).toBe("test-token");
    expect(targetId).toBeUndefined();
    expect(body).toMatchObject({
      name: "Blog pipeline",
      description: "Writes posts",
      base_pipeline_type: "custom",
      agent_ids: ["custom-agent:draft-a"],
      manifest: { limits: { max_turns: 5 }, steps: [expect.objectContaining({ agent: "custom-agent" })] },
    });
    expect(builder.onSaved).toHaveBeenCalledWith({ id: "wf-new", baseIsCustom: true });
  });

  it("keeps the name typed by the user when the draft has neither name nor id", async () => {
    const user = userEvent.setup();
    const nameless = { steps: DRAFT.steps } as WorkflowManifest;
    renderComposer({
      initialName: "My flow",
      builder: binding({ draft: { revision: 1, manifest: nameless, targetTrust: "user" } }),
    });

    await user.click(screen.getByRole("button", { name: /Save workflow/i }));

    await waitFor(() => expect(mockSave).toHaveBeenCalledTimes(1));
    expect(mockSave.mock.calls[0][2]).toMatchObject({ name: "My flow" });
  });
});

describe("ComposerPage builder Save — linked rows", () => {
  it("shows only Save as new for a non-custom base and never sends the row id", async () => {
    const user = userEvent.setup();
    const builder = binding({ linkedBaseIsCustom: false });
    mockSave.mockResolvedValue({ id: "wf-copy" } as Awaited<ReturnType<typeof saveUserWorkflow>>);
    renderComposer({ initialName: "Foo", initialUserWorkflowId: "wf-proto", builder });

    expect(screen.queryByRole("button", { name: /Save workflow/i })).not.toBeInTheDocument();
    expect(screen.getByDisplayValue("Foo (AI)")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save as new" }));

    await waitFor(() => expect(mockSave).toHaveBeenCalledTimes(1));
    expect(mockSave.mock.calls[0][1]).toBeUndefined();
    expect(mockSave.mock.calls[0][2]).toMatchObject({ name: "Foo (AI)", base_pipeline_type: "custom" });
    expect(builder.onSaved).toHaveBeenCalledWith({ id: "wf-copy", baseIsCustom: true });
  });

  it("moves the pre-filled name to the next copy name after each 409 and keeps the error", async () => {
    const user = userEvent.setup();
    mockSave.mockRejectedValueOnce(conflict()).mockRejectedValueOnce(conflict());
    renderComposer({
      initialName: "Foo",
      initialUserWorkflowId: "wf-proto",
      builder: binding({ linkedBaseIsCustom: false }),
    });

    await user.click(screen.getByRole("button", { name: "Save as new" }));
    expect(await screen.findByText(CONFLICT)).toBeInTheDocument();
    expect(screen.getByDisplayValue("Foo (AI) 2")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Save as new" }));
    await waitFor(() => expect(screen.getByDisplayValue("Foo (AI) 3")).toBeInTheDocument());
    expect(mockSave).toHaveBeenCalledTimes(2);
    expect(mockSave.mock.calls.every(([, id]) => id === undefined)).toBe(true);
  });

  it("leaves a name the user typed alone after a 409 on Save as new", async () => {
    const user = userEvent.setup();
    mockSave.mockRejectedValueOnce(conflict());
    renderComposer({
      initialName: "Foo",
      initialUserWorkflowId: "wf-proto",
      builder: binding({ linkedBaseIsCustom: false }),
    });

    const field = screen.getByDisplayValue("Foo (AI)");
    await user.clear(field);
    await user.type(field, "Bar");
    await user.click(screen.getByRole("button", { name: "Save as new" }));

    expect(await screen.findByText(CONFLICT)).toBeInTheDocument();
    expect(screen.getByDisplayValue("Bar")).toBeInTheDocument();
  });

  it("offers Save workflow and Save as new in one Save menu for a linked custom row", async () => {
    const user = userEvent.setup();
    const builder = binding({ linkedBaseIsCustom: true });
    mockSave.mockResolvedValue({ id: "wf-1" } as Awaited<ReturnType<typeof saveUserWorkflow>>);
    renderComposer({ initialName: "Foo", initialUserWorkflowId: "wf-1", builder });

    expect(screen.queryByRole("button", { name: "Save as new" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Save workflow/i }));
    expect(screen.getByRole("menuitem", { name: "Save workflow" })).toBeEnabled();
    expect(screen.getByRole("menuitem", { name: "Save as new" })).toBeEnabled();

    await user.click(screen.getByRole("menuitem", { name: "Save workflow" }));

    await waitFor(() => expect(mockSave).toHaveBeenCalledTimes(1));
    expect(mockSave.mock.calls[0][1]).toBe("wf-1");
    expect(builder.onSaved).toHaveBeenCalledWith({ id: "wf-1", baseIsCustom: true });
  });

  it("creates a new row for Save as new from the Save menu of a linked custom row", async () => {
    const user = userEvent.setup();
    mockSave.mockResolvedValue({ id: "wf-2" } as Awaited<ReturnType<typeof saveUserWorkflow>>);
    renderComposer({ initialName: "Foo", initialUserWorkflowId: "wf-1", builder: binding() });

    await user.click(screen.getByRole("button", { name: /Save workflow/i }));
    await user.click(screen.getByRole("menuitem", { name: "Save as new" }));

    await waitFor(() => expect(mockSave).toHaveBeenCalledTimes(1));
    expect(mockSave.mock.calls[0][1]).toBeUndefined();
  });

  it("keeps the link and skips the host when a 422 comes back", async () => {
    const user = userEvent.setup();
    const builder = binding({ linkedBaseIsCustom: true });
    mockSave.mockRejectedValueOnce(Object.assign(new Error("The manifest does not compile."), { status: 422 }));
    renderComposer({ initialName: "Foo", initialUserWorkflowId: "wf-1", builder });

    await user.click(screen.getByRole("button", { name: /Save workflow/i }));
    await user.click(screen.getByRole("menuitem", { name: "Save workflow" }));

    expect(await screen.findByText("The manifest does not compile.")).toBeInTheDocument();
    expect(builder.onSaved).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /Save workflow/i })).toBeEnabled();
  });
});
