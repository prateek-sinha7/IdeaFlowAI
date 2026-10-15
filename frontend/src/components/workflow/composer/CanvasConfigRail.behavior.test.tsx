/**
 * Behavior of the Canvas config rail beyond the fan-out / skills / effort /
 * gate suites: the empty state, header rename, tab navigation, hooks, tool
 * grants and packs, node type, design context, overrides, retry, the route
 * editor and the sub-agent strategy.
 *
 * Boundaries replaced: the capabilities / prompt / workflow-catalog APIs and the
 * (Redux-backed) skills catalog. Redux itself, the shared lever reducer and the
 * hooks catalog run for real through renderWithProviders.
 */
// MERGE NOTE (feat/user-stories-v2 into feat/stale-bug-fixes, 2026-10-12): this suite came
// from dev (75c58275c) and was written against dev's pre-redesign rail. The 14
// it.skip cases assert UI our branch replaced (5b3540d71 / 911547c7d): Node type is an
// Overview radio group, there is no Hooks tab, the code-step and fan-out task-source
// controls changed. The redesigned rail is covered by CanvasConfigRail.test.tsx,
// .dataTab, .effort, .iss686 and .iss765. Retarget or delete these skips in a follow-up.
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { ComponentProps } from "react";
import { renderWithProviders, screen, waitFor, within } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";
import type { CapabilitiesPalette } from "@/lib/api";
import type { AgentDef } from "@/types/index";
import type { StepSelection } from "../AgentsPopup";

const mockGetCapabilities = vi.fn();
const mockListUserWorkflows = vi.fn();
vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getCapabilities: (t: string) => mockGetCapabilities(t),
  getWorkflowDefinitions: vi.fn().mockResolvedValue([]),
  getAgentPrompt: vi
    .fn()
    .mockResolvedValue({ prompt_body: "", override: null, has_override: false }),
  saveAgentPromptOverride: vi.fn(),
  deleteAgentPromptOverride: vi.fn(),
}));
vi.mock("@/store/api/userWorkflows", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/store/api/userWorkflows")>();
  return {
    ...actual,
    userWorkflowsApi: { ...actual.userWorkflowsApi, list: () => mockListUserWorkflows() },
  };
});
vi.mock("@/hooks/useSkillsCatalog", () => ({
  useSkillsCatalog: () => ({ skills: [], categories: [] }),
}));

import { CanvasConfigRail } from "./CanvasConfigRail";

