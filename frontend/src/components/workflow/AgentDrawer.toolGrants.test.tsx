/**
 * ISS-378 (QA-KB-016) — the Library / Add-agent drawer's Config tab
 * (ConfigLeversFlat) renders no Tool grants rows. Tests were `it.fails` until verified:
 * green while the defect exists; once the fix lands each one passes, vitest
 * flags the `it.fails` as failing, and the verifier removes the `.fails`.
 * ISS-912 is covered on the same surface: a grant toggle must keep tool_sets.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderWithProviders, screen } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";

vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getAgentPrompt: vi.fn().mockResolvedValue({
    agent_id: "requirements-analyst",
    prompt_body: "",
    override: null,
    has_override: false,
  }),
  saveAgentPromptOverride: vi.fn(),
  deleteAgentPromptOverride: vi.fn(),
  getCapabilities: vi.fn().mockResolvedValue({ capabilities: [], model_catalog: [] }),
}));

import { AgentCapabilitiesModal, type SelectionsMap } from "./AgentsPopup";
import { SkillsHooksProvider } from "@/context/SkillsHooksContext";
import type { AgentDef } from "@/types/index";

const AGENT = {
  id: "requirements-analyst",
  name: "Requirements Analyst",
  description: "Analyzes requirements.",
  role: "analyst",
  pipeline_type: "prototype",
  estimated_duration: 30,
  order: 1,
  has_skill: true,
} as AgentDef;

const onSelectionsChange = vi.fn();

beforeEach(() => vi.clearAllMocks());

async function openConfig(initialSelections?: SelectionsMap) {
  renderWithProviders(
    <SkillsHooksProvider>
      <AgentCapabilitiesModal
        agent={AGENT}
        agentIndex={0}
        onClose={vi.fn()}
        onSelectionsChange={onSelectionsChange}
        initialSelections={initialSelections}
      />
    </SkillsHooksProvider>,
  );
  await userEvent.click(screen.getByRole("tab", { name: /config/i }));
  await screen.findByLabelText("Retry for Requirements Analyst");
}

const write = () =>
  screen.getByRole("checkbox", { name: "Write files for Requirements Analyst" });

describe("ISS-378 — Config tab Tool grants", () => {
  it("ISS-378: Read files and Write files are checked by default, Execute commands disabled", async () => {
    await openConfig();
    expect(screen.getByRole("checkbox", { name: "Read files for Requirements Analyst" })).toBeChecked();
    expect(write()).toBeChecked();
    const exec = screen.getByRole("checkbox", { name: "Execute commands for Requirements Analyst" });
    expect(exec).toBeDisabled();
    expect(exec).not.toBeChecked();
  });

  it("ISS-378: unticking Write files reports the grant through onSelectionsChange", async () => {
    await openConfig();
    await userEvent.click(write());
    expect(onSelectionsChange).toHaveBeenLastCalledWith({
      "requirements-analyst": { tools: { read_files: true, write_files: false } },
    });
  });

  it("ISS-378: a stored write_files=false renders unticked", async () => {
    await openConfig({ "requirements-analyst": { tools: { write_files: false } } });
    expect(write()).not.toBeChecked();
  });

  it("ISS-912: toggling a grant keeps the step's tool_sets", async () => {
    await openConfig({
      "requirements-analyst": { tools: { read_files: true, write_files: true, tool_sets: ["playwright"] } },
    });
    await userEvent.click(write());
    expect(onSelectionsChange).toHaveBeenLastCalledWith({
      "requirements-analyst": {
        tools: { read_files: true, write_files: false, tool_sets: ["playwright"] },
      },
    });
  });
});
