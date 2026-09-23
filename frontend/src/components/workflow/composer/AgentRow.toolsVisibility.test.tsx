/**
 * ISS-274 — Simple view's per-agent "Configure →" panel has no Tools
 * section, hiding an existing tool-grant override set in Canvas view.
 * `AgentRow` opens `AdvancedExpander` (Validator/Gate/Model/Retry only) —
 * never `CanvasConfigRail`, the sole place the three tool-grant switches
 * (Read files / Write files / Execute commands) are rendered. Mirrors the
 * fixtures/mocking idiom of `AgentRow.test.tsx`.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import type { ComponentProps } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { CapabilitiesPalette } from "@/lib/api";
import type { AgentDef, WorkflowType } from "@/types/index";

const mockGetCapabilities = vi.fn();
vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getCapabilities: (t: string) => mockGetCapabilities(t),
  getAgentPrompt: vi
    .fn()
    .mockResolvedValue({ prompt_body: "", override: null, has_override: false }),
  saveAgentPromptOverride: vi.fn(),
  deleteAgentPromptOverride: vi.fn(),
}));

vi.mock("@/hooks/useSkillsCatalog", () => ({
  useSkillsCatalog: () => ({ skills: [], categories: [] }),
}));

import { AgentRow } from "./AgentRow";

const PALETTE: CapabilitiesPalette = {
  capabilities: [
    { kind: "validator", name: "code_test", user_allowed: true, description: "Runs the tests.", security_gated: false, config_schema: {} },
    { kind: "gate", name: "approval", user_allowed: true, description: "Human approval gate.", security_gated: false, config_schema: {} },
  ],
  model_catalog: [
    { id: "model-opus", label: "Opus 4.5", description: "Most capable.", tier: "powerful", cost_class: "premium", provider: "anthropic", context_window: 200000, user_allowed: true },
  ],
};

function mkAgent(over: Partial<AgentDef> & { id: string; name: string }): AgentDef {
  return {
    role: "Does a thing",
    description: "A capable agent.",
    pipeline_type: "custom",
    order: 1,
    icon: "",
    estimated_duration: 120,
    has_skill: false,
    ...over,
  } as AgentDef;
}

const PLAN = mkAgent({ id: "prototype-plan", name: "Plan" });

function renderRow(props: Partial<ComponentProps<typeof AgentRow>> = {}) {
  const onSelection = vi.fn();
  const utils = render(
    <AgentRow
      agent={PLAN}
      index={0}
      total={1}
      pipelineType={"prototype" as WorkflowType}
      selection={undefined}
      onSelection={onSelection}
      onMoveUp={() => {}}
      onMoveDown={() => {}}
      onRemove={() => {}}
      {...props}
    />,
  );
  return { ...utils, onSelection };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGetCapabilities.mockResolvedValue(PALETTE);
});

describe("AgentRow — Simple view Tools visibility", () => {
  it("ISS-274: shows a Tools override indicator when the agent carries a non-default tool grant", async () => {
    // A Canvas-set restriction: Write files disabled. This is real, persisted
    // StepSelection state — the same SelectionsMap Canvas and Simple share.
    const restricted = {
      tools: { read_files: true, write_files: false, execute_commands: false },
    } as unknown as ComponentProps<typeof AgentRow>["selection"];
    renderRow({ selection: restricted });

    // Expected: the Overrides row surfaces a Tools chip alongside
    // Validator/Gate/Retry/Skills, just as it does for those other levers.
    expect(screen.getByRole("button", { name: "Tools" })).toBeInTheDocument();
  });

  it("ISS-274: exposes the Tools grants (Read/Write/Execute) inside the Configure panel", async () => {
    renderRow();
    await userEvent.click(screen.getByRole("button", { name: /model for plan/i }));

    // Expected: the same three switches Canvas view's CanvasConfigRail
    // renders (Read files / Write files / Execute commands) are reachable
    // from Simple view's Configure panel too.
    expect(await screen.findByText(/read files/i)).toBeInTheDocument();
    expect(screen.getByText(/write files/i)).toBeInTheDocument();
    expect(screen.getByText(/execute commands/i)).toBeInTheDocument();
  });
});
