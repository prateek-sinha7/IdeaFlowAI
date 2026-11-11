/**
 * Tools tab writers keep a step's connected-app grants (design 4.5, the ISS-912
 * class). `toggleToolPack` used to write `{...toolGrants, tool_sets}`, which
 * dropped `tools.connectors`; every writer now spreads the step's other keys.
 *
 * Boundaries replaced: the capabilities / prompt / workflow-catalog APIs and the
 * (Redux-backed) skills catalog, as in CanvasConfigRail.behavior.test.tsx.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, waitFor } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";
import type { CapabilitiesPalette } from "@/lib/api";
import type { AgentDef } from "@/types/index";
import type { StepSelection } from "../AgentsPopup";

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

import { CanvasConfigRail } from "./CanvasConfigRail";

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

const CONNECTORS = ["jira__search_issues", "github__get_issue"];

function renderRail(selection: StepSelection | undefined) {
  const onSelection = vi.fn();
  renderWithProviders(
    <CanvasConfigRail
      agent={WRITER}
      index={0}
      total={1}
      selection={selection}
      priorAgents={[]}
      onSelection={onSelection}
    />,
  );
  return onSelection;
}

async function openTools() {
  await userEvent.click(screen.getByRole("tab", { name: /tools/i }));
  await waitFor(() => expect(screen.getByRole("switch", { name: "Read files" })).toBeEnabled());
}

function lastTools(onSelection: ReturnType<typeof vi.fn>) {
  const [id, sel] = onSelection.mock.calls.at(-1) as [string, StepSelection | undefined];
  expect(id).toBe("writer");
  return sel?.tools;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGetCapabilities.mockResolvedValue(PALETTE);
});

describe("CanvasConfigRail - tools tab keeps connected-app grants", () => {
  it("keeps the connectors when a tool pack is switched on", async () => {
    const user = userEvent.setup();
    const onSelection = renderRail({ tools: { read_files: true, write_files: true, connectors: CONNECTORS } });
    await openTools();

    await user.click(screen.getByRole("switch", { name: "Playwright browser" }));

    expect(lastTools(onSelection)).toEqual({
      read_files: true,
      write_files: true,
      tool_sets: ["playwright"],
      connectors: CONNECTORS,
    });
  });

  it("keeps the connectors when the last tool pack is switched off", async () => {
    const user = userEvent.setup();
    const onSelection = renderRail({
      tools: { read_files: true, write_files: true, tool_sets: ["playwright"], connectors: CONNECTORS },
    });
    await openTools();

    await user.click(screen.getByRole("switch", { name: "Playwright browser" }));

    const tools = lastTools(onSelection);
    expect(tools).toEqual({ read_files: true, write_files: true, connectors: CONNECTORS });
    expect(tools).not.toHaveProperty("tool_sets");
  });

  it("keeps the connectors and the other pack when one of two packs is switched off", async () => {
    const user = userEvent.setup();
    const onSelection = renderRail({
      tools: {
        read_files: true,
        write_files: true,
        tool_sets: ["file_extract", "playwright"],
        connectors: CONNECTORS,
      },
    });
    await openTools();

    await user.click(screen.getByRole("switch", { name: "File extraction" }));

    expect(lastTools(onSelection)).toEqual({
      read_files: true,
      write_files: true,
      tool_sets: ["playwright"],
      connectors: CONNECTORS,
    });
  });

  it("keeps the connectors when a file grant is switched off", async () => {
    const user = userEvent.setup();
    const onSelection = renderRail({ tools: { read_files: true, write_files: true, connectors: CONNECTORS } });
    await openTools();

    await user.click(screen.getByRole("switch", { name: "Write files" }));

    expect(lastTools(onSelection)).toEqual({ read_files: true, write_files: false, connectors: CONNECTORS });
  });

  it("adds no connectors key when the step had none", async () => {
    const user = userEvent.setup();
    const onSelection = renderRail(undefined);
    await openTools();

    await user.click(screen.getByRole("switch", { name: "File extraction" }));

    const tools = lastTools(onSelection);
    expect(tools).toEqual({ read_files: true, write_files: true, tool_sets: ["file_extract"] });
    expect(tools).not.toHaveProperty("connectors");
  });
});
