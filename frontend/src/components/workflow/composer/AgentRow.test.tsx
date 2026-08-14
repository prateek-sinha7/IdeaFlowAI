/**
 * Spec 013 — the Simple view's per-agent Skills picker (parity with the
 * Canvas view's CanvasConfigRail, R-01/R-36/R-38). Mirrors
 * `CanvasConfigRail.test.tsx`'s skills-picker suite: same fixtures, same
 * mocked `useSkillsCatalog` (Redux-backed, mocked here so this test doesn't
 * need a live `<Provider>` — same idiom as `@/lib/api` below).
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

const SKILL_FIXTURES = [
  { id: "market-research", name: "Market Research", description: "", category: "research" as const, content: "", tags: [], compatible_agents: ["prototype-plan"] },
  { id: "any-skill", name: "Any Skill", description: "", category: "workflow" as const, content: "", tags: [] },
];
vi.mock("@/hooks/useSkillsCatalog", () => ({
  useSkillsCatalog: () => ({ skills: SKILL_FIXTURES, categories: [] }),
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

describe("AgentRow — Simple view skills picker (R-01/R-36/R-38)", () => {
  it("opens the config panel and renders a skills list, filtered by compatible_agents", async () => {
    renderRow();
    await userEvent.click(screen.getByRole("button", { name: /model for plan/i }));
    // `market-research`'s compatible_agents includes "prototype-plan" (PLAN.id).
    expect(await screen.findByText("Market Research")).toBeInTheDocument();
    // `any-skill` has no compatible_agents (compatible with everything, R-33).
    expect(screen.getByText("Any Skill")).toBeInTheDocument();
  });

  it("is unrestricted for a custom agent — offers every skill regardless of compatible_agents (R-34)", async () => {
    const custom = mkAgent({ id: "agent-1", name: "Custom One", isCustom: true, instance_id: "agent-1" });
    renderRow({ agent: custom });
    await userEvent.click(screen.getByRole("button", { name: /model for custom one/i }));
    expect(await screen.findByText("Market Research")).toBeInTheDocument();
    expect(screen.getByText("Any Skill")).toBeInTheDocument();
  });

  it("toggling a skill via its Add/Remove button calls onSkillsChange with the updated skill id list", async () => {
    const onSkillsChange = vi.fn();
    renderRow({ onSkillsChange });
    await userEvent.click(screen.getByRole("button", { name: /model for plan/i }));
    await screen.findByText("Market Research");
    await userEvent.click(screen.getByRole("button", { name: "Add Market Research" }));
    expect(onSkillsChange).toHaveBeenCalledWith("prototype-plan", ["market-research"]);
  });

  it("shows a Skills chip on the collapsed row, matching the Validator/Gate/Retry chip style", () => {
    const withSkills = mkAgent({ id: "prototype-plan", name: "Plan", skills: ["market-research"] });
    renderRow({ agent: withSkills });
    const chip = screen.getByRole("button", { name: "Skills" });
    expect(chip.className).toContain("bg-ink-900");
  });

  it("the Skills chip is inactive-styled when no skills are attached", () => {
    renderRow();
    const chip = screen.getByRole("button", { name: "Skills" });
    expect(chip.className).not.toContain("bg-ink-900");
  });
});
