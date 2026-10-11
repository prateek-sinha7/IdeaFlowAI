/**
 * Gap-closing behaviour tests for the exported building blocks of AgentsPopup.tsx
 * (helpers, AgentPromptSection, AgentCapabilitiesModal, HooksTab,
 * CapabilityPaletteSection, AdvancedExpander and the Config-tab lever list).
 *
 * The main `AgentsPopup` composer (canvas, footer, save, cancel) is covered in
 * AgentsPopup.composer.test.tsx. Existing AgentsPopup.reskin / AdvancedExpander /
 * CapabilityPaletteSection / AgentDrawer / effortHelpers tests are left as-is.
 *
 * Boundary: `@/lib/api` (token + network). Everything else — Redux catalogs,
 * SkillsHooksProvider, Tabs, AgentSkillsPicker — is the real implementation.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderWithProviders, screen, waitFor, within, fireEvent } from "@/test/renderWithProviders";
import { act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { CapabilitiesPalette } from "@/lib/api";
import type { AgentDef } from "@/types/index";
import type { GlobalHookEntry } from "@/store/api/hooks";
import type { GlobalSkillEntry } from "@/store/api/skills";

const api = vi.hoisted(() => ({
  getToken: vi.fn(),
  getCapabilities: vi.fn(),
  getAgentPrompt: vi.fn(),
  saveAgentPromptOverride: vi.fn(),
  deleteAgentPromptOverride: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  getToken: api.getToken,
  getCapabilities: api.getCapabilities,
  getAgentPrompt: api.getAgentPrompt,
  saveAgentPromptOverride: api.saveAgentPromptOverride,
  deleteAgentPromptOverride: api.deleteAgentPromptOverride,
}));

import {
  AdvancedExpander,
  AgentCapabilitiesModal,
  AgentPromptSection,
  CapabilityPaletteSection,
  HooksTab,
  PIPELINE_LABEL,
  applyLeverPatch,
  effectiveToolGrants,
  getAgentInitials,
  getRole,
  hasToolOverride,
  type SelectionsMap,
} from "./AgentsPopup";

// ─── Builders ────────────────────────────────────────────────────────────────

const AGENT: AgentDef = {
  id: "requirements-analyst",
  name: "Requirements Analyst",
  description: "Analyzes requirements and produces a spec, drafts acceptance criteria.",
  role: "analyst",
  pipeline_type: "prototype",
  estimated_duration: 30,
  order: 1,
  icon: "🧠",
  has_skill: true,
};

function makeAgent(overrides: Partial<AgentDef> = {}): AgentDef {
  return { ...AGENT, ...overrides };
}

function makeHook(id: string, overrides: Partial<GlobalHookEntry> = {}): GlobalHookEntry {
  return {
    id,
    name: id,
    display_name: `Hook ${id}`,
    description: `Does ${id} things`,
    content: "",
    event: "PreToolUse",
    trigger: `on ${id}`,
    compatible_agents: [],
    tags: [],
    ...overrides,
  };
}

function makeSkill(id: string, overrides: Partial<GlobalSkillEntry> = {}): GlobalSkillEntry {
  return {
    id,
    name: id,
    display_name: `Skill ${id}`,
    description: `About ${id}`,
    content: "",
    category: "testing",
    tags: [],
    compatible_agents: [],
    ...overrides,
  };
}

function catalogState(hooks: GlobalHookEntry[] = [], skills: GlobalSkillEntry[] = []) {
  return {
    hooks: {
      hooks,
      totalCount: hooks.length,
      hookEvents: [
        { id: "all", label: "All" },
        { id: "PreToolUse", label: "Pre-tool" },
        { id: "Stop", label: "Stop" },
      ],
      status: "succeeded" as const,
      error: null,
    },
    skills: {
      skills,
      totalCount: skills.length,
      skillCategories: [],
      status: "succeeded" as const,
      error: null,
    },
  };
}

const PALETTE: CapabilitiesPalette = {
  capabilities: [
    { kind: "validator", name: "code_test", user_allowed: true, description: "Runs tests.", security_gated: false, config_schema: {} },
    { kind: "validator", name: "locked_validator", user_allowed: false, description: "", security_gated: true, config_schema: {} },
    { kind: "gate", name: "approval", user_allowed: true, description: "", security_gated: false, config_schema: {} },
    { kind: "gate", name: "security", user_allowed: true, description: "", security_gated: true, config_schema: {} },
    { kind: "gate", name: "validation", user_allowed: true, description: "", security_gated: false, config_schema: {} },
    { kind: "gate", name: "conditional", user_allowed: true, description: "", security_gated: false, config_schema: {} },
    { kind: "gate", name: "human", user_allowed: true, description: "", security_gated: false, config_schema: {} },
  ],
  model_catalog: [
    {
      id: "model-basic",
      label: "Basic Model",
      description: "Cheap and quick.",
      tier: "fast",
      cost_class: "low",
      provider: "anthropic",
      context_window: 200000,
      user_allowed: true,
      reasoning_mode: "none",
      reasoning_levels: [],
    },
    {
      id: "model-thinker",
      label: "Thinker Model",
      description: "Reasons at length.",
      tier: "powerful",
      cost_class: "premium",
      provider: "openai",
      context_window: 1000000,
      user_allowed: true,
      reasoning_mode: "effort",
      reasoning_levels: ["none", "low", "xhigh"],
    },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  api.getToken.mockReturnValue("tok");
  api.getCapabilities.mockResolvedValue(PALETTE);
  api.getAgentPrompt.mockResolvedValue({
    agent_id: AGENT.id,
    prompt_body: "You are the analyst.",
    override: null,
    has_override: false,
  });
  api.saveAgentPromptOverride.mockResolvedValue(undefined);
  api.deleteAgentPromptOverride.mockResolvedValue(undefined);
});

afterEach(() => {
  vi.useRealTimers();
});

// ─── Pure helpers ────────────────────────────────────────────────────────────

describe("getRole", () => {
  it.each([
    ["domain-analyst", "user_stories", "locked"],
    ["epic-architect", "user_stories", "required"],
    ["ppt-composer", "ppt", "locked"],
    ["ppt-slide-architect", "ppt", "required"],
    ["prototype-build", "prototype", "locked"],
    ["app-user-stories", "app_builder", "required"],
    ["mulesoft-inventory", "mulesoft_to_springboot", "locked"],
    ["dotnet-validation", "dotnet_to_azure", "required"],
  ] as const)("classifies %s in %s as %s", (agentId, pipeline, role) => {
    expect(getRole(agentId, pipeline)).toBe(role);
  });

  it("treats an unlisted agent as optional in any pipeline", () => {
    expect(getRole("some-custom-agent", "user_stories")).toBe("optional");
  });

  it("treats a core agent as optional in a pipeline that does not own it", () => {
    expect(getRole("domain-analyst", "ppt")).toBe("optional");
  });

  it("treats every agent as optional in the custom pipeline", () => {
    expect(getRole("domain-analyst", "custom")).toBe("optional");
  });
});

describe("getAgentInitials", () => {
  it.each([
    ["Requirements Analyst", "RA"],
    ["Solo", "SO"],
    ["Planner Agent", "PL"],
    ["Deep Code agent", "DC"],
    ["x", "X"],
  ])("derives %s as %s", (name, initials) => {
    expect(getAgentInitials(name)).toBe(initials);
  });
});

describe("PIPELINE_LABEL", () => {
  it("maps the built-in pipeline types to their display labels", () => {
    expect(PIPELINE_LABEL).toMatchObject({
      user_stories: "User Stories",
      ppt: "Presentation",
      prototype: "Prototype",
      app_builder: "App Builder",
      custom: "Custom",
    });
  });
});

describe("applyLeverPatch", () => {
  it("sets a lever on an empty selection", () => {
    expect(applyLeverPatch(undefined, { model: "m1" })).toEqual({ model: "m1" });
  });

  it.each([[undefined], [""], [[]]])("clears a lever patched with %j", (empty) => {
    expect(applyLeverPatch({ model: "m1", retry: 2 }, { model: empty as never })).toEqual({ retry: 2 });
  });

  it("auto-attaches the validation gate once, alongside existing gates", () => {
    const result = applyLeverPatch({ gates: ["approval", "validation"] }, { validators: ["code_test"] });

    expect(result.validators).toEqual(["code_test"]);
    expect(result.gates).toEqual(["approval", "validation"]);
  });

  it("adds the validation gate when only validators are selected", () => {
    expect(applyLeverPatch({}, { validators: ["code_test"] }).gates).toEqual(["validation"]);
  });

  it("does not mutate the input selection", () => {
    const current = { model: "m1" };

    applyLeverPatch(current, { retry: 3 });

    expect(current).toEqual({ model: "m1" });
  });
});

describe("tool grants helpers", () => {
  it("defaults both grants to on when no selection exists", () => {
    expect(effectiveToolGrants(undefined)).toEqual({ read_files: true, write_files: true });
    expect(hasToolOverride(undefined)).toBe(false);
  });

  it("reflects an explicitly restricted grant", () => {
    const sel = { tools: { read_files: true, write_files: false } };

    expect(effectiveToolGrants(sel)).toEqual({ read_files: true, write_files: false });
    expect(hasToolOverride(sel)).toBe(true);
  });
});

// ─── AgentPromptSection ──────────────────────────────────────────────────────

describe("AgentPromptSection", () => {
  async function openPrompt(user: ReturnType<typeof userEvent.setup>) {
    await user.click(screen.getByRole("button", { name: /system prompt/i }));
  }

  it("does not fetch the prompt until the section is opened", () => {
    renderWithProviders(<AgentPromptSection agent={AGENT} />);

    expect(api.getAgentPrompt).not.toHaveBeenCalled();
  });

  it("loads and shows the base prompt with its default badge when opened", async () => {
    const user = userEvent.setup();
    renderWithProviders(<AgentPromptSection agent={AGENT} />);

    await openPrompt(user);

    expect(await screen.findByText("You are the analyst.")).toBeInTheDocument();
    expect(api.getAgentPrompt).toHaveBeenCalledWith("tok", "requirements-analyst");
    expect(screen.getByText("Default AGENT.md")).toBeInTheDocument();
    expect(screen.getByText("Base AGENT.md prompt")).toBeInTheDocument();
  });

  it("does not fetch when there is no auth token", async () => {
    const user = userEvent.setup();
    api.getToken.mockReturnValue(null);
    renderWithProviders(<AgentPromptSection agent={AGENT} />);

    await openPrompt(user);

    expect(api.getAgentPrompt).not.toHaveBeenCalled();
    expect(screen.queryByText("Loading prompt…")).not.toBeInTheDocument();
  });

  it("shows the load error message when the fetch fails", async () => {
    const user = userEvent.setup();
    api.getAgentPrompt.mockRejectedValue(new Error("prompt service down"));
    renderWithProviders(<AgentPromptSection agent={AGENT} />);

    await openPrompt(user);

    expect(await screen.findByText("prompt service down")).toBeInTheDocument();
  });

  it("falls back to a generic message when the failure carries no message", async () => {
    const user = userEvent.setup();
    api.getAgentPrompt.mockRejectedValue(undefined);
    renderWithProviders(<AgentPromptSection agent={AGENT} />);

    await openPrompt(user);

    expect(await screen.findByText("Failed to load prompt.")).toBeInTheDocument();
  });

  it("shows a placeholder when the agent has no prompt body", async () => {
    const user = userEvent.setup();
    api.getAgentPrompt.mockResolvedValue({ agent_id: AGENT.id, prompt_body: "", override: null, has_override: false });
    renderWithProviders(<AgentPromptSection agent={AGENT} />);

    await openPrompt(user);

    expect(await screen.findByText("No prompt body found.")).toBeInTheDocument();
  });

  it("collapses the section when the header is clicked again", async () => {
    const user = userEvent.setup();
    renderWithProviders(<AgentPromptSection agent={AGENT} />);
    await openPrompt(user);
    await screen.findByText("You are the analyst.");

    await openPrompt(user);

    await waitFor(() => expect(screen.queryByText("You are the analyst.")).not.toBeInTheDocument());
  });

  it("shows the override as the displayed prompt with an overridden marker", async () => {
    const user = userEvent.setup();
    api.getAgentPrompt.mockResolvedValue({
      agent_id: AGENT.id,
      prompt_body: "Base.",
      override: "My override.",
      has_override: true,
    });
    renderWithProviders(<AgentPromptSection agent={AGENT} />);

    await openPrompt(user);

    expect(await screen.findByText("My override.")).toBeInTheDocument();
    expect(screen.getByText("Your override")).toBeInTheDocument();
    expect(screen.getByText("overridden")).toBeInTheDocument();
    expect(screen.getByText("Custom override active")).toBeInTheDocument();
  });

  describe("editing (writes enabled)", () => {
    async function startEditing(user: ReturnType<typeof userEvent.setup>) {
      renderWithProviders(<AgentPromptSection agent={AGENT} />);
      await openPrompt(user);
      await screen.findByText("You are the analyst.");
      await user.click(screen.getByRole("button", { name: "Edit" }));
      return screen.getByRole("textbox", { name: "Custom agent prompt" });
    }

    it("seeds the editor with the base prompt and shows a character count", async () => {
      const user = userEvent.setup();

      const editor = await startEditing(user);

      expect(editor).toHaveValue("You are the analyst.");
      expect(screen.getByText("20 chars · max 32,768")).toBeInTheDocument();
    });

    it("seeds the editor with an existing override instead of the base prompt", async () => {
      const user = userEvent.setup();
      api.getAgentPrompt.mockResolvedValue({
        agent_id: AGENT.id,
        prompt_body: "Base.",
        override: "Old override.",
        has_override: true,
      });
      renderWithProviders(<AgentPromptSection agent={AGENT} />);
      await openPrompt(user);
      await screen.findByText("Old override.");

      await user.click(screen.getByRole("button", { name: "Edit" }));

      expect(screen.getByRole("textbox", { name: "Custom agent prompt" })).toHaveValue("Old override.");
    });

    it("discards the draft on Cancel without saving", async () => {
      const user = userEvent.setup();
      const editor = await startEditing(user);
      await user.type(editor, " extra");

      await user.click(screen.getByRole("button", { name: "Cancel" }));

      expect(screen.queryByRole("textbox", { name: "Custom agent prompt" })).not.toBeInTheDocument();
      expect(screen.getByText("You are the analyst.")).toBeInTheDocument();
      expect(api.saveAgentPromptOverride).not.toHaveBeenCalled();
    });

    it("disables Save override while the draft is blank", async () => {
      const user = userEvent.setup();
      const editor = await startEditing(user);

      await user.clear(editor);

      expect(screen.getByRole("button", { name: /save override/i })).toBeDisabled();
    });

    it("saves the draft and shows it as the active override", async () => {
      const user = userEvent.setup();
      const editor = await startEditing(user);
      await user.clear(editor);
      await user.type(editor, "Be concise.");

      await user.click(screen.getByRole("button", { name: /save override/i }));

      expect(await screen.findByText("Your override")).toBeInTheDocument();
      expect(api.saveAgentPromptOverride).toHaveBeenCalledWith("tok", "requirements-analyst", "Be concise.");
      expect(screen.getByText("Be concise.")).toBeInTheDocument();
      expect(screen.queryByRole("textbox", { name: "Custom agent prompt" })).not.toBeInTheDocument();
    });

    it("shows Saving… and disables the button while the save is pending", async () => {
      const user = userEvent.setup();
      api.saveAgentPromptOverride.mockReturnValue(new Promise(() => undefined));
      await startEditing(user);

      await user.click(screen.getByRole("button", { name: /save override/i }));

      expect(await screen.findByRole("button", { name: "Saving…" })).toBeDisabled();
    });

    it("shows the save error and stays in the editor when saving fails", async () => {
      const user = userEvent.setup();
      api.saveAgentPromptOverride.mockRejectedValue(new Error("too long"));
      await startEditing(user);

      await user.click(screen.getByRole("button", { name: /save override/i }));

      expect(await screen.findByText("too long")).toBeInTheDocument();
      expect(screen.getByRole("textbox", { name: "Custom agent prompt" })).toBeInTheDocument();
    });

    it("falls back to a generic save error when the failure has no message", async () => {
      const user = userEvent.setup();
      api.saveAgentPromptOverride.mockRejectedValue(undefined);
      await startEditing(user);

      await user.click(screen.getByRole("button", { name: /save override/i }));

      expect(await screen.findByText("Failed to save.")).toBeInTheDocument();
    });

    it("does not call the API when the token disappears before saving", async () => {
      const user = userEvent.setup();
      await startEditing(user);
      api.getToken.mockReturnValue(null);

      await user.click(screen.getByRole("button", { name: /save override/i }));

      expect(api.saveAgentPromptOverride).not.toHaveBeenCalled();
    });
  });

  describe("reverting an override", () => {
    beforeEach(() => {
      api.getAgentPrompt.mockResolvedValue({
        agent_id: AGENT.id,
        prompt_body: "Base.",
        override: "Custom.",
        has_override: true,
      });
    });

    async function openOverridden(user: ReturnType<typeof userEvent.setup>) {
      renderWithProviders(<AgentPromptSection agent={AGENT} />);
      await openPrompt(user);
      await screen.findByText("Custom.");
    }

    it("deletes the override and returns to the base prompt", async () => {
      const user = userEvent.setup();
      await openOverridden(user);

      await user.click(screen.getByRole("button", { name: /revert to default/i }));

      expect(await screen.findByText("Base.")).toBeInTheDocument();
      expect(api.deleteAgentPromptOverride).toHaveBeenCalledWith("tok", "requirements-analyst");
      expect(screen.getByText("Default AGENT.md")).toBeInTheDocument();
    });

    it("keeps the override when the delete fails", async () => {
      const user = userEvent.setup();
      api.deleteAgentPromptOverride.mockRejectedValue(new Error("nope"));
      await openOverridden(user);

      await user.click(screen.getByRole("button", { name: /revert to default/i }));

      await waitFor(() => expect(api.deleteAgentPromptOverride).toHaveBeenCalledTimes(1));
      expect(screen.getByText("Custom.")).toBeInTheDocument();
      expect(screen.getByText("Your override")).toBeInTheDocument();
    });

    it("does not call the API when the token disappears before reverting", async () => {
      const user = userEvent.setup();
      await openOverridden(user);
      api.getToken.mockReturnValue(null);

      await user.click(screen.getByRole("button", { name: /revert to default/i }));

      expect(api.deleteAgentPromptOverride).not.toHaveBeenCalled();
    });
  });

  describe("surface-only mode", () => {
    it("shows the prompt but offers no Edit or Revert controls", async () => {
      const user = userEvent.setup();
      api.getAgentPrompt.mockResolvedValue({
        agent_id: AGENT.id,
        prompt_body: "Base.",
        override: "Custom.",
        has_override: true,
      });
      renderWithProviders(<AgentPromptSection agent={AGENT} surfaceOnly />);

      await openPrompt(user);

      expect(await screen.findByText("Custom.")).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /revert to default/i })).not.toBeInTheDocument();
    });
  });
});

// ─── AgentCapabilitiesModal ──────────────────────────────────────────────────

describe("AgentCapabilitiesModal", () => {
  function renderModal(
    props: Partial<React.ComponentProps<typeof AgentCapabilitiesModal>> = {},
    catalogs: { hooks?: GlobalHookEntry[]; skills?: GlobalSkillEntry[] } = {},
  ) {
    const onClose = props.onClose ?? vi.fn();
    const view = renderWithProviders(
      <AgentCapabilitiesModal agent={AGENT} agentIndex={0} {...props} onClose={onClose} />,
      { preloadedState: catalogState(catalogs.hooks, catalogs.skills) },
    );
    return { ...view, onClose };
  }

  describe("overview tab", () => {
    it("shows the agent identity, duration, pipeline label and skill-support chip", () => {
      renderModal();

      expect(screen.getByRole("heading", { name: "Requirements Analyst" })).toBeInTheDocument();
      expect(screen.getAllByText("analyst").length).toBeGreaterThan(0);
      expect(screen.getByText("~30s")).toBeInTheDocument();
      expect(screen.getAllByText("Prototype").length).toBeGreaterThan(0);
      expect(screen.getByText("Skill support")).toBeInTheDocument();
      expect(screen.getByText("RA")).toBeInTheDocument();
    });

    it("omits the skill-support chip when the agent declares no skill", () => {
      renderModal({ agent: makeAgent({ has_skill: false }) });

      expect(screen.queryByText("Skill support")).not.toBeInTheDocument();
    });

    it("splits a multi-clause description into separate capability lines", () => {
      renderModal();

      expect(screen.getByText("Analyzes requirements and produces a spec")).toBeInTheDocument();
      expect(screen.getByText("drafts acceptance criteria.")).toBeInTheDocument();
    });

    it("shows a short description whole as a single capability", () => {
      renderModal({ agent: makeAgent({ description: "Does one thing." }) });

      expect(screen.getByText("Does one thing.")).toBeInTheDocument();
    });

    it("shows at most five capability lines", () => {
      const clauses = Array.from({ length: 7 }, (_, i) => `capability number ${i + 1}`);
      renderModal({ agent: makeAgent({ description: clauses.join(", ") }) });

      expect(screen.getAllByText(/^capability number \d$/)).toHaveLength(5);
    });

    it("uses the first pipeline type for a multi-pipeline agent", () => {
      renderModal({ agent: makeAgent({ pipeline_type: ["ppt", "prototype"] }) });

      expect(screen.getAllByText("Presentation").length).toBeGreaterThan(0);
    });

    it("falls back to the raw pipeline type when it has no label", () => {
      renderModal({ agent: makeAgent({ pipeline_type: "weird_flow" }) });

      expect(screen.getAllByText("weird_flow").length).toBeGreaterThan(0);
    });

    it("lists attached skills by catalog name and falls back to the id for unknown skills", () => {
      renderModal(
        { agent: makeAgent({ skills: ["s1", "ghost"] }), onSkillsChange: vi.fn() },
        { skills: [makeSkill("s1")] },
      );

      expect(screen.getByText("Attached skills")).toBeInTheDocument();
      expect(screen.getByText("Skill s1")).toBeInTheDocument();
      expect(screen.getByText("ghost")).toBeInTheDocument();
    });

    it("hides the attached-skills block when the agent has none", () => {
      renderModal();

      expect(screen.queryByText("Attached skills")).not.toBeInTheDocument();
    });
  });

  describe("dismissal and shell", () => {
    it("closes on Escape", async () => {
      const user = userEvent.setup();
      const { onClose } = renderModal();

      await user.keyboard("{Escape}");

      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it("closes from the header close button", async () => {
      const user = userEvent.setup();
      const { onClose } = renderModal();
      const dialog = screen.getByRole("dialog", { name: "Requirements Analyst details" });

      // Icon-only close button with no accessible name: the first button in the dialog.
      await user.click(within(dialog).getAllByRole("button")[0]);

      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it("closes when the backdrop is clicked but not when the panel is", async () => {
      const user = userEvent.setup();
      const { onClose } = renderModal();
      const dialog = screen.getByRole("dialog", { name: "Requirements Analyst details" });

      await user.click(dialog);
      expect(onClose).not.toHaveBeenCalled();

      await user.click(dialog.parentElement as HTMLElement);
      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it("exposes a drawer test id only in drawer mode", () => {
      const { unmount } = renderModal({ asDrawer: true });
      expect(screen.getByTestId("agent-drawer")).toBeInTheDocument();
      unmount();

      renderModal({ asDrawer: false });
      expect(screen.queryByTestId("agent-drawer")).not.toBeInTheDocument();
    });
  });

  describe("hooks tab", () => {
    const HOOKS = [
      makeHook("h1"),
      makeHook("h2", { compatible_agents: ["requirements-analyst"] }),
      makeHook("h3", { compatible_agents: ["someone-else"] }),
    ];

    it("suggests hooks compatible with the agent, treating an empty list as compatible with all", async () => {
      const user = userEvent.setup();
      renderModal({}, { hooks: HOOKS });

      await user.click(screen.getByRole("tab", { name: "Hooks" }));

      expect(screen.getByText("Hook h1")).toBeInTheDocument();
      expect(screen.getByText("Hook h2")).toBeInTheDocument();
      expect(screen.queryByText("Hook h3")).not.toBeInTheDocument();
    });

    it("suggests at most three hooks", async () => {
      const user = userEvent.setup();
      renderModal({}, { hooks: [makeHook("a"), makeHook("b"), makeHook("c"), makeHook("d")] });

      await user.click(screen.getByRole("tab", { name: "Hooks" }));

      expect(screen.getAllByRole("button", { name: /attach/i })).toHaveLength(3);
    });

    it("attaches a hook and then shows it as added and disabled", async () => {
      const user = userEvent.setup();
      renderModal({}, { hooks: [makeHook("h1")] });
      await user.click(screen.getByRole("tab", { name: "Hooks" }));

      await user.click(screen.getByRole("button", { name: /attach/i }));

      expect(screen.getByRole("button", { name: /added/i })).toBeDisabled();
    });

    it("shows an empty state when no hook is suggested", async () => {
      const user = userEvent.setup();
      renderModal({}, { hooks: [makeHook("h3", { compatible_agents: ["someone-else"] })] });

      await user.click(screen.getByRole("tab", { name: "Hooks" }));

      expect(screen.getByText("No suggested hooks")).toBeInTheDocument();
    });
  });

  describe("skills tab", () => {
    const SKILLS = [makeSkill("s1"), makeSkill("s2", { compatible_agents: ["someone-else"] })];

    it("is read-only when no onSkillsChange handler is supplied", async () => {
      const user = userEvent.setup();
      renderModal({}, { skills: SKILLS });

      await user.click(screen.getByRole("tab", { name: "Skills" }));

      expect(screen.getByRole("button", { name: "Add Skill s1" })).toBeDisabled();
      expect(screen.getByText("Attach skills to this agent in the workflow composer.")).toBeInTheDocument();
    });

    it("lists only compatible skills and reports an attach through onSkillsChange", async () => {
      const user = userEvent.setup();
      const onSkillsChange = vi.fn();
      renderModal({ onSkillsChange }, { skills: SKILLS });
      await user.click(screen.getByRole("tab", { name: "Skills" }));
      expect(screen.queryByText("Skill s2")).not.toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: "Add Skill s1" }));

      expect(onSkillsChange).toHaveBeenCalledWith("requirements-analyst", ["s1"]);
      expect(screen.getByRole("button", { name: "Remove Skill s1" })).toBeInTheDocument();
    });

    it("accumulates picks so a second toggle keeps the first", async () => {
      const user = userEvent.setup();
      const onSkillsChange = vi.fn();
      renderModal({ onSkillsChange }, { skills: [makeSkill("s1"), makeSkill("s3")] });
      await user.click(screen.getByRole("tab", { name: "Skills" }));

      await user.click(screen.getByRole("button", { name: "Add Skill s1" }));
      await user.click(screen.getByRole("button", { name: "Add Skill s3" }));

      expect(onSkillsChange).toHaveBeenLastCalledWith("requirements-analyst", ["s1", "s3"]);
    });

    it("shows a newly attached skill as a chip on the overview tab", async () => {
      const user = userEvent.setup();
      renderModal({ onSkillsChange: vi.fn() }, { skills: SKILLS });
      await user.click(screen.getByRole("tab", { name: "Skills" }));
      await user.click(screen.getByRole("button", { name: "Add Skill s1" }));

      await user.click(screen.getByRole("tab", { name: "Overview" }));

      expect(screen.getByText("Attached skills")).toBeInTheDocument();
    });
  });

  describe("config tab", () => {
    async function openConfig(
      user: ReturnType<typeof userEvent.setup>,
      props: Partial<React.ComponentProps<typeof AgentCapabilitiesModal>> = {},
    ) {
      const view = renderModal(props);
      await user.click(screen.getByRole("tab", { name: "Config" }));
      return view;
    }

    async function chooseOption(
      user: ReturnType<typeof userEvent.setup>,
      lever: string,
      option: string,
    ) {
      await user.click(screen.getByRole("button", { name: `${lever} for Requirements Analyst` }));
      await user.click(await screen.findByRole("option", { name: option }));
    }

    it("reports a model choice through onSelectionsChange", async () => {
      const user = userEvent.setup();
      const onSelectionsChange = vi.fn();
      await openConfig(user, { onSelectionsChange, token: "tok" });

      await chooseOption(user, "Model", "Basic Model");

      expect(onSelectionsChange).toHaveBeenLastCalledWith({
        "requirements-analyst": { model: "model-basic" },
      });
    });

    it("seeds the levers from initialSelections", async () => {
      const user = userEvent.setup();
      await openConfig(user, {
        initialSelections: { "requirements-analyst": { retry: 2 } },
      });

      expect(screen.getByRole("button", { name: "Retry for Requirements Analyst" })).toHaveTextContent("2 attempts");
    });

    it("offers an Effort lever only for a model that declares reasoning levels", async () => {
      const user = userEvent.setup();
      await openConfig(user);
      expect(screen.queryByRole("button", { name: "Effort for Requirements Analyst" })).not.toBeInTheDocument();

      await chooseOption(user, "Model", "Thinker Model");

      await user.click(screen.getByRole("button", { name: "Effort for Requirements Analyst" }));
      const levels = within(screen.getByRole("listbox", { name: "Effort for Requirements Analyst" }))
        .getAllByRole("option")
        .map((o) => o.textContent);
      expect(levels).toEqual(["Default", "None", "Low", "xHigh"]);
    });

    it("records the chosen effort level", async () => {
      const user = userEvent.setup();
      const onSelectionsChange = vi.fn();
      await openConfig(user, { onSelectionsChange });
      await chooseOption(user, "Model", "Thinker Model");

      await chooseOption(user, "Effort", "Low");

      expect(onSelectionsChange).toHaveBeenLastCalledWith({
        "requirements-analyst": { model: "model-thinker", effort: "low" },
      });
    });

    it("couples the validation gate to a chosen validator and hides it from the gate list", async () => {
      const user = userEvent.setup();
      const onSelectionsChange = vi.fn();
      await openConfig(user, { onSelectionsChange });
      await screen.findByRole("checkbox", { name: /Before execute: Approval gate/ });

      await chooseOption(user, "Validator", "code_test");

      expect(onSelectionsChange).toHaveBeenLastCalledWith({
        "requirements-analyst": { validators: ["code_test"], gates: ["validation"] },
      });
      expect(screen.queryByRole("checkbox", { name: /validation/i })).not.toBeInTheDocument();
    });

    it("clears the validator when Default is chosen again", async () => {
      const user = userEvent.setup();
      const onSelectionsChange = vi.fn();
      await openConfig(user, { onSelectionsChange });
      await chooseOption(user, "Validator", "code_test");

      await chooseOption(user, "Validator", "Default");

      expect(onSelectionsChange.mock.calls.at(-1)?.[0]["requirements-analyst"]).not.toHaveProperty("validators");
    });

    it("groups gates by phase and toggles them independently", async () => {
      const user = userEvent.setup();
      const onSelectionsChange = vi.fn();
      await openConfig(user, { onSelectionsChange });

      await user.click(await screen.findByRole("checkbox", { name: /Before execute: Security gate/ }));
      await user.click(screen.getByRole("checkbox", { name: /After execute: Conditional gate/ }));

      expect(onSelectionsChange).toHaveBeenLastCalledWith({
        "requirements-analyst": { gates: ["security", "conditional"] },
      });

      await user.click(screen.getByRole("checkbox", { name: /Before execute: Security gate/ }));
      expect(onSelectionsChange).toHaveBeenLastCalledWith({
        "requirements-analyst": { gates: ["conditional"] },
      });
    });

    it("allows only one human-review gate per step", async () => {
      const user = userEvent.setup();
      await openConfig(user);

      await user.click(await screen.findByRole("checkbox", { name: /Before execute: Approval gate/ }));

      expect(screen.getByRole("checkbox", { name: /After execute: Human gate/ })).toBeDisabled();
    });

    it("records a retry count as a number", async () => {
      const user = userEvent.setup();
      const onSelectionsChange = vi.fn();
      await openConfig(user, { onSelectionsChange });

      await chooseOption(user, "Retry", "3 attempts");

      expect(onSelectionsChange).toHaveBeenLastCalledWith({
        "requirements-analyst": { retry: 3 },
      });
    });

    it("labels the single-attempt retry option in the singular", async () => {
      const user = userEvent.setup();
      await openConfig(user);

      await user.click(screen.getByRole("button", { name: "Retry for Requirements Analyst" }));

      expect(await screen.findByRole("option", { name: "1 attempt" })).toBeInTheDocument();
    });

    it("closes an open lever list on an outside click and when its trigger is pressed again", async () => {
      const user = userEvent.setup();
      await openConfig(user);
      const trigger = screen.getByRole("button", { name: "Retry for Requirements Analyst" });

      await user.click(trigger);
      expect(screen.getByRole("listbox", { name: "Retry for Requirements Analyst" })).toBeInTheDocument();
      await user.click(document.body);
      expect(screen.queryByRole("listbox")).not.toBeInTheDocument();

      await user.click(trigger);
      await user.click(trigger);
      expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    });

    it("shows the capability load error instead of the levers", async () => {
      const user = userEvent.setup();
      api.getCapabilities.mockRejectedValue(new Error("registry offline"));
      await openConfig(user);

      expect(await screen.findByText("registry offline")).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Model for Requirements Analyst" })).not.toBeInTheDocument();
    });

    it("reports not-authenticated when there is no token", async () => {
      const user = userEvent.setup();
      api.getToken.mockReturnValue(null);
      await openConfig(user);

      expect(await screen.findByText("Not authenticated.")).toBeInTheDocument();
    });

    it("clears every lever and reports an empty map on Reset", async () => {
      const user = userEvent.setup();
      const onSelectionsChange = vi.fn();
      await openConfig(user, { onSelectionsChange });
      await chooseOption(user, "Retry", "2 attempts");

      await user.click(screen.getByRole("button", { name: "Reset" }));

      expect(onSelectionsChange).toHaveBeenLastCalledWith({});
      expect(screen.getByRole("button", { name: "Retry for Requirements Analyst" })).toHaveTextContent("Default");
    });

    it("confirms Save agent, reports the selections and closes after the confirmation delay", async () => {
      const user = userEvent.setup();
      const onSelectionsChange = vi.fn();
      const { onClose } = await openConfig(user, { onSelectionsChange });
      await chooseOption(user, "Retry", "2 attempts");
      onSelectionsChange.mockClear();

      // Fake timers go on only for the timer-owned close; RTL's async wrapper
      // around user-event waits on a real setTimeout and would hang, so the
      // click is dispatched with fireEvent (wrapped in act by RTL).
      vi.useFakeTimers();
      fireEvent.click(screen.getByRole("button", { name: "Save agent" }));

      expect(onSelectionsChange).toHaveBeenCalledWith({ "requirements-analyst": { retry: 2 } });
      expect(screen.getByRole("button", { name: "✓ Saved" })).toBeDisabled();
      expect(onClose).not.toHaveBeenCalled();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(900);
      });

      expect(onClose).toHaveBeenCalledTimes(1);
    });
  });
});

// ─── HooksTab ────────────────────────────────────────────────────────────────

describe("HooksTab", () => {
  const HOOKS = [
    makeHook("alpha", { event: "PreToolUse", description: "Guards writes" }),
    makeHook("beta", { event: "Stop", description: "Runs at the end" }),
  ];

  function renderTab(hooks: GlobalHookEntry[] = HOOKS) {
    return renderWithProviders(<HooksTab pipelineType="prototype" />, {
      preloadedState: catalogState(hooks),
    });
  }

  it("shows the empty hint while nothing is attached and the picker is closed", () => {
    renderTab();

    expect(screen.getByText(/No hooks attached/)).toBeInTheDocument();
  });

  it("opens the picker listing every hook and closes it with Done", async () => {
    const user = userEvent.setup();
    renderTab();

    await user.click(screen.getByRole("button", { name: /add hook/i }));
    expect(screen.getByText("Hook alpha")).toBeInTheDocument();
    expect(screen.getByText("Hook beta")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Done" }));
    expect(screen.queryByText("Hook alpha")).not.toBeInTheDocument();
  });

  it("toggles the picker closed from the Add hook button", async () => {
    const user = userEvent.setup();
    renderTab();
    const toggle = screen.getByRole("button", { name: /add hook/i });

    await user.click(toggle);
    await user.click(toggle);

    expect(screen.queryByRole("textbox", { name: "Search hooks" })).not.toBeInTheDocument();
  });

  it("filters hooks by search text over name and description", async () => {
    const user = userEvent.setup();
    renderTab();
    await user.click(screen.getByRole("button", { name: /add hook/i }));

    await user.type(screen.getByRole("textbox", { name: "Search hooks" }), "GUARDS");

    expect(screen.getByText("Hook alpha")).toBeInTheDocument();
    expect(screen.queryByText("Hook beta")).not.toBeInTheDocument();
  });

  it("filters hooks by event", async () => {
    const user = userEvent.setup();
    renderTab();
    await user.click(screen.getByRole("button", { name: /add hook/i }));

    await user.click(screen.getByRole("button", { name: "Stop" }));

    expect(screen.queryByText("Hook alpha")).not.toBeInTheDocument();
    expect(screen.getByText("Hook beta")).toBeInTheDocument();
  });

  it("shows a no-results message when nothing matches", async () => {
    const user = userEvent.setup();
    renderTab();
    await user.click(screen.getByRole("button", { name: /add hook/i }));

    await user.type(screen.getByRole("textbox", { name: "Search hooks" }), "zzz-nothing");

    expect(screen.getByText("No hooks found")).toBeInTheDocument();
  });

  it("attaches a hook, lists it with a count badge, and detaches it again", async () => {
    const user = userEvent.setup();
    renderTab();
    await user.click(screen.getByRole("button", { name: /add hook/i }));

    // The picker's per-row button is named exactly "Add" (the toggle is "Add hook").
    await user.click(screen.getAllByRole("button", { name: "Add" })[0]);

    expect(screen.getByRole("button", { name: /added/i })).toBeDisabled();
    expect(screen.getByText("1")).toBeInTheDocument();

    // With the picker closed only the attached row remains. Its remove control
    // is icon-only (no accessible name), so it is the one button without text.
    await user.click(screen.getByRole("button", { name: "Done" }));
    const [removeButton] = screen.getAllByRole("button").filter((b) => !b.textContent?.trim());
    await user.click(removeButton);

    expect(screen.queryByText("1")).not.toBeInTheDocument();
    expect(screen.getByText(/No hooks attached/)).toBeInTheDocument();
  });
});

// ─── CapabilityPaletteSection gaps ───────────────────────────────────────────

describe("CapabilityPaletteSection (additional states)", () => {
  it("reports not-authenticated without a token", async () => {
    api.getToken.mockReturnValue(null);

    renderWithProviders(<CapabilityPaletteSection />);

    expect(await screen.findByText("Not authenticated.")).toBeInTheDocument();
    expect(api.getCapabilities).not.toHaveBeenCalled();
  });

  it("uses an explicit token over the stored one", async () => {
    api.getToken.mockReturnValue(null);

    renderWithProviders(<CapabilityPaletteSection token="explicit" />);

    await screen.findByText("code_test");
    expect(api.getCapabilities).toHaveBeenCalledWith("explicit");
  });

  it("shows a fallback message when the fetch fails without a message", async () => {
    api.getCapabilities.mockRejectedValue(undefined);

    renderWithProviders(<CapabilityPaletteSection />);

    expect(await screen.findByText("Failed to load capabilities.")).toBeInTheDocument();
  });

  it("lists the opened workflow's declared capabilities per step", async () => {
    renderWithProviders(
      <CapabilityPaletteSection
        declaredCapabilities={[{ step: "plan", capabilities: ["validator:code_test", "gate:approval"] }]}
      />,
    );

    expect(await screen.findByText("Declared by this workflow")).toBeInTheDocument();
    expect(screen.getByText("plan")).toBeInTheDocument();
    expect(screen.getByText("validator:code_test · gate:approval")).toBeInTheDocument();
  });

  it("omits the declared strip for an empty declaration", async () => {
    renderWithProviders(<CapabilityPaletteSection declaredCapabilities={[]} />);

    await screen.findByText("code_test");
    expect(screen.queryByText("Declared by this workflow")).not.toBeInTheDocument();
  });

  it("expands and collapses a capability's config schema with required and typed fields", async () => {
    const user = userEvent.setup();
    api.getCapabilities.mockResolvedValue({
      capabilities: [
        {
          kind: "validator",
          name: "schema_cap",
          user_allowed: true,
          description: "",
          security_gated: false,
          config_schema: { path: { type: "string", required: true }, flag: "free-form", count: { type: 3 } },
        },
      ],
      model_catalog: [],
    });
    renderWithProviders(<CapabilityPaletteSection />);
    const toggle = await screen.findByRole("button", { name: "Configuration for schema_cap" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    await user.click(toggle);

    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("path")).toBeInTheDocument();
    expect(screen.getByText("string")).toBeInTheDocument();
    expect(screen.getByText("*")).toBeInTheDocument();
    expect(screen.getByText("flag")).toBeInTheDocument();

    await user.click(toggle);
    expect(screen.queryByText("string")).not.toBeInTheDocument();
  });

  it.each([
    ["strategy", "Strategies"],
    ["gate", "Gates"],
    ["match", "Matches"],
    ["task_parser", "Task parsers"],
    ["bus", "Buses"],
  ])("titles the %s group as %s", async (kind, heading) => {
    api.getCapabilities.mockResolvedValue({
      capabilities: [{ kind, name: "x", user_allowed: true, description: "", security_gated: false, config_schema: {} }],
      model_catalog: [],
    });

    renderWithProviders(<CapabilityPaletteSection />);

    expect(await screen.findByRole("group", { name: heading })).toBeInTheDocument();
  });
});

// ─── AdvancedExpander gaps ───────────────────────────────────────────────────

describe("AdvancedExpander (additional behaviour)", () => {
  const AGENTS = [
    { id: "agent-a", name: "Agent A" },
    { id: "agent-b", name: "Agent B" },
  ];

  async function open(user: ReturnType<typeof userEvent.setup>, name: string) {
    await user.click(await screen.findByRole("button", { name: new RegExp(`Advanced — ${name}`) }));
  }

  function lastSelections(fn: ReturnType<typeof vi.fn>): SelectionsMap {
    return fn.mock.calls.at(-1)?.[0] as SelectionsMap;
  }

  it("shows a loading message while the palette is being fetched", () => {
    api.getCapabilities.mockReturnValue(new Promise(() => undefined));

    renderWithProviders(<AdvancedExpander agents={AGENTS} />);

    expect(screen.getByText("Loading levers…")).toBeInTheDocument();
  });

  it("shows the error when the palette cannot be loaded", async () => {
    api.getCapabilities.mockRejectedValue(new Error("palette down"));

    renderWithProviders(<AdvancedExpander agents={AGENTS} />);

    expect(await screen.findByText("palette down")).toBeInTheDocument();
  });

  it("shows a not-authenticated error without a token", async () => {
    api.getToken.mockReturnValue(null);

    renderWithProviders(<AdvancedExpander agents={AGENTS} />);

    expect(await screen.findByText("Not authenticated.")).toBeInTheDocument();
  });

  it.each([
    ["resolves", (d: { resolve: (v: unknown) => void; reject: (e: unknown) => void }) => d.resolve(PALETTE)],
    ["rejects", (d: { resolve: (v: unknown) => void; reject: (e: unknown) => void }) => d.reject(new Error("late"))],
  ])("ignores a palette request that %s after the expander unmounted", async (_label, settle) => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    let deferred!: { resolve: (v: unknown) => void; reject: (e: unknown) => void };
    api.getCapabilities.mockReturnValue(
      new Promise((resolve, reject) => {
        deferred = { resolve, reject };
      }),
    );
    const { unmount } = renderWithProviders(<AdvancedExpander agents={AGENTS} />);
    unmount();

    await act(async () => {
      settle(deferred);
    });

    expect(consoleError).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });

  it("asks the user to add agents when there are none", async () => {
    renderWithProviders(<AdvancedExpander agents={[]} />);

    expect(await screen.findByText("Add agents to assign per-agent levers.")).toBeInTheDocument();
  });

  it("shows tool grants outside the disclosure and records a restricted grant", async () => {
    const user = userEvent.setup();
    const onSelectionsChange = vi.fn();
    renderWithProviders(<AdvancedExpander agents={AGENTS} onSelectionsChange={onSelectionsChange} />);

    const write = await screen.findByRole("checkbox", { name: "Write files for Agent A" });
    expect(write).toBeChecked();
    await user.click(write);

    expect(lastSelections(onSelectionsChange)).toEqual({
      "agent-a": { tools: { read_files: true, write_files: false } },
    });
    expect(screen.getByRole("checkbox", { name: "Write files for Agent A" })).not.toBeChecked();
  });

  it("keeps execute commands fixed off and disabled", async () => {
    renderWithProviders(<AdvancedExpander agents={AGENTS} />);

    const exec = await screen.findByRole("checkbox", { name: "Execute commands for Agent A" });

    expect(exec).toBeDisabled();
    expect(exec).not.toBeChecked();
  });

  it("seeds tool grants from initialSelections", async () => {
    renderWithProviders(
      <AdvancedExpander
        agents={AGENTS}
        initialSelections={{ "agent-a": { tools: { read_files: false, write_files: true } } }}
      />,
    );

    expect(await screen.findByRole("checkbox", { name: "Read files for Agent A" })).not.toBeChecked();
  });

  it("collapses an expanded agent when its header is clicked again", async () => {
    const user = userEvent.setup();
    renderWithProviders(<AdvancedExpander agents={AGENTS} />);
    await open(user, "Agent A");
    expect(screen.getByLabelText("Retry for Agent A")).toBeInTheDocument();

    await open(user, "Agent A");

    expect(screen.queryByLabelText("Retry for Agent A")).not.toBeInTheDocument();
  });

  it("keeps the coupled validation gate when a gate is picked after a validator", async () => {
    const user = userEvent.setup();
    const onSelectionsChange = vi.fn();
    renderWithProviders(<AdvancedExpander agents={AGENTS} onSelectionsChange={onSelectionsChange} />);
    await open(user, "Agent A");
    await user.selectOptions(screen.getByLabelText("Validator for Agent A"), "code_test");

    await user.selectOptions(screen.getByLabelText("Gate for Agent A"), "approval");

    expect(lastSelections(onSelectionsChange)["agent-a"].gates).toEqual(["validation", "approval"]);
    expect(screen.getByLabelText("Gate for Agent A")).toHaveValue("approval");
  });

  it("clears a picked gate when Default is selected", async () => {
    const user = userEvent.setup();
    const onSelectionsChange = vi.fn();
    renderWithProviders(<AdvancedExpander agents={AGENTS} onSelectionsChange={onSelectionsChange} />);
    await open(user, "Agent A");
    await user.selectOptions(screen.getByLabelText("Gate for Agent A"), "approval");

    await user.selectOptions(screen.getByLabelText("Gate for Agent A"), "");

    expect(lastSelections(onSelectionsChange)).toEqual({});
  });

  it("shows tier, context window and description for the picked model", async () => {
    const user = userEvent.setup();
    renderWithProviders(<AdvancedExpander agents={AGENTS} />);
    await open(user, "Agent A");

    await user.selectOptions(screen.getByLabelText("Model for Agent A"), "model-basic");

    expect(screen.getByText("fast")).toBeInTheDocument();
    expect(screen.getByText("200K ctx")).toBeInTheDocument();
    expect(screen.getByText("Cheap and quick.")).toBeInTheDocument();
  });

  it("formats a million-token context window in millions", async () => {
    const user = userEvent.setup();
    renderWithProviders(<AdvancedExpander agents={AGENTS} />);
    await open(user, "Agent A");

    await user.selectOptions(screen.getByLabelText("Model for Agent A"), "model-thinker");

    expect(screen.getByText("1M ctx")).toBeInTheDocument();
  });

  it("offers an Effort select with labelled levels only for a reasoning model", async () => {
    const user = userEvent.setup();
    const onSelectionsChange = vi.fn();
    renderWithProviders(<AdvancedExpander agents={AGENTS} onSelectionsChange={onSelectionsChange} />);
    await open(user, "Agent A");
    await user.selectOptions(screen.getByLabelText("Model for Agent A"), "model-basic");
    expect(screen.queryByLabelText("Effort for Agent A")).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Model for Agent A"), "model-thinker");
    const effort = screen.getByLabelText("Effort for Agent A") as HTMLSelectElement;
    expect(Array.from(effort.options).map((o) => o.textContent)).toEqual(["Default", "None", "Low", "xHigh"]);
    await user.selectOptions(effort, "xhigh");

    expect(lastSelections(onSelectionsChange)["agent-a"]).toEqual({ model: "model-thinker", effort: "xhigh" });
  });

  it("records the retry lever as a number and clears it on Default", async () => {
    const user = userEvent.setup();
    const onSelectionsChange = vi.fn();
    renderWithProviders(<AdvancedExpander agents={AGENTS} onSelectionsChange={onSelectionsChange} />);
    await open(user, "Agent A");

    await user.selectOptions(screen.getByLabelText("Retry for Agent A"), "3");
    expect(lastSelections(onSelectionsChange)["agent-a"].retry).toBe(3);

    await user.selectOptions(screen.getByLabelText("Retry for Agent A"), "");
    expect(lastSelections(onSelectionsChange)).toEqual({});
  });

  it("clears the validator and its coupling notice when Default is chosen", async () => {
    const user = userEvent.setup();
    renderWithProviders(<AdvancedExpander agents={AGENTS} />);
    await open(user, "Agent A");
    await user.selectOptions(screen.getByLabelText("Validator for Agent A"), "code_test");
    expect(screen.getByRole("status")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Validator for Agent A"), "");

    expect(screen.getByLabelText("Validator for Agent A")).toHaveValue("");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  describe("fan-out modes", () => {
    // Three agents so the last one has two earlier steps to choose a source from;
    // its default source is the nearest earlier step, agent-b.
    const THREE = [...AGENTS, { id: "agent-c", name: "Agent C" }];

    async function enableFanout(user: ReturnType<typeof userEvent.setup>, onSelectionsChange: () => void) {
      renderWithProviders(<AdvancedExpander agents={THREE} onSelectionsChange={onSelectionsChange} />);
      await open(user, "Agent C");
      await user.click(screen.getByRole("checkbox", { name: "Fan out over a list for Agent C" }));
    }

    it("switches to the one-at-a-time shape with a heading-task source", async () => {
      const user = userEvent.setup();
      const onSelectionsChange = vi.fn();
      await enableFanout(user, onSelectionsChange);

      await user.selectOptions(screen.getByLabelText("Fan-out mode for Agent C"), "task_loop");

      expect(lastSelections(onSelectionsChange)["agent-c"]).toEqual({
        strategy: "task_loop",
        task_source: { kind: "parsed", parser: "heading_tasks", source_step: "agent-b" },
      });
    });

    it("keeps the json parser and target when the source changes in wave mode", async () => {
      const user = userEvent.setup();
      const onSelectionsChange = vi.fn();
      await enableFanout(user, onSelectionsChange);
      await user.selectOptions(screen.getByLabelText("Fan-out mode for Agent C"), "wave_scheduler");

      await user.selectOptions(screen.getByLabelText("Source list for Agent C"), "agent-a");

      expect(lastSelections(onSelectionsChange)["agent-c"].task_source).toEqual({
        kind: "parsed",
        parser: "json_tasks",
        target: "tasks.json",
        source_step: "agent-a",
      });
      expect(lastSelections(onSelectionsChange)["agent-c"].on_conflict).toBe("human_gate");
    });

    it("explains the json task list requirement for an unknown producer in wave mode", async () => {
      const user = userEvent.setup();
      await enableFanout(user, vi.fn());

      await user.selectOptions(screen.getByLabelText("Fan-out mode for Agent C"), "wave_scheduler");

      expect(screen.getByText(/schedules waves from the/)).toBeInTheDocument();
    });

    it("hides the unknown-producer warning once a known producer is the source", async () => {
      const user = userEvent.setup();
      renderWithProviders(
        <AdvancedExpander
          agents={[{ id: "prototype-plan", name: "Plan" }, { id: "agent-b", name: "Agent B" }]}
        />,
      );
      await open(user, "Agent B");

      await user.click(screen.getByRole("checkbox", { name: "Fan out over a list for Agent B" }));

      expect(screen.queryByText(/fans out one worker per/)).not.toBeInTheDocument();
    });
  });
});
