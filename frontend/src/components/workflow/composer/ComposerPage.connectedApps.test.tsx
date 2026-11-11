/**
 * ComposerPage decides where connected apps are offered (design 4.4, 5.5 layer 5)
 * and shows the server's refusal text when a save is rejected (`detail.error`
 * of the 422 `connector_grants_not_allowed` envelope).
 *
 * Boundaries replaced: lib/api (token, capabilities, save) and the Connectors
 * REST client. ComposerPage, CanvasView, the rail and the section run for real.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, waitFor } from "@/test/renderWithProviders";
import { within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { WorkflowType } from "@/types/index";
import { buildConnectedConnector } from "@/test/connectorFixtures";

const mockSaveUserWorkflow = vi.fn();
vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getCapabilities: vi.fn().mockResolvedValue({ capabilities: [], model_catalog: [] }),
  saveUserWorkflow: (...a: unknown[]) => mockSaveUserWorkflow(...a),
  getWorkflowDetail: vi.fn().mockResolvedValue({ steps: [] }),
  getAgentPrompt: vi.fn().mockResolvedValue({ prompt_body: "", override: null, has_override: false }),
  saveAgentPromptOverride: vi.fn(),
  deleteAgentPromptOverride: vi.fn(),
}));
const mockConnectorsList = vi.fn();
const mockConnectorTools = vi.fn();
vi.mock("@/store/api/connectors", () => ({
  connectorsApi: {
    list: (...a: unknown[]) => mockConnectorsList(...a),
    tools: (...a: unknown[]) => mockConnectorTools(...a),
  },
}));

import { resetConnectedAppsCache } from "@/hooks/useConnectedApps";
import { ComposerPage } from "./ComposerPage";
import { NOT_AVAILABLE_NOTE } from "./ConnectedAppsSection";
import { SkillsHooksProvider } from "@/context/SkillsHooksContext";

const AGENT = {
  id: "domain-analyst",
  name: "Domain Discovery Agent",
  role: "Market & Persona Research",
  description: "Research market and personas",
  pipeline_type: "user_stories",
  order: 1,
  icon: "",
  estimated_duration: 60,
  has_skill: false,
};

function renderComposer(props: Record<string, unknown> = {}) {
  return renderWithProviders(
    <SkillsHooksProvider>
      <ComposerPage
        workflowType={"user_stories" as WorkflowType}
        onBack={() => {}}
        initialAgentIds={[AGENT.id]}
        {...props}
      />
    </SkillsHooksProvider>,
    {
      preloadedState: {
        agents: { agents: [AGENT], totalCount: 1, pipelines: {}, status: "succeeded", error: null },
      },
    },
  );
}

async function openToolsTab() {
  const user = userEvent.setup();
  await user.click(await screen.findByTestId(`canvas-node-${AGENT.id}`));
  await user.click(await screen.findByRole("tab", { name: /tools/i }));
}

beforeEach(() => {
  vi.clearAllMocks();
  resetConnectedAppsCache();
  mockConnectorsList.mockResolvedValue({
    connectors: [buildConnectedConnector({ key: "github", display_name: "GitHub" })],
  });
  mockConnectorTools.mockResolvedValue({ connector: "github", status: "connected", tools: [], listed_at: null });
});

describe("ComposerPage - where connected apps are offered", () => {
  it("offers connected apps, with no note, on the user's own workflow", async () => {
    renderComposer();
    await openToolsTab();

    expect(await screen.findByRole("group", { name: /GitHub/ })).toBeInTheDocument();
    expect(screen.queryByText(NOT_AVAILABLE_NOTE)).not.toBeInTheDocument();
  });

  it("offers connected apps on a saved custom workflow", async () => {
    renderComposer({ initialUserWorkflowId: "wf-1", initialName: "Mine" });
    await openToolsTab();

    expect(await screen.findByRole("group", { name: /GitHub/ })).toBeInTheDocument();
    expect(screen.queryByText(NOT_AVAILABLE_NOTE)).not.toBeInTheDocument();
  });

  it("shows the save-a-copy note on a built-in canvas", async () => {
    renderComposer({ builtinCanvasType: "user_stories" });
    await openToolsTab();

    expect(await screen.findByText(NOT_AVAILABLE_NOTE)).toBeInTheDocument();
  });

  it("shows the save-a-copy note on an override row", async () => {
    renderComposer({
      initialUserWorkflowId: "wf-override",
      initialName: "My PPT",
      overridesPipelineType: "ppt",
    });
    await openToolsTab();

    expect(await screen.findByText(NOT_AVAILABLE_NOTE)).toBeInTheDocument();
  });

  it("treats a null override marker as an ordinary workflow", async () => {
    renderComposer({ initialUserWorkflowId: "wf-1", overridesPipelineType: null });
    await openToolsTab();

    expect(await screen.findByRole("group", { name: /GitHub/ })).toBeInTheDocument();
    expect(screen.queryByText(NOT_AVAILABLE_NOTE)).not.toBeInTheDocument();
  });
});

describe("ComposerPage - save refusal text", () => {
  it("shows detail.error, not the raw JSON, when the server refuses connector grants", async () => {
    const text = "Connected apps work in your own workflows. Save a copy to use them.";
    const envelope = { error: text, code: "connector_grants_not_allowed", recoverable: true };
    mockSaveUserWorkflow.mockRejectedValue(
      Object.assign(new Error(JSON.stringify(envelope)), { status: 422, detail: envelope }),
    );
    renderComposer({ initialName: "Flow" });

    await userEvent.click(screen.getByRole("button", { name: /Save workflow/i }));

    expect(await screen.findByText(text)).toBeInTheDocument();
    expect(screen.queryByText(/connector_grants_not_allowed/)).not.toBeInTheDocument();
  });

  it("still shows the message of an ordinary save error", async () => {
    mockSaveUserWorkflow.mockRejectedValue(new Error("A workflow with this name already exists."));
    renderComposer({ initialName: "Flow" });

    await userEvent.click(screen.getByRole("button", { name: /Save workflow/i }));

    await waitFor(() =>
      expect(screen.getByText("A workflow with this name already exists.")).toBeInTheDocument(),
    );
  });
});

const GITHUB_TOOL = "github__list_issues";

describe("ComposerPage - a plain composition with a connected app switched on", () => {
  beforeEach(() => {
    mockConnectorTools.mockResolvedValue({
      connector: "github",
      status: "connected",
      tools: [
        {
          name: GITHUB_TOOL,
          source_name: "list_issues",
          title: "List issues",
          description: "List repository issues.",
          write_capable: false,
        },
      ],
      listed_at: null,
    });
  });

  /** Switch on the GitHub tool of the plain library-agent step. Returns the user for later steps. */
  async function switchOnListIssues() {
    const user = userEvent.setup();
    await openToolsTab();
    const github = await screen.findByRole("group", { name: /GitHub/ });
    await user.click(within(github).getByRole("button", { name: "Show GitHub tools" }));
    await user.click(await within(github).findByRole("switch", { name: "List issues" }));
    return user;
  }

  it("saves the composition as the full manifest, not the flat selections", async () => {
    mockSaveUserWorkflow.mockResolvedValue({ id: "wf-1", agent_ids: [AGENT.id] });
    renderComposer({ initialName: "Flow" });
    await switchOnListIssues();

    await userEvent.click(screen.getByRole("button", { name: /Save workflow/i }));

    await waitFor(() => expect(mockSaveUserWorkflow).toHaveBeenCalledTimes(1));
    const body = mockSaveUserWorkflow.mock.calls[0][2] as {
      selections?: unknown;
      manifest?: { steps: Array<{ agent: string; tools?: { connectors?: string[] } }> };
    };
    expect(body).not.toHaveProperty("selections");
    expect(body.manifest?.steps.find((step) => step.agent === AGENT.id)?.tools?.connectors).toEqual([GITHUB_TOOL]);
  });

  it("runs once with the inline manifest when the composition is unsaved", async () => {
    const onRun = vi.fn().mockResolvedValue("run-1");
    renderComposer({ onRun, initialName: "Flow" });
    const user = await switchOnListIssues();
    await user.click(screen.getByRole("button", { name: /^Simple$/ }));
    await user.type(screen.getByRole("textbox", { name: "Brief description" }), "Summarise open issues");

    await user.click(screen.getByRole("button", { name: "Run once" }));

    await waitFor(() => expect(onRun).toHaveBeenCalledTimes(1));
    const extra = onRun.mock.calls[0][3] as {
      user_workflow_id?: string;
      manifest?: { steps: Array<{ agent: string; tools?: { connectors?: string[] } }> };
    };
    // Unsaved, so the inline manifest carries the steps. Flat selections may ride
    // along for the overlay, as they do for every manifest launch.
    expect(extra.user_workflow_id).toBeUndefined();
    expect(extra.manifest?.steps.find((step) => step.agent === AGENT.id)?.tools?.connectors).toEqual([GITHUB_TOOL]);
  });
});
