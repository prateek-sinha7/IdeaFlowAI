/**
 * Behavior of the Simple view's AgentRow beyond the skills-picker and tools
 * suites: core/optional roles, reordering, removal, the model pill, attached
 * skill chips, the config panel toggle and native drag-reorder wiring. Uses the
 * same module boundaries as AgentRow.test.tsx (capabilities API + skills catalog).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { ComponentProps } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
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

// "prototype-plan" is a core (locked) agent in the prototype pipeline and an
// ordinary optional agent in a custom pipeline.
const PLAN = mkAgent({ id: "prototype-plan", name: "Plan", role: "Plans the build" });

function renderRow(props: Partial<ComponentProps<typeof AgentRow>> = {}) {
  const handlers = {
    onSelection: vi.fn(),
    onMoveUp: vi.fn(),
    onMoveDown: vi.fn(),
    onRemove: vi.fn(),
  };
  render(
    <AgentRow
      agent={PLAN}
      index={1}
      total={3}
      pipelineType={"custom" as WorkflowType}
      selection={undefined}
      {...handlers}
      {...props}
    />,
  );
  return handlers;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGetCapabilities.mockResolvedValue(PALETTE);
});

describe("AgentRow", () => {
  describe("header", () => {
    it("shows the 1-based position, initials, name and role", () => {
      renderRow({ index: 11, total: 20, agent: mkAgent({ id: "x", name: "Data Mapper", role: "Maps the data" }) });

      expect(screen.getByText("12")).toBeInTheDocument();
      expect(screen.getByText("DM")).toBeInTheDocument();
      expect(screen.getByText("Data Mapper")).toBeInTheDocument();
      expect(screen.getByText("Maps the data")).toBeInTheDocument();
    });

    it("zero-pads single-digit positions", () => {
      renderRow({ index: 0 });

      expect(screen.getByText("01")).toBeInTheDocument();
    });
  });

  describe("core and optional agents", () => {
    it("marks a core agent, keeps it in place and refuses removal", async () => {
      const user = userEvent.setup();
      const { onRemove } = renderRow({ pipelineType: "prototype" as WorkflowType });

      const remove = screen.getByRole("button", { name: "Remove Plan" });
      expect(screen.getByText("Core")).toBeInTheDocument();
      expect(remove).toBeDisabled();
      expect(remove).toHaveAttribute("title", "Core agents can't be removed");
      expect(screen.getByTestId("agent-row-prototype-plan")).toHaveAttribute("draggable", "false");

      await user.click(remove);
      expect(onRemove).not.toHaveBeenCalled();
    });

    it("lets an optional agent be removed and dragged", async () => {
      const user = userEvent.setup();
      const { onRemove } = renderRow({ pipelineType: "custom" as WorkflowType });

      const remove = screen.getByRole("button", { name: "Remove Plan" });
      expect(screen.queryByText("Core")).not.toBeInTheDocument();
      expect(remove).toBeEnabled();
      expect(remove).toHaveAttribute("title", "Remove agent");
      expect(screen.getByTestId("agent-row-prototype-plan")).toHaveAttribute("draggable", "true");

      await user.click(remove);
      expect(onRemove).toHaveBeenCalledTimes(1);
    });
  });

  describe("reordering", () => {
    it("moves the agent up and down from the middle of the list", async () => {
      const user = userEvent.setup();
      const { onMoveUp, onMoveDown } = renderRow({ index: 1, total: 3 });

      await user.click(screen.getByRole("button", { name: "Move Plan up" }));
      await user.click(screen.getByRole("button", { name: "Move Plan down" }));

      expect(onMoveUp).toHaveBeenCalledTimes(1);
      expect(onMoveDown).toHaveBeenCalledTimes(1);
    });

    it("cannot move the first agent up", async () => {
      const user = userEvent.setup();
      const { onMoveUp } = renderRow({ index: 0, total: 3 });

      const up = screen.getByRole("button", { name: "Move Plan up" });
      expect(up).toBeDisabled();
      expect(screen.getByRole("button", { name: "Move Plan down" })).toBeEnabled();
      await user.click(up);
      expect(onMoveUp).not.toHaveBeenCalled();
    });

    it("cannot move the last agent down", async () => {
      const user = userEvent.setup();
      const { onMoveDown } = renderRow({ index: 2, total: 3 });

      const down = screen.getByRole("button", { name: "Move Plan down" });
      expect(down).toBeDisabled();
      expect(screen.getByRole("button", { name: "Move Plan up" })).toBeEnabled();
      await user.click(down);
      expect(onMoveDown).not.toHaveBeenCalled();
    });

    it("disables both arrows for a lone agent", () => {
      renderRow({ index: 0, total: 1 });

      expect(screen.getByRole("button", { name: "Move Plan up" })).toBeDisabled();
      expect(screen.getByRole("button", { name: "Move Plan down" })).toBeDisabled();
    });

    // user-event has no HTML5 drag-and-drop API, so the native drag events are
    // dispatched directly.
    it("forwards native drag events to the owner", () => {
      const onDragStart = vi.fn();
      const onDragOver = vi.fn();
      const onDrop = vi.fn();
      const onDragEnd = vi.fn();
      renderRow({ onDragStart, onDragOver, onDrop, onDragEnd });
      const row = screen.getByTestId("agent-row-prototype-plan");

      fireEvent.dragStart(row);
      fireEvent.dragOver(row);
      fireEvent.drop(row);
      fireEvent.dragEnd(row);

      expect(onDragStart).toHaveBeenCalledTimes(1);
      expect(onDragOver).toHaveBeenCalledTimes(1);
      expect(onDrop).toHaveBeenCalledTimes(1);
      expect(onDragEnd).toHaveBeenCalledTimes(1);
    });

    it("tolerates drag events when the owner supplies no handlers", () => {
      renderRow();
      const row = screen.getByTestId("agent-row-prototype-plan");

      fireEvent.dragStart(row);
      fireEvent.drop(row);

      expect(row).toBeInTheDocument();
    });
  });

  describe("model pill", () => {
    it("reads Default when no model is chosen", () => {
      renderRow();

      expect(screen.getByRole("button", { name: "Model for Plan" })).toHaveTextContent("Default");
    });

    it("shows the catalog label of the chosen model once the catalog loads", async () => {
      renderRow({ selection: { model: "model-opus" } });

      expect(await screen.findByRole("button", { name: "Model for Plan" })).toHaveTextContent("Opus 4.5");
    });

    it("falls back to the raw id for a model missing from the catalog", async () => {
      renderRow({ selection: { model: "mystery-model" } });

      expect(await screen.findByRole("button", { name: "Model for Plan" })).toHaveTextContent("mystery-model");
    });
  });

  describe("config panel", () => {
    it("is closed initially and toggles from the Configure link", async () => {
      const user = userEvent.setup();
      renderRow();
      expect(screen.queryByTestId("agent-skills-picker-prototype-plan")).not.toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: "Configure →" }));
      expect(await screen.findByTestId("agent-skills-picker-prototype-plan")).toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: "Configure →" }));
      await vi.waitFor(() =>
        expect(screen.queryByTestId("agent-skills-picker-prototype-plan")).not.toBeInTheDocument(),
      );
    });

    it.each(["Validator", "Gate", "Retry", "Skills", "Tools"])(
      "opens from the %s override chip",
      async (label) => {
        const user = userEvent.setup();
        renderRow();

        await user.click(screen.getByRole("button", { name: label }));

        expect(await screen.findByTestId("agent-skills-picker-prototype-plan")).toBeInTheDocument();
      },
    );

    it("keeps the panel open when an override chip is clicked again", async () => {
      const user = userEvent.setup();
      renderRow();

      await user.click(screen.getByRole("button", { name: "Retry" }));
      await user.click(screen.getByRole("button", { name: "Retry" }));

      expect(await screen.findByTestId("agent-skills-picker-prototype-plan")).toBeInTheDocument();
    });

    it("toggles from the model pill", async () => {
      const user = userEvent.setup();
      renderRow();

      await user.click(screen.getByRole("button", { name: "Model for Plan" }));
      expect(await screen.findByTestId("agent-skills-picker-prototype-plan")).toBeInTheDocument();
    });

    it("reports a lever change made in the panel under this agent's id", async () => {
      const user = userEvent.setup();
      const { onSelection } = renderRow();

      await user.click(screen.getByRole("button", { name: "Configure →" }));
      await user.click(await screen.findByRole("button", { name: /Advanced — Plan/ }));
      await user.selectOptions(await screen.findByRole("combobox", { name: "Retry for Plan" }), "2");

      expect(onSelection).toHaveBeenLastCalledWith(
        "prototype-plan",
        expect.objectContaining({ retry: 2 }),
      );
    });
  });

  describe("attached skill chips", () => {
    it("shows no chips when the agent has no skills", () => {
      renderRow();

      expect(screen.queryByRole("button", { name: /^Remove (?!Plan)/ })).not.toBeInTheDocument();
    });

    it("lists each attached skill and removes only the clicked one", async () => {
      const user = userEvent.setup();
      const onSkillsChange = vi.fn();
      renderRow({ agent: { ...PLAN, skills: ["alpha", "beta"] }, onSkillsChange });

      expect(screen.getByText("alpha")).toBeInTheDocument();
      expect(screen.getByText("beta")).toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: "Remove alpha" }));

      expect(onSkillsChange).toHaveBeenCalledWith("prototype-plan", ["beta"]);
    });

    it("tolerates removing a skill when the owner supplies no handler", async () => {
      const user = userEvent.setup();
      renderRow({ agent: { ...PLAN, skills: ["alpha"] } });

      await user.click(screen.getByRole("button", { name: "Remove alpha" }));

      expect(screen.getByText("alpha")).toBeInTheDocument();
    });
  });
});
