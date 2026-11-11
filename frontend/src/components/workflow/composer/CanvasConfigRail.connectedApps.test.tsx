/**
 * The rail's Tools tab hosts the Connected Apps block (design 4.4, Q11): shown
 * only when the host says whether the canvas can use connected apps, written
 * through the shared lever writer so a step's other grants survive.
 *
 * Boundaries replaced: the capabilities / prompt / workflow-catalog APIs, the
 * skills catalog (as in the sibling rail tests) and the Connectors REST client.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, waitFor, within } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";
import type { CapabilitiesPalette } from "@/lib/api";
import type { AgentDef } from "@/types/index";
import type { StepSelection } from "../AgentsPopup";
import { buildConnectedConnector } from "@/test/connectorFixtures";

const mockGetCapabilities = vi.fn();
vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getCapabilities: (t: string) => mockGetCapabilities(t),
  getWorkflowDefinitions: vi.fn().mockResolvedValue([]),
  getAgentPrompt: vi.fn().mockResolvedValue({ prompt_body: "", override: null, has_override: false }),
  saveAgentPromptOverride: vi.fn(),
  deleteAgentPromptOverride: vi.fn(),
}));
vi.mock("@/hooks/useSkillsCatalog", () => ({
  useSkillsCatalog: () => ({ skills: [], categories: [] }),
}));
const mockConnectorsList = vi.fn();
const mockConnectorsTools = vi.fn();
vi.mock("@/store/api/connectors", () => ({
  connectorsApi: {
    list: (...a: unknown[]) => mockConnectorsList(...a),
    tools: (...a: unknown[]) => mockConnectorsTools(...a),
  },
}));

import { resetConnectedAppsCache } from "@/hooks/useConnectedApps";
import { CanvasConfigRail } from "./CanvasConfigRail";
import type { ConnectedAppsAvailability } from "./ConnectedAppsSection";

const PALETTE: CapabilitiesPalette = { capabilities: [], model_catalog: [] };

const WRITER = {
  id: "writer",
  name: "Writer",
  role: "Writes drafts",
  description: "A capable agent.",
  pipeline_type: "custom",
  order: 1,
  icon: "",
  estimated_duration: 120,
  has_skill: false,
} as AgentDef;

function renderRail(selection: StepSelection | undefined, availability?: ConnectedAppsAvailability) {
  const onSelection = vi.fn();
  renderWithProviders(
    <CanvasConfigRail
      agent={WRITER}
      index={0}
      total={1}
      selection={selection}
      priorAgents={[]}
      onSelection={onSelection}
      connectedAppsAvailability={availability}
    />,
  );
  return onSelection;
}

async function openTools() {
  await userEvent.click(screen.getByRole("tab", { name: /tools/i }));
  await waitFor(() => expect(screen.getByRole("switch", { name: "Read files" })).toBeEnabled());
}

beforeEach(() => {
  vi.clearAllMocks();
  resetConnectedAppsCache();
  mockGetCapabilities.mockResolvedValue(PALETTE);
  mockConnectorsList.mockResolvedValue({
    connectors: [buildConnectedConnector({ key: "github", display_name: "GitHub" })],
  });
  mockConnectorsTools.mockResolvedValue({
    connector: "github",
    status: "connected",
    listed_at: null,
    tools: [
      {
        name: "github__get_issue",
        source_name: "get_issue",
        title: "Get issue",
        description: "Read one issue.",
        write_capable: false,
      },
    ],
  });
});

describe("CanvasConfigRail - Connected Apps in the Tools tab", () => {
  it("offers no Connected Apps and makes no connectors request when the host passes no availability", async () => {
    renderRail(undefined);
    await openTools();

    expect(screen.queryByRole("region", { name: "Connected apps" })).not.toBeInTheDocument();
    expect(mockConnectorsList).not.toHaveBeenCalled();
  });

  it("does not show Connected Apps on the other tabs", async () => {
    renderRail(undefined, "available");

    expect(screen.queryByRole("region", { name: "Connected apps" })).not.toBeInTheDocument();
    expect(mockConnectorsList).not.toHaveBeenCalled();
  });

  it("shows Connected Apps below the tool packs once the Tools tab is open", async () => {
    renderRail(undefined, "available");
    await openTools();

    const region = await screen.findByRole("region", { name: "Connected apps" });

    expect(within(region).getByRole("group", { name: /GitHub/ })).toBeInTheDocument();
    const pack = screen.getByRole("switch", { name: "Playwright browser" });
    expect(pack.compareDocumentPosition(region) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("reports a turned-on tool through onSelection and keeps the step's packs and file grants", async () => {
    const user = userEvent.setup();
    const onSelection = renderRail(
      { tools: { read_files: true, write_files: false, tool_sets: ["playwright"] } },
      "available",
    );
    await openTools();
    const region = await screen.findByRole("region", { name: "Connected apps" });
    const group = await within(region).findByRole("group", { name: /GitHub/ });
    await user.click(within(group).getByRole("button", { name: "Show GitHub tools" }));

    await user.click(await within(group).findByRole("switch", { name: "Get issue" }));

    const [id, sel] = onSelection.mock.calls.at(-1) as [string, StepSelection];
    expect(id).toBe("writer");
    expect(sel.tools).toEqual({
      read_files: true,
      write_files: false,
      tool_sets: ["playwright"],
      connectors: ["github__get_issue"],
    });
  });

  it("disables the switches and explains why on a built-in canvas", async () => {
    const user = userEvent.setup();
    renderRail(undefined, "builtin");
    await openTools();
    const region = await screen.findByRole("region", { name: "Connected apps" });
    const group = await within(region).findByRole("group", { name: /GitHub/ });
    await user.click(within(group).getByRole("button", { name: "Show GitHub tools" }));

    expect(within(region).getByText(/Save a copy to use them/)).toBeInTheDocument();
    expect(await within(group).findByRole("switch", { name: "Get issue" })).toBeDisabled();
  });
});