const PALETTE: CapabilitiesPalette = {
  capabilities: [
    { kind: "validator", name: "code_test", user_allowed: true, description: "Runs the tests.", security_gated: false, config_schema: {} },
    { kind: "gate", name: "approval", user_allowed: true, description: "Approval gate.", security_gated: false, config_schema: {} },
    { kind: "gate", name: "human", user_allowed: true, description: "Human review.", security_gated: false, config_schema: {} },
    { kind: "gate", name: "before-human", user_allowed: true, description: "Pre-step review.", security_gated: false, config_schema: {} },
    { kind: "gate", name: "conditional", user_allowed: true, description: "Branch on a decision.", security_gated: false, config_schema: {} },
    { kind: "gate", name: "validation", user_allowed: true, description: "Coupled to the validator.", security_gated: false, config_schema: {} },
    { kind: "mechanical", name: "publish", user_allowed: true, description: "Copy the final file onto the deliverable.", security_gated: false, config_schema: {} },
    { kind: "mechanical", name: "assemble_prototype", user_allowed: true, description: "Assemble parts into the shell.", security_gated: false, config_schema: {} },
    { kind: "mechanical", name: "custom_stitch", user_allowed: true, description: "Stitch things.", security_gated: false, config_schema: {} },
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

const WRITER = mkAgent({ id: "writer", name: "Writer", role: "Writes drafts" });
const RESEARCHER = mkAgent({ id: "researcher", name: "Researcher" });
const REVIEWER = mkAgent({ id: "reviewer", name: "Reviewer" });

function renderRail(props: Partial<ComponentProps<typeof CanvasConfigRail>> = {}, preloadedState = {}) {
  const handlers = {
    onSelection: vi.fn(),
    onSkillsChange: vi.fn(),
    onPromptChange: vi.fn(),
    onStrategyChange: vi.fn(),
    onRename: vi.fn(),
    onRouteChange: vi.fn(),
    onMechanicalChange: vi.fn(),
    onInjectsChange: vi.fn(),
  };
  const utils = renderWithProviders(
    <CanvasConfigRail
      agent={WRITER}
      index={2}
      total={4}
      selection={undefined}
      priorAgents={[RESEARCHER]}
      {...handlers}
      {...props}
    />,
    { preloadedState },
  );
  return { ...utils, ...handlers };
}

async function openTab(name: RegExp) {
  await userEvent.click(screen.getByRole("tab", { name }));
}

/** Open the Config tab and wait for the capabilities fetch to enable the controls.
 *  The Node type control is a radio group on the Overview tab on this branch
 *  (5b3540d71 / 911547c7d), so readiness is the first Config combobox enabled. */
async function openConfig() {
  await openTab(/config/i);
  await waitFor(() => expect(screen.getAllByRole("combobox")[0]).toBeEnabled());
}

/** The Overview tab's "Node type" radio group (AI agent / Code). */
async function nodeTypeRadio(label: "AI agent" | "Code") {
  await openTab(/overview/i);
  const group = await screen.findByRole("radiogroup", { name: "Node type" });
  return within(group).getByRole("radio", { name: label });
}

const lastSelection = (fn: ReturnType<typeof vi.fn>) => fn.mock.calls.at(-1) as [string, Record<string, unknown> | undefined];

beforeEach(() => {
  vi.clearAllMocks();
  mockGetCapabilities.mockResolvedValue(PALETTE);
  mockListUserWorkflows.mockResolvedValue([]);
});

describe("CanvasConfigRail", () => {
  describe("without a selection", () => {
    it("asks the author to select a node", () => {
      renderRail({ agent: null });

      expect(screen.getByText("Select a node")).toBeInTheDocument();
      expect(screen.queryByRole("tab")).not.toBeInTheDocument();
    });
  });

  describe("header", () => {
    it.skip("shows the agent's position and role", () => {
      renderRail();

      expect(screen.getByDisplayValue("Writer")).toBeInTheDocument();
      expect(screen.getByText("Agent · step 3 of 4 · Writes drafts")).toBeInTheDocument();
    });

    it("renames the agent on blur with the trimmed name", async () => {
      const user = userEvent.setup();
      const { onRename } = renderRail();

      const input = screen.getByRole("textbox", { name: "Agent name" });
      await user.clear(input);
      await user.type(input, "  Editor  ");
      await user.tab();

      expect(onRename).toHaveBeenCalledWith("writer", "Editor");
    });

    it("commits a rename when Enter is pressed", async () => {
      const user = userEvent.setup();
      const { onRename } = renderRail();

      const input = screen.getByRole("textbox", { name: "Agent name" });
      await user.clear(input);
      await user.type(input, "Editor{Enter}");

      expect(onRename).toHaveBeenCalledWith("writer", "Editor");
    });

    it("discards the draft on Escape", async () => {
      const user = userEvent.setup();
      const { onRename } = renderRail();

      const input = screen.getByRole("textbox", { name: "Agent name" });
      await user.type(input, "XYZ{Escape}");
      expect(input).toHaveValue("Writer");
      await user.tab();

      expect(onRename).not.toHaveBeenCalled();
    });

    it("does not rename to a blank or unchanged name", async () => {
      const user = userEvent.setup();
      const { onRename } = renderRail();
      const input = screen.getByRole("textbox", { name: "Agent name" });

      await user.clear(input);
      await user.tab();
      expect(input).toHaveValue("Writer");

      await user.click(input);
      await user.tab();

      expect(onRename).not.toHaveBeenCalled();
    });
  });

  describe("tabs", () => {
    it("starts on Overview and shows the agent's description", () => {
      renderRail();

      expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
      expect(screen.getByText("A capable agent.")).toBeInTheDocument();
    });

    it("omits the description paragraph when the agent has none", () => {
      renderRail({ agent: { ...WRITER, description: "" } });

      expect(screen.queryByText("A capable agent.")).not.toBeInTheDocument();
    });

    it("jumps to the Config tab when the open-config signal is bumped", async () => {
      const { rerender } = renderRail({ openConfigSignal: 0 });
      expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");

      rerender(
        <CanvasConfigRail
          agent={WRITER}
          index={2}
          total={4}
          onSelection={vi.fn()}
          openConfigSignal={1}
        />,
      );

      await waitFor(() =>
        expect(screen.getByRole("tab", { name: "Config" })).toHaveAttribute("aria-selected", "true"),
      );
    });

    it("edits a custom agent's own prompt on Overview", async () => {
      const user = userEvent.setup();
      const { onPromptChange } = renderRail({ agent: { ...WRITER, isCustom: true, prompt: "" } });

      await user.type(screen.getByRole("textbox", { name: "Custom agent prompt" }), "Hi");

      expect(onPromptChange).toHaveBeenLastCalledWith("writer", "i");
    });
  });

  describe("hooks tab", () => {
    const hooksState = {
      hooks: {
        hooks: [
          { id: "h1", name: "lint", display_name: "Lint on save", description: "Runs the linter", content: "", event: "PostToolUse", trigger: "Write", compatible_agents: ["writer"], tags: [] },
          { id: "h2", name: "other", display_name: "", description: "Not for this agent", content: "", event: "Stop", trigger: "*", compatible_agents: ["someone-else"], tags: [] },
        ],
        totalCount: 2,
        hookEvents: [],
        status: "succeeded" as const,
        error: null,
      },
    };

    it.skip("suggests only hooks compatible with this agent", async () => {
      renderRail({}, hooksState);
      await openTab(/hooks/i);

      expect(screen.getByText("Lint on save")).toBeInTheDocument();
      expect(screen.getByText("Runs the linter")).toBeInTheDocument();
      expect(screen.queryByText("Not for this agent")).not.toBeInTheDocument();
    });

    it.skip("attaches a suggested hook once and then marks it Added", async () => {
      const user = userEvent.setup();
      renderRail({}, hooksState);
      await openTab(/hooks/i);

      await user.click(screen.getByRole("button", { name: /Attach/ }));

      const added = await screen.findByRole("button", { name: /Added/ });
      expect(added).toBeDisabled();
    });

    it.skip("says there are no suggestions when none fit", async () => {
      renderRail();
      await openTab(/hooks/i);

      expect(screen.getByText("No suggested hooks")).toBeInTheDocument();
    });
  });

  describe("tools tab", () => {
    async function openTools() {
      await openTab(/tools/i);
      await waitFor(() => expect(screen.getByRole("switch", { name: "Read files" })).toBeEnabled());
    }

    it("shows read and write on by default and execute permanently off", async () => {
      renderRail();
      await openTools();

      expect(screen.getByRole("switch", { name: "Read files" })).toBeChecked();
      expect(screen.getByRole("switch", { name: "Write files" })).toBeChecked();
      const exec = screen.getByRole("switch", { name: "Execute commands" });
      expect(exec).not.toBeChecked();
      expect(exec).toBeDisabled();
    });

    it("revokes write access without touching read access", async () => {
      const user = userEvent.setup();
      const { onSelection } = renderRail();
      await openTools();

      await user.click(screen.getByRole("switch", { name: "Write files" }));

      const [id, sel] = lastSelection(onSelection);
      expect(id).toBe("writer");
      expect(sel).toMatchObject({ tools: { read_files: true, write_files: false } });
    });

    it("grants write access back when it was revoked", async () => {
      const user = userEvent.setup();
      const { onSelection } = renderRail({ selection: { tools: { read_files: true, write_files: false } } });
      await openTools();

      await user.click(screen.getByRole("switch", { name: "Write files" }));

      const [, sel] = lastSelection(onSelection);
      expect(sel).toEqual({ tools: { read_files: true, write_files: true } });
    });

    it("adds a tool pack alongside the file grants", async () => {
      const user = userEvent.setup();
      const { onSelection } = renderRail();
      await openTools();

      await user.click(screen.getByRole("switch", { name: "Playwright browser" }));

      const [, sel] = lastSelection(onSelection);
      expect(sel).toMatchObject({ tools: { tool_sets: ["playwright"] } });
    });

    it("keeps the other pack when one of two is switched off", async () => {
      const user = userEvent.setup();
      const { onSelection } = renderRail({
        selection: { tools: { read_files: true, write_files: true, tool_sets: ["file_extract", "playwright"] } },
      });
      await openTools();
      expect(screen.getByRole("switch", { name: "File extraction" })).toBeChecked();

      await user.click(screen.getByRole("switch", { name: "File extraction" }));

      const [, sel] = lastSelection(onSelection);
      expect(sel).toMatchObject({ tools: { tool_sets: ["playwright"] } });
    });

    it("drops the pack list entirely when the last pack is switched off", async () => {
      const user = userEvent.setup();
      const { onSelection } = renderRail({
        selection: { tools: { read_files: true, write_files: true, tool_sets: ["playwright"] } },
      });
      await openTools();

      await user.click(screen.getByRole("switch", { name: "Playwright browser" }));

      const [, sel] = lastSelection(onSelection);
      expect(sel?.tools).toEqual({ read_files: true, write_files: true });
      expect(sel?.tools).not.toHaveProperty("tool_sets");
    });
  });

  describe("config tab: node type", () => {
    it("lists model-only controls for an AI agent", async () => {
      renderRail();
      await openConfig();

      expect(screen.getByRole("combobox", { name: "Model" })).toBeInTheDocument();
      expect(screen.getByRole("checkbox", { name: "Design context: Design system" })).toBeInTheDocument();
      expect(screen.queryByRole("combobox", { name: "Code step" })).not.toBeInTheDocument();
    });

    it("switches an AI agent to the first code step offered", async () => {
      const user = userEvent.setup();
      const { onMechanicalChange } = renderRail();
      await openConfig();

      await waitFor(async () => expect(await nodeTypeRadio("Code")).toBeEnabled());
      await user.click(await nodeTypeRadio("Code"));

      expect(onMechanicalChange).toHaveBeenCalledWith("writer", "publish");
    });

    it("switches a code step back to an AI agent", async () => {
      const user = userEvent.setup();
      const { onMechanicalChange } = renderRail({ agent: { ...WRITER, mechanical: "publish" } });
      await openConfig();

      await waitFor(async () => expect(await nodeTypeRadio("AI agent")).toBeEnabled());
      await user.click(await nodeTypeRadio("AI agent"));

      expect(onMechanicalChange).toHaveBeenCalledWith("writer", undefined);
    });

    it.skip("shows a code step's kind with its description and hides the model and design controls", async () => {
      const user = userEvent.setup();
      const { onMechanicalChange } = renderRail({ agent: { ...WRITER, mechanical: "publish" } });
      await openConfig();

      expect(screen.getByRole("combobox", { name: "Code step" })).toHaveValue("publish");
      expect(screen.getByText("Copy the final file onto the deliverable.")).toBeInTheDocument();
      expect(screen.queryByRole("combobox", { name: "Model" })).not.toBeInTheDocument();
      expect(screen.queryByRole("checkbox", { name: /Design context/ })).not.toBeInTheDocument();

      await user.selectOptions(screen.getByRole("combobox", { name: "Code step" }), "assemble_prototype");
      expect(onMechanicalChange).toHaveBeenCalledWith("writer", "assemble_prototype");
    });

    it.skip("names code steps in plain language, humanising any without a friendly name", async () => {
      renderRail({ agent: { ...WRITER, mechanical: "publish" } });
      await openConfig();

      const select = screen.getByRole("combobox", { name: "Code step" });
      expect(within(select).getByRole("option", { name: "Publish the final file" })).toBeInTheDocument();
      expect(within(select).getByRole("option", { name: "Assemble the prototype" })).toBeInTheDocument();
      expect(within(select).getByRole("option", { name: "Custom stitch" })).toBeInTheDocument();
    });

    it("shows no description for a code step the catalog does not list", async () => {
      renderRail({ agent: { ...WRITER, mechanical: "retired_step" } });
      await openConfig();

      expect(screen.queryByText("Copy the final file onto the deliverable.")).not.toBeInTheDocument();
    });

    it.skip("disables the Code option when the catalog offers no code steps", async () => {
      mockGetCapabilities.mockResolvedValue({ ...PALETTE, capabilities: PALETTE.capabilities.filter((c) => c.kind !== "mechanical") });
      renderRail();
      await openConfig();

      expect(screen.getByRole("option", { name: /^Code —/ })).toBeDisabled();
    });
  });

  describe("config tab: design context", () => {
    it("adds a block in canonical order", async () => {
      const user = userEvent.setup();
      const { onInjectsChange } = renderRail({ agent: { ...WRITER, injects: ["template_example"] } });
      await openConfig();

      await user.click(screen.getByRole("checkbox", { name: "Design context: Design system" }));

      expect(onInjectsChange).toHaveBeenCalledWith("writer", ["design_system", "template_example"]);
    });

    it("adds a block when none were set", async () => {
      const user = userEvent.setup();
      const { onInjectsChange } = renderRail();
      await openConfig();

      await user.click(screen.getByRole("checkbox", { name: "Design context: Template" }));

      expect(onInjectsChange).toHaveBeenCalledWith("writer", ["template"]);
    });

    it("removes only the unchecked block", async () => {
      const user = userEvent.setup();
      const { onInjectsChange } = renderRail({ agent: { ...WRITER, injects: ["design_system", "template"] } });
      await openConfig();
      expect(screen.getByRole("checkbox", { name: "Design context: Template" })).toBeChecked();

      await user.click(screen.getByRole("checkbox", { name: "Design context: Template" }));

      expect(onInjectsChange).toHaveBeenCalledWith("writer", ["design_system"]);
    });
  });

  describe("config tab: overrides", () => {
    it("picks a model", async () => {
      const user = userEvent.setup();
      const { onSelection } = renderRail();
      await openConfig();

      await user.selectOptions(screen.getByRole("combobox", { name: "Model" }), "model-opus");

      expect(lastSelection(onSelection)[1]).toMatchObject({ model: "model-opus" });
    });

    it("turns the validator on with the first registered validator and off again", async () => {
      const user = userEvent.setup();
      const first = renderRail();
      await openConfig();

      await user.click(screen.getByRole("switch", { name: "Validator" }));
      expect(lastSelection(first.onSelection)[1]).toMatchObject({ validators: ["code_test"] });
      first.unmount();

      const second = renderRail({ selection: { validators: ["code_test"], gates: ["validation"] } });
      await openConfig();
      expect(screen.getByRole("switch", { name: "Validator" })).toBeChecked();
      await user.click(screen.getByRole("switch", { name: "Validator" }));
      // The validators are removed. (The coupled "validation" gate is left in
      // place by the shared reducer; see the evidence notes for the observation.)
      expect(lastSelection(second.onSelection)[1]).not.toHaveProperty("validators");
    });

    it("disables the validator switch when no validator is registered", async () => {
      mockGetCapabilities.mockResolvedValue({ ...PALETTE, capabilities: PALETTE.capabilities.filter((c) => c.kind !== "validator") });
      renderRail();
      await openConfig();

      expect(screen.getByRole("switch", { name: "Validator" })).toBeDisabled();
    });

    it("offers only the gates the author owns, with plain labels", async () => {
      renderRail();
      await openConfig();

      const gate = screen.getByRole("combobox", { name: "Gate" });
      expect(within(gate).getAllByRole("option").map((o) => o.textContent)).toEqual([
        "No gate",
        "Approval gate",
        "Human gate",
        "Conditional gate",
      ]);
    });

    it("sets a human gate and explains it", async () => {
      const user = userEvent.setup();
      const { onSelection } = renderRail();
      await openConfig();

      await user.selectOptions(screen.getByRole("combobox", { name: "Gate" }), "human");

      expect(lastSelection(onSelection)[1]).toMatchObject({ gates: ["human"] });
    });

    it("explains the chosen gate", async () => {
      renderRail({ selection: { gates: ["approval"] } });
      await openConfig();

      expect(screen.getByText("Explicit sign-off before this step runs")).toBeInTheDocument();
    });

    it("clears the gate when 'No gate' is chosen", async () => {
      const user = userEvent.setup();
      const { onSelection } = renderRail({ selection: { gates: ["human"] } });
      await openConfig();

      await user.selectOptions(screen.getByRole("combobox", { name: "Gate" }), "");

      expect(lastSelection(onSelection)[1]).toBeUndefined();
    });

    it("steps retries up to the cap of three and back down to off", async () => {
      const user = userEvent.setup();
      const { onSelection } = renderRail({ selection: { retry: 3 } });
      await openConfig();
      expect(screen.getByText("3×")).toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: "Increase retries" }));
      expect(lastSelection(onSelection)[1]).toMatchObject({ retry: 3 });

      await user.click(screen.getByRole("button", { name: "Decrease retries" }));
      expect(lastSelection(onSelection)[1]).toMatchObject({ retry: 2 });
    });

    it("turns retries off when the last one is removed and cannot go below off", async () => {
      const user = userEvent.setup();
      const { onSelection } = renderRail({ selection: { retry: 1 } });
      await openConfig();

      await user.click(screen.getByRole("button", { name: "Decrease retries" }));

      expect(lastSelection(onSelection)[1]).toBeUndefined();
    });

    it("shows retries as Off and disables the decrease button at zero", async () => {
      const user = userEvent.setup();
      const { onSelection } = renderRail();
      await openConfig();

      expect(screen.getByText("Off")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Decrease retries" })).toBeDisabled();
      await user.click(screen.getByRole("button", { name: "Increase retries" }));

      expect(lastSelection(onSelection)[1]).toMatchObject({ retry: 1 });
    });
  });

  describe("config tab: route editor", () => {
    const CONDITIONAL = { gates: ["conditional"] };
    const ALL = [RESEARCHER, WRITER, REVIEWER];
    const route = (outcomes: NonNullable<AgentDef["route"]>["outcomes"], extra: Partial<NonNullable<AgentDef["route"]>> = {}) => ({
      ...WRITER,
      route: { outcomes, ...extra },
    });

    it("is hidden until the gate is conditional", async () => {
      renderRail({ allSteps: ALL });
      await openConfig();

      expect(screen.queryByTestId("canvas-rail-route-writer")).not.toBeInTheDocument();
    });

    it("asks for at least one outcome when none exist", async () => {
      renderRail({ selection: CONDITIONAL, allSteps: ALL });
      await openConfig();

      expect(screen.getByText("At least one outcome is required for this gate to run.")).toBeInTheDocument();
    });

    it("adds an outcome under the next free name", async () => {
      const user = userEvent.setup();
      const { onRouteChange } = renderRail({
        selection: CONDITIONAL,
        allSteps: ALL,
        agent: route({ outcome_1: { trigger: "step", target: "reviewer" } }),
      });
      await openConfig();

      await user.click(screen.getByTestId("canvas-rail-route-add-writer"));

      expect(onRouteChange).toHaveBeenCalledWith("writer", {
        outcomes: {
          outcome_1: { trigger: "step", target: "reviewer" },
          outcome_2: { trigger: "step", target: "" },
        },
      });
    });

    it("stops offering new outcomes at the maximum", async () => {
      const outcomes = Object.fromEntries(
        [1, 2, 3, 4, 5].map((n) => [`outcome_${n}`, { trigger: "step" as const, target: "reviewer" }]),
      );
      renderRail({ selection: CONDITIONAL, allSteps: ALL, agent: route(outcomes) });
      await openConfig();

      const add = screen.getByTestId("canvas-rail-route-add-writer");
      expect(add).toBeDisabled();
      expect(add).toHaveAttribute("title", "Maximum 5 outcomes per gate");
    });

    it("removes an outcome", async () => {
      const user = userEvent.setup();
      const { onRouteChange } = renderRail({
        selection: CONDITIONAL,
        allSteps: ALL,
        agent: route({ a: { trigger: "step", target: "reviewer" }, b: { trigger: "step", target: "researcher" } }),
      });
      await openConfig();

      await user.click(screen.getByRole("button", { name: "Remove outcome a" }));

      expect(onRouteChange).toHaveBeenCalledWith("writer", {
        outcomes: { b: { trigger: "step", target: "researcher" } },
      });
    });

    it("renames an outcome's condition in place, keeping order", async () => {
      const user = userEvent.setup();
      const { onRouteChange } = renderRail({
        selection: CONDITIONAL,
        allSteps: ALL,
        agent: route({ a: { trigger: "step", target: "reviewer" }, b: { trigger: "step", target: "researcher" } }),
      });
      await openConfig();

      const [first] = screen.getAllByRole("textbox", { name: "Condition" });
      await user.clear(first);
      await user.type(first, "approved");
      await user.tab();

      const [, next] = onRouteChange.mock.calls.at(-1) as [string, NonNullable<AgentDef["route"]>];
      expect(Object.keys(next.outcomes)).toEqual(["approved", "b"]);
      expect(next.outcomes.approved).toEqual({ trigger: "step", target: "reviewer" });
    });

    it.each([
      ["blank", ""],
      ["unchanged", "a"],
      ["already used", "b"],
    ])("ignores a %s condition rename", async (_label, typed) => {
      const user = userEvent.setup();
      const { onRouteChange } = renderRail({
        selection: CONDITIONAL,
        allSteps: ALL,
        agent: route({ a: { trigger: "step", target: "reviewer" }, b: { trigger: "step", target: "researcher" } }),
      });
      await openConfig();

      const [first] = screen.getAllByRole("textbox", { name: "Condition" });
      await user.clear(first);
      if (typed) await user.type(first, typed);
      await user.tab();

      expect(onRouteChange).not.toHaveBeenCalled();
    });

    it("lists every other step as a target and writes the chosen id", async () => {
      const user = userEvent.setup();
      const { onRouteChange } = renderRail({
        selection: CONDITIONAL,
        allSteps: ALL,
        agent: route({ a: { trigger: "step", target: "" } }),
      });
      await openConfig();

      const target = screen.getByRole("combobox", { name: "Target" });
      expect(within(target).getAllByRole("option").map((o) => o.textContent)).toEqual([
        "Select a step…",
        "Researcher",
        "Reviewer",
      ]);
      await user.selectOptions(target, "reviewer");

      expect(onRouteChange).toHaveBeenCalledWith("writer", {
        outcomes: { a: { trigger: "step", target: "reviewer" } },
      });
    });

    it("keeps a target that names no known step visible as written", async () => {
      renderRail({
        selection: CONDITIONAL,
        allSteps: ALL,
        agent: route({ a: { trigger: "step", target: "ghost-step" } }),
      });
      await openConfig();

      expect(screen.getByRole("option", { name: "ghost-step" })).toBeInTheDocument();
    });

    it("shows a target stored in backend form as the step it names", async () => {
      renderRail({
        selection: CONDITIONAL,
        allSteps: [RESEARCHER, WRITER, mkAgent({ id: "pb-build", name: "Builder" })],
        agent: route({ a: { trigger: "step", target: "custom-agent:pb-build" } }),
      });
      await openConfig();

      expect(screen.getByRole("combobox", { name: "Target" })).toHaveValue("pb-build");
    });

    it("clears the target when an outcome changes from step to workflow", async () => {
      const user = userEvent.setup();
      const { onRouteChange } = renderRail({
        selection: CONDITIONAL,
        allSteps: ALL,
        agent: route({ a: { trigger: "step", target: "reviewer" } }),
      });
      await openConfig();

      await user.selectOptions(screen.getByRole("combobox", { name: "Type" }), "workflow");

      expect(onRouteChange).toHaveBeenCalledWith("writer", {
        outcomes: { a: { trigger: "workflow", target: "" } },
      });
    });

    it("offers a workflow picker for a workflow outcome", async () => {
      renderRail({
        selection: CONDITIONAL,
        allSteps: ALL,
        agent: route({ a: { trigger: "workflow", target: "self" } }),
      });
      await openConfig();

      expect(await screen.findByRole("button", { name: "Target" })).toHaveTextContent("self (this workflow)");
    });

    it("sets the default step for unmatched decisions and clears it again", async () => {
      const user = userEvent.setup();
      const { onRouteChange } = renderRail({
        selection: CONDITIONAL,
        allSteps: ALL,
        agent: route({ a: { trigger: "step", target: "reviewer" } }, { default_next: "researcher" }),
      });
      await openConfig();
      const fallback = screen.getByRole("combobox", { name: "Default (no match)" });
      expect(fallback).toHaveValue("researcher");

      await user.selectOptions(fallback, "reviewer");
      expect(onRouteChange).toHaveBeenLastCalledWith("writer", {
        outcomes: { a: { trigger: "step", target: "reviewer" } },
        default_next: "reviewer",
      });

      await user.selectOptions(fallback, "");
      const [, cleared] = onRouteChange.mock.calls.at(-1) as [string, NonNullable<AgentDef["route"]>];
      expect(cleared.default_next).toBeUndefined();
    });

    it("sets and clears the condition source", async () => {
      const user = userEvent.setup();
      const { onRouteChange } = renderRail({
        selection: CONDITIONAL,
        allSteps: ALL,
        agent: route({ a: { trigger: "step", target: "reviewer" } }, { condition_agent: "r" }),
      });
      await openConfig();

      const source = screen.getByRole("textbox", { name: "Condition source" });
      await user.clear(source);

      const [, next] = onRouteChange.mock.calls.at(-1) as [string, NonNullable<AgentDef["route"]>];
      expect(next.condition_agent).toBeUndefined();
    });

    it("tolerates edits when no route handler is supplied", async () => {
      const user = userEvent.setup();
      renderRail({
        selection: CONDITIONAL,
        allSteps: ALL,
        agent: route({}),
        onRouteChange: undefined,
      });
      await openConfig();

      await user.click(screen.getByTestId("canvas-rail-route-add-writer"));

      expect(screen.getByTestId("canvas-rail-route-writer")).toBeInTheDocument();
    });

    it("describes a shared cap when several outcomes loop back", async () => {
      renderRail({
        selection: CONDITIONAL,
        allSteps: ALL,
        agent: route({
          a: { trigger: "step", target: "researcher" },
          b: { trigger: "step", target: "writer" },
        }),
      });
      await openConfig();

      expect(screen.getAllByRole("spinbutton", { name: "Max loop count" })).toHaveLength(2);
      expect(
        screen.getAllByText(/one cap per gate, shared by every looping outcome here/)[0],
      ).toBeInTheDocument();
    });

    it("does not offer a loop cap for a forward target", async () => {
      renderRail({
        selection: CONDITIONAL,
        allSteps: ALL,
        agent: route({ a: { trigger: "step", target: "reviewer" } }),
      });
      await openConfig();

      expect(screen.queryByRole("spinbutton", { name: "Max loop count" })).not.toBeInTheDocument();
    });
  });

  describe("config tab: fan-out", () => {
    const FANOUT: StepSelection = {
      strategy: "fanout_batch",
      task_source: { kind: "parsed", parser: "heading_tasks", source_step: "researcher" },
    };

    it("disables fan-out for a first step with no upstream", async () => {
      renderRail({ priorAgents: [] });
      await openConfig();

      expect(screen.getByRole("switch", { name: "Fan out over a list" })).toBeDisabled();
      expect(screen.getByText("Add an earlier step that outputs a task list to fan out over.")).toBeInTheDocument();
    });

    it.skip("switches a batch fan-out to waves, seeding the dependency-ordered defaults", async () => {
      const user = userEvent.setup();
      const { onSelection } = renderRail({ selection: FANOUT });
      await openConfig();

      await user.selectOptions(screen.getByRole("combobox", { name: "Fan-out mode" }), "wave_scheduler");

      expect(lastSelection(onSelection)[1]).toMatchObject({
        strategy: "wave_scheduler",
        task_source: { kind: "parsed", parser: "json_tasks", target: "build/tasks.json", source_step: "researcher" },
        fanout: { agent: "self", mode: "parallel", max_parallel: 5 },
        on_conflict: "human_gate",
      });
    });

    it("keeps an explicitly chosen parser when the mode changes", async () => {
      const user = userEvent.setup();
      const { onSelection } = renderRail({
        selection: {
          strategy: "fanout_batch",
          task_source: { kind: "parsed", parser: "screen_plan", target: "build/screens.json", source_step: "researcher" },
        },
      });
      await openConfig();

      await user.selectOptions(screen.getByRole("combobox", { name: "Fan-out mode" }), "task_loop");

      const [, sel] = lastSelection(onSelection);
      expect(sel).toMatchObject({
        strategy: "task_loop",
        task_source: { parser: "screen_plan", target: "build/screens.json" },
      });
      expect(sel?.fanout).toBeUndefined();
    });

    it("changes the task source step while keeping the parser", async () => {
      const user = userEvent.setup();
      const { onSelection } = renderRail({
        priorAgents: [RESEARCHER, REVIEWER],
        selection: FANOUT,
      });
      await openConfig();

      await user.selectOptions(screen.getByRole("combobox", { name: "Task source agent" }), "reviewer");

      expect(lastSelection(onSelection)[1]).toMatchObject({
        task_source: { kind: "parsed", parser: "heading_tasks", source_step: "reviewer" },
      });
    });

    it("warns when the source step is not a known task producer", async () => {
      renderRail({ selection: FANOUT });
      await openConfig();

      expect(
        screen.getByText(/Make sure Researcher is prompted to end its reply with/),
      ).toBeInTheDocument();
    });

    it.skip("names the file a screen-list source must write", async () => {
      renderRail({
        selection: {
          strategy: "fanout_batch",
          task_source: { kind: "parsed", parser: "screen_plan", source_step: "researcher" },
        },
      });
      await openConfig();

      expect(screen.getByText(/Make sure Researcher is prompted to write/)).toBeInTheDocument();
      expect(screen.getAllByText("build/screens.json").length).toBeGreaterThan(0);
    });

    it("does not warn when the source step is a known task producer", async () => {
      renderRail({
        priorAgents: [mkAgent({ id: "prototype-plan", name: "Plan" })],
        selection: {
          strategy: "fanout_batch",
          task_source: { kind: "parsed", parser: "heading_tasks", source_step: "prototype-plan" },
        },
      });
      await openConfig();

      expect(screen.queryByText(/Make sure Plan is prompted/)).not.toBeInTheDocument();
    });
  });

  describe("config tab: fan-out defaults and task source type", () => {
    const PARSERS = [
      { kind: "task_parser", name: "heading_tasks", user_allowed: true, description: "Reads `## Task N:` headings.", security_gated: false, config_schema: {} },
      { kind: "task_parser", name: "json_tasks", user_allowed: true, description: "Reads a JSON task list.", security_gated: false, config_schema: {} },
      { kind: "task_parser", name: "screen_plan", user_allowed: true, description: "One task per screen.", security_gated: false, config_schema: {} },
    ] as unknown as CapabilitiesPalette["capabilities"];

    beforeEach(() => {
      mockGetCapabilities.mockResolvedValue({ ...PALETTE, capabilities: [...PALETTE.capabilities, ...PARSERS] });
    });

    it.skip("seeds the default parser and the preceding step when a fan-out has no task source yet", async () => {
      const user = userEvent.setup();
      const { onSelection } = renderRail({ selection: { strategy: "fanout_batch" } });
      await openConfig();

      await user.selectOptions(screen.getByRole("combobox", { name: "Fan-out mode" }), "wave_scheduler");

      expect(lastSelection(onSelection)[1]).toMatchObject({
        strategy: "wave_scheduler",
        task_source: { parser: "json_tasks", target: "build/tasks.json", source_step: "researcher" },
      });
    });

    it.skip("defaults the parser from the mode when the source step changes on a fan-out with no task source", async () => {
      const user = userEvent.setup();
      const first = renderRail({ priorAgents: [RESEARCHER, REVIEWER], selection: { strategy: "fanout_batch" } });
      await openConfig();
      await user.selectOptions(screen.getByRole("combobox", { name: "Task source agent" }), "researcher");
      expect(lastSelection(first.onSelection)[1]).toMatchObject({
        task_source: { parser: "heading_tasks", source_step: "researcher" },
      });
      first.unmount();

      const waves = renderRail({ priorAgents: [RESEARCHER, REVIEWER], selection: { strategy: "wave_scheduler" } });
      await openConfig();
      await user.selectOptions(screen.getByRole("combobox", { name: "Task source agent" }), "researcher");
      expect(lastSelection(waves.onSelection)[1]).toMatchObject({
        task_source: { parser: "json_tasks", target: "build/tasks.json", source_step: "researcher" },
      });
    });

    it("lists the registered task source types and describes the selected one", async () => {
      renderRail({ selection: { strategy: "fanout_batch", task_source: { kind: "parsed", parser: "json_tasks", source_step: "researcher" } } });
      await openConfig();

      const type = screen.getByRole("combobox", { name: "Task source type" });
      expect(type).toHaveValue("json_tasks");
      expect(within(type).getAllByRole("option").map((o) => o.textContent)).toEqual([
        "## Task headings",
        "JSON task list — build/tasks.json",
        "Screen list — build/screens.json",
      ]);
      expect(screen.getByText("Reads a JSON task list.")).toBeInTheDocument();
    });

    it("assumes the waves default type when none is stored", async () => {
      renderRail({ selection: { strategy: "wave_scheduler" } });
      await openConfig();

      expect(screen.getByRole("combobox", { name: "Task source type" })).toHaveValue("json_tasks");
    });

    it.skip("points a screen-list source at its file when that type is chosen", async () => {
      const user = userEvent.setup();
      const { onSelection } = renderRail({
        selection: { strategy: "fanout_batch", task_source: { kind: "parsed", parser: "heading_tasks", source_step: "researcher" } },
      });
      await openConfig();

      await user.selectOptions(screen.getByRole("combobox", { name: "Task source type" }), "screen_plan");

      expect(lastSelection(onSelection)[1]).toMatchObject({
        task_source: { kind: "parsed", parser: "screen_plan", target: "build/screens.json", source_step: "researcher" },
      });
    });

    it.skip("carries a stored target across when the new type has no fixed file", async () => {
      const user = userEvent.setup();
      const { onSelection } = renderRail({
        selection: {
          strategy: "fanout_batch",
          task_source: { kind: "parsed", parser: "json_tasks", target: "custom/tasks.json", source_step: "researcher" },
        },
      });
      await openConfig();

      await user.selectOptions(screen.getByRole("combobox", { name: "Task source type" }), "heading_tasks");

      expect(lastSelection(onSelection)[1]).toMatchObject({
        task_source: { parser: "heading_tasks", target: "custom/tasks.json" },
      });
    });

    it("falls back to the preceding step when the stored source is missing", async () => {
      const user = userEvent.setup();
      const { onSelection } = renderRail({
        selection: { strategy: "fanout_batch", task_source: { kind: "parsed", parser: "heading_tasks", source_step: "" } },
      });
      await openConfig();

      await user.selectOptions(screen.getByRole("combobox", { name: "Task source type" }), "screen_plan");

      expect(lastSelection(onSelection)[1]).toMatchObject({ task_source: { source_step: "researcher" } });
    });

    it.skip("refers to 'the source step' in the warning when the stored source is not an earlier step", async () => {
      renderRail({
        selection: { strategy: "wave_scheduler", task_source: { kind: "parsed", parser: "json_tasks", source_step: "gone" } },
      });
      await openConfig();

      expect(screen.getByText(/Make sure the source step is prompted to write/)).toBeInTheDocument();
    });

    it("does not describe a task source type the catalog does not list", async () => {
      renderRail({
        selection: { strategy: "fanout_batch", task_source: { kind: "parsed", parser: "retired_parser", source_step: "researcher" } },
      });
      await openConfig();

      expect(screen.queryByText("Reads `## Task N:` headings.")).not.toBeInTheDocument();
    });
  });

  describe("config tab: gate edge cases", () => {
    it("shows an unlisted gate under its raw name and hint", async () => {
      mockGetCapabilities.mockResolvedValue({
        ...PALETTE,
        capabilities: [
          ...PALETTE.capabilities,
          { kind: "gate", name: "legal_review", user_allowed: true, description: "Legal.", security_gated: false, config_schema: {} },
        ],
      });
      renderRail({ selection: { gates: ["legal_review"] } });
      await openConfig();

      expect(screen.getByRole("option", { name: "legal_review" })).toBeInTheDocument();
      expect(screen.getAllByText("legal_review").length).toBeGreaterThan(1);
    });

    it("keeps Prompt User's pre-step gate when the gate changes to conditional", async () => {
      const user = userEvent.setup();
      const { onSelection } = renderRail({ selection: { gates: ["before-human"] } });
      await openConfig();

      await user.selectOptions(screen.getByRole("combobox", { name: "Gate" }), "conditional");

      expect(lastSelection(onSelection)[1]).toMatchObject({ gates: ["before-human", "conditional"] });
    });

    it("drops Prompt User's pre-step gate when the gate changes to a human review", async () => {
      const user = userEvent.setup();
      const { onSelection } = renderRail({ selection: { gates: ["before-human", "conditional"] } });
      await openConfig();

      await user.selectOptions(screen.getByRole("combobox", { name: "Gate" }), "human");

      expect(lastSelection(onSelection)[1]).toMatchObject({ gates: ["human"] });
    });

    it("turns Prompt User on for a conditional step whose pre-step gate is already declared", async () => {
      const user = userEvent.setup();
      const { onSelection, onRouteChange } = renderRail({
        selection: { gates: ["before-human", "conditional"] },
        allSteps: [RESEARCHER, WRITER],
      });
      await openConfig();

      await user.click(screen.getByRole("switch", { name: "Prompt User" }));

      expect(lastSelection(onSelection)[1]).toMatchObject({ gates: ["before-human", "conditional"] });
      expect(onRouteChange).toHaveBeenCalledWith("writer", expect.objectContaining({ condition_agent: "researcher" }));
    });
  });

  describe("config tab: sub-agent strategy", () => {
    const withChildren = mkAgent({ id: "writer", name: "Writer", children: [mkAgent({ id: "kid", name: "Kid" })] });

    it("is hidden for an agent without sub-agents", async () => {
      renderRail();
      await openConfig();

      expect(screen.queryByRole("combobox", { name: "Sub-agent strategy" })).not.toBeInTheDocument();
    });

    it("defaults to sequential and hides the parallel limit", async () => {
      renderRail({ agent: withChildren });
      await openConfig();

      expect(screen.getByRole("combobox", { name: "Sub-agent strategy" })).toHaveValue("sequential");
      expect(screen.queryByRole("button", { name: "Increase max parallel" })).not.toBeInTheDocument();
    });

    it("switches to parallel, passing the current limit through", async () => {
      const user = userEvent.setup();
      const { onStrategyChange } = renderRail({ agent: { ...withChildren, maxParallel: 4 } });
      await openConfig();

      await user.selectOptions(screen.getByRole("combobox", { name: "Sub-agent strategy" }), "parallel");

      expect(onStrategyChange).toHaveBeenCalledWith("writer", "parallel", 4);
    });

    it("raises and lowers the parallel limit", async () => {
      const user = userEvent.setup();
      const { onStrategyChange } = renderRail({ agent: { ...withChildren, strategy: "parallel", maxParallel: 3 } });
      await openConfig();

      await user.click(screen.getByRole("button", { name: "Increase max parallel" }));
      expect(onStrategyChange).toHaveBeenLastCalledWith("writer", "parallel", 4);

      await user.click(screen.getByRole("button", { name: "Decrease max parallel" }));
      expect(onStrategyChange).toHaveBeenLastCalledWith("writer", "parallel", 2);
    });

    it("cannot lower the parallel limit below one", async () => {
      renderRail({ agent: { ...withChildren, strategy: "parallel", maxParallel: 1 } });
      await openConfig();

      expect(screen.getByRole("button", { name: "Decrease max parallel" })).toBeDisabled();
    });

    it("assumes a limit of three when none is set", async () => {
      renderRail({ agent: { ...withChildren, strategy: "parallel" } });
      await openConfig();

      expect(screen.getByText("3")).toBeInTheDocument();
    });
  });
});
