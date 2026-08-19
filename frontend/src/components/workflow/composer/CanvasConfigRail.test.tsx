/**
 * 51-07 (FANOUT-01 / D6/D7/D9) — the Canvas config-rail fan-out control.
 *
 * The rail gains a "Fan out over a list" toggle + a "Source list from" picker
 * (§4b), reusing the SHARED `applyLeverPatch` reducer (via the rail's `patch()`)
 * and the SHARED `KNOWN_PRODUCERS` allow-list — NO forked lever logic, NO
 * redefined type/allow-list (they are imported from AgentsPopup). These tests
 * pin the parity contract with the simple-view surface (AdvancedExpander, 51-06):
 *
 *   1. Enabling persists `{ strategy: "fanout_batch", task_source: { source_step } }`,
 *      defaulting the source to a KNOWN upstream producer.
 *   2. The source picker lists ONLY earlier agents (priorAgents); with no known
 *      producer upstream it defaults to the immediately-preceding step.
 *   3. The toggle is DISABLED for a step with no upstream (the first agent) + hint.
 *   4. Toggling OFF clears every fan-out lever (selection omitted when empty).
 *   5. A NON-blocking warning renders when the chosen source is not a known producer.
 *
 * `getCapabilities`/prompt fetchers are mocked (same idiom as CanvasView.test).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import type { ComponentProps } from "react";
import { renderWithProviders, screen, within, waitFor } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";
import type { CapabilitiesPalette } from "@/lib/api";
import type { AgentDef } from "@/types/index";
import type { StepSelection } from "../AgentsPopup";

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

// The skills picker (T29/R-36/R-38) reads the global Skills catalog via
// `useSkillsCatalog` (Redux-backed) — mocked here (same idiom as `@/lib/api`
// above) so these tests don't need a live `<Provider>`.
const SKILL_FIXTURES = [
  { id: "market-research", name: "Market Research", description: "", category: "research" as const, content: "", tags: [], compatible_agents: ["prototype-plan"] },
  { id: "any-skill", name: "Any Skill", description: "", category: "workflow" as const, content: "", tags: [] },
];
vi.mock("@/hooks/useSkillsCatalog", () => ({
  useSkillsCatalog: () => ({ skills: SKILL_FIXTURES, categories: [] }),
}));

import { CanvasConfigRail } from "./CanvasConfigRail";

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

// `prototype-plan` is a v1 KNOWN `## Task N:` producer; `writer`/`researcher` are not.
const PLAN = mkAgent({ id: "prototype-plan", name: "Plan" });
const RESEARCHER = mkAgent({ id: "researcher", name: "Researcher" });
const WRITER = mkAgent({ id: "writer", name: "Writer" });

function renderRail(props: Partial<ComponentProps<typeof CanvasConfigRail>> = {}) {
  const onSelection = vi.fn();
  const utils = renderWithProviders(
    <CanvasConfigRail
      agent={WRITER}
      index={2}
      total={3}
      selection={undefined}
      onSelection={onSelection}
      priorAgents={[PLAN, RESEARCHER]}
      {...props}
    />,
  );
  return { ...utils, onSelection };
}

// The rail is a 4-tab inspector (Overview/Skills/Hooks/Config, mirroring the
// library agent drawer) — Model/Overrides/Fan-out/Strategy live under Config,
// the custom-agent prompt editor under Overview, the picker under Skills. The
// tab bar itself renders synchronously (it doesn't wait on the capabilities
// fetch), so switching tabs never needs its own `findBy`.
async function openTab(name: RegExp) {
  await userEvent.click(screen.getByRole("tab", { name }));
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGetCapabilities.mockResolvedValue(PALETTE);
});

describe("CanvasConfigRail — 51-07 fan-out control (FANOUT-01)", () => {
  it("persists {strategy: 'fanout_batch', task_source.source_step} when enabled, defaulting to a known upstream producer", async () => {
    const { onSelection } = renderRail();
    await openTab(/config/i);
    // Let the shared capabilities fetch settle before interacting (userEvent
    // clicks are swallowed while a pending act/microtask is in flight).
    await screen.findByLabelText(/^Model$/i);
    await userEvent.click(
      screen.getByRole("switch", { name: /fan out over a list/i }),
    );
    await waitFor(() => expect(onSelection).toHaveBeenCalled());
    const [id, sel] = onSelection.mock.calls.at(-1) as [string, StepSelection | undefined];
    expect(id).toBe("writer");
    expect(sel).toMatchObject({
      strategy: "fanout_batch",
      task_source: {
        kind: "parsed",
        parser: "heading_tasks",
        source_step: "prototype-plan", // the known producer, auto-selected
      },
    });
  });

  it("lists ONLY earlier agents (priorAgents) in the source picker", async () => {
    renderRail({
      selection: {
        strategy: "fanout_batch",
        task_source: { kind: "parsed", parser: "heading_tasks", source_step: "prototype-plan" },
      },
    });
    await openTab(/config/i);
    const source = screen.getByLabelText(/source list from/i);
    expect(within(source).getByText("Plan")).toBeInTheDocument();
    expect(within(source).getByText("Researcher")).toBeInTheDocument();
    expect(within(source).queryByText("Writer")).not.toBeInTheDocument();
  });

  it("defaults the source to the immediately-preceding step when no known producer is upstream", async () => {
    const { onSelection } = renderRail({
      agent: WRITER,
      priorAgents: [RESEARCHER, mkAgent({ id: "editor", name: "Editor" })],
    });
    await openTab(/config/i);
    await screen.findByLabelText(/^Model$/i);
    await userEvent.click(
      screen.getByRole("switch", { name: /fan out over a list/i }),
    );
    await waitFor(() => expect(onSelection).toHaveBeenCalled());
    const [, sel] = onSelection.mock.calls.at(-1) as [string, StepSelection | undefined];
    expect(sel?.task_source?.source_step).toBe("editor");
  });

  it("disables the fan-out toggle for the first agent (no upstream) with a hint", async () => {
    renderRail({ agent: PLAN, index: 0, priorAgents: [] });
    await openTab(/config/i);
    const toggle = screen.getByRole("switch", { name: /fan out over a list/i });
    expect(toggle).toBeDisabled();
    expect(
      screen.getByText(/add an earlier step that outputs a task list/i),
    ).toBeInTheDocument();
  });

  it("clears the fan-out levers when toggled OFF (selection omitted when empty)", async () => {
    const { onSelection } = renderRail({
      selection: {
        strategy: "fanout_batch",
        task_source: { kind: "parsed", parser: "heading_tasks", source_step: "prototype-plan" },
      },
    });
    await openTab(/config/i);
    await screen.findByLabelText(/^Model$/i);
    await userEvent.click(
      screen.getByRole("switch", { name: /fan out over a list/i }),
    );
    await waitFor(() => expect(onSelection).toHaveBeenCalled());
    const [id, sel] = onSelection.mock.calls.at(-1) as [string, StepSelection | undefined];
    expect(id).toBe("writer");
    // Only fan-out levers were set → clearing them omits the selection entirely.
    expect(sel).toBeUndefined();
  });

  it("renders a non-blocking warning when the chosen source is not a known producer", async () => {
    renderRail({
      selection: {
        strategy: "fanout_batch",
        task_source: { kind: "parsed", parser: "heading_tasks", source_step: "researcher" },
      },
    });
    await openTab(/config/i);
    // `researcher` is not on the known-producer allow-list → steer the user.
    expect(screen.getByText(/fans out one worker per/i)).toBeInTheDocument();
    // Still persists the strategy (non-blocking) — the source picker is present.
    expect(screen.getByLabelText(/source list from/i)).toBeInTheDocument();
  });

  it("no warning renders when the chosen source IS a known producer", async () => {
    renderRail({
      selection: {
        strategy: "fanout_batch",
        task_source: { kind: "parsed", parser: "heading_tasks", source_step: "prototype-plan" },
      },
    });
    await openTab(/config/i);
    expect(screen.queryByText(/fans out one worker per/i)).not.toBeInTheDocument();
  });
});

// ── Reuse guard (source-level): no redefined type/allow-list, shared reducer ──────
describe("CanvasConfigRail — reuses the shared fan-out type + allow-list (INV-3 / SC-001)", () => {
  it("imports KNOWN_PRODUCERS + StepSelection from AgentsPopup and writes fan-out via patch()", async () => {
    const { readFileSync } = await import("node:fs");
    const { resolve } = await import("node:path");
    const src = readFileSync(
      resolve(process.cwd(), "src/components/workflow/composer/CanvasConfigRail.tsx"),
      "utf8",
    );
    // Imported from the shared module, not redefined locally.
    expect(src).toMatch(/KNOWN_PRODUCERS/);
    expect(src).not.toMatch(/const\s+KNOWN_PRODUCERS/);
    // Fan-out persists via the shared reducer (patch → applyLeverPatch), not a fork.
    expect(src).toMatch(/patch\(\{[\s\S]*strategy: "fanout_batch"/);
  });
});

// ── Spec 012 (R-36/R-38/T29) — skills picker, custom-agent prompt editor,
//    strategy selector, workflow-level internet toggle. ─────────────────────
describe("CanvasConfigRail — skills picker (R-01/R-36/R-38)", () => {
  it("filters the picker by compatible_agents for a built-in agent", async () => {
    renderRail({ agent: PLAN, index: 0, priorAgents: [] });
    await openTab(/skills/i);
    // `market-research`'s compatible_agents includes "prototype-plan" (PLAN.id).
    expect(screen.getByText("Market Research")).toBeInTheDocument();
    // `any-skill` has no compatible_agents (compatible with everything, R-33).
    expect(screen.getByText("Any Skill")).toBeInTheDocument();
  });

  it("is unrestricted for a custom agent — offers every skill regardless of compatible_agents (R-34)", async () => {
    const custom = mkAgent({ id: "agent-1", name: "Custom One", isCustom: true, instance_id: "agent-1" });
    renderRail({ agent: custom, index: 0, priorAgents: [] });
    await openTab(/skills/i);
    expect(screen.getByText("Market Research")).toBeInTheDocument();
    expect(screen.getByText("Any Skill")).toBeInTheDocument();
  });

  it("toggling a skill via its Add/Remove button calls onSkillsChange with the updated skill id list", async () => {
    const onSkillsChange = vi.fn();
    renderRail({ agent: PLAN, index: 0, priorAgents: [], onSkillsChange });
    await openTab(/skills/i);
    await userEvent.click(screen.getByRole("button", { name: "Add Market Research" }));
    expect(onSkillsChange).toHaveBeenCalledWith("prototype-plan", ["market-research"]);
  });
});

describe("CanvasConfigRail — custom-agent prompt editor (R-02/R-06/R-36)", () => {
  it("a custom agent gets its OWN prompt textarea, not the built-in AgentPromptSection", async () => {
    const custom = mkAgent({ id: "agent-1", name: "Custom One", isCustom: true, instance_id: "agent-1" });
    renderRail({ agent: custom, index: 0, priorAgents: [] });
    // The prompt editor lives on Overview (moved off Config alongside the
    // per-skill chip list).
    expect(screen.getByLabelText(/custom agent prompt/i)).toBeInTheDocument();
    expect(screen.queryByText(/System Prompt/i)).not.toBeInTheDocument();
  });

  it("editing the textarea calls onPromptChange", async () => {
    const onPromptChange = vi.fn();
    const custom = mkAgent({ id: "agent-1", name: "Custom One", isCustom: true, instance_id: "agent-1" });
    renderRail({ agent: custom, index: 0, priorAgents: [], onPromptChange });
    await userEvent.type(screen.getByLabelText(/custom agent prompt/i), "Do the thing");
    expect(onPromptChange).toHaveBeenCalled();
    expect(onPromptChange.mock.calls.at(-1)?.[0]).toBe("agent-1");
  });

  it("a built-in agent keeps the existing AgentPromptSection override (R-06)", async () => {
    renderRail({ agent: PLAN, index: 0, priorAgents: [] });
    expect(screen.getByText(/System Prompt/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/custom agent prompt/i)).not.toBeInTheDocument();
  });
});

describe("CanvasConfigRail — sub-agent strategy selector (R-04/R-36)", () => {
  const withChildren = mkAgent({
    id: "parent-1",
    name: "Parent",
    isCustom: true,
    instance_id: "parent-1",
    children: [mkAgent({ id: "agent-1", name: "Child", isCustom: true, instance_id: "agent-1" })],
  });

  it("is absent for a node with no children", async () => {
    renderRail({ agent: PLAN, index: 0, priorAgents: [] });
    await openTab(/config/i);
    await screen.findByLabelText(/^Model$/i);
    expect(screen.queryByLabelText(/sub-agent strategy/i)).not.toBeInTheDocument();
  });

  it("shows the strategy selector + max-parallel stepper when the node has children", async () => {
    renderRail({ agent: withChildren, index: 0, priorAgents: [] });
    await openTab(/config/i);
    await screen.findByLabelText(/^Model$/i);
    expect(screen.getByLabelText(/sub-agent strategy/i)).toBeInTheDocument();
  });

  it("changing the strategy calls onStrategyChange with the node id + chosen mode", async () => {
    const onStrategyChange = vi.fn();
    renderRail({ agent: withChildren, index: 0, priorAgents: [], onStrategyChange });
    await openTab(/config/i);
    await screen.findByLabelText(/^Model$/i);
    await userEvent.selectOptions(screen.getByLabelText(/sub-agent strategy/i), "parallel");
    expect(onStrategyChange).toHaveBeenCalledWith("parent-1", "parallel", undefined);
  });

  it("max-parallel stepper increments via onStrategyChange, defaulting the base to 3", async () => {
    const onStrategyChange = vi.fn();
    const parallelParent = { ...withChildren, strategy: "parallel" as const };
    renderRail({ agent: parallelParent, index: 0, priorAgents: [], onStrategyChange });
    await openTab(/config/i);
    await screen.findByLabelText(/^Model$/i);
    await userEvent.click(screen.getByRole("button", { name: /increase max parallel/i }));
    expect(onStrategyChange).toHaveBeenCalledWith("parent-1", "parallel", 4);
  });
});

// Workflow-level internet/run-settings toggles moved to CanvasView (they live
// under the Brief instruction now, not the per-node rail) — see
// CanvasView.test.tsx for their coverage.
