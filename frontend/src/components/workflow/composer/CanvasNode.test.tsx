/**
 * CanvasNode.tsx — the Canvas agent card, the external-workflow reference card,
 * the route helpers and the workflow-target picker / options hook.
 *
 * Boundaries replaced: the workflow catalog APIs (`@/lib/api`,
 * `@/store/api/userWorkflows`). Everything else (including the real
 * WorkflowPickerModal) runs for real. The agent card itself is a
 * `role="button"` whose accessible name is its whole content, so it is located
 * through its `canvas-node-<id>` test id.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, renderHook, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ComponentProps } from "react";
import type { AgentDef, WorkflowType } from "@/types/index";
import type { CapabilityModelEntry } from "@/lib/api";

const mocks = vi.hoisted(() => ({
  getToken: vi.fn<() => string | null>(),
  getWorkflowDefinitions: vi.fn(),
  listUserWorkflows: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  getToken: mocks.getToken,
  getWorkflowDefinitions: mocks.getWorkflowDefinitions,
}));
vi.mock("@/store/api/userWorkflows", () => ({
  userWorkflowsApi: { list: mocks.listUserWorkflows },
}));

import {
  CanvasNode,
  ExternalWorkflowNode,
  WorkflowTargetPicker,
  applyOutcomePatch,
  applyRoutePatch,
  nextOutcomeKey,
  resolveWorkflowTarget,
  EXTERNAL_NODE_W,
  MAX_ROUTE_OUTCOMES,
  type WorkflowPickerOption,
} from "./CanvasNode";

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

const MODELS: CapabilityModelEntry[] = [
  {
    id: "model-opus",
    label: "Opus 4.5",
    description: "Most capable.",
    tier: "powerful",
    cost_class: "premium",
    provider: "anthropic",
    context_window: 200000,
    user_allowed: true,
  },
];

// "prototype-plan" is core (locked) in the prototype pipeline and an ordinary
// removable agent in a custom pipeline.
const AGENT = mkAgent({ id: "prototype-plan", name: "Plan Agent", role: "Plans the build" });

function renderNode(props: Partial<ComponentProps<typeof CanvasNode>> = {}) {
  const handlers = {
    onSelect: vi.fn(),
    onRemove: vi.fn(),
  };
  const utils = render(
    <CanvasNode
      agent={AGENT}
      pipelineType={"custom" as WorkflowType}
      selected={false}
      isChild={false}
      hasChildren={false}
      cardWidth={260}
      left={10}
      top={20}
      modelOptions={MODELS}
      {...handlers}
      {...props}
    />,
  );
  return { ...handlers, ...utils };
}

const card = (id = "prototype-plan") => screen.getByTestId(`canvas-node-${id}`);

beforeEach(() => {
  vi.clearAllMocks();
});

describe("CanvasNode", () => {
  describe("identity", () => {
    it("shows the name without a trailing ' Agent' and the role", () => {
      renderNode();

      expect(screen.getByRole("heading", { name: "Plan" })).toBeInTheDocument();
      expect(screen.getByText("Plans the build")).toBeInTheDocument();
    });

    it("keeps the full name when removing the suffix would leave nothing", () => {
      renderNode({ agent: { ...AGENT, name: "Agent" } });

      expect(screen.getByRole("heading", { name: "Agent" })).toBeInTheDocument();
    });

    it("marks an AI step with an AI-agent icon and a code step with a code icon", () => {
      const { rerender } = renderNode();
      expect(screen.getByLabelText("AI agent")).toBeInTheDocument();
      expect(screen.queryByLabelText("Code step")).not.toBeInTheDocument();

      rerender(
        <CanvasNode
          agent={{ ...AGENT, mechanical: "assemble_prototype" }}
          pipelineType={"custom" as WorkflowType}
          selected={false}
          isChild={false}
          hasChildren={false}
          cardWidth={260}
          left={0}
          top={0}
          modelOptions={MODELS}
          onSelect={vi.fn()}
          onRemove={vi.fn()}
        />,
      );
      expect(screen.getByLabelText("Code step")).toBeInTheDocument();
      expect(screen.queryByLabelText("AI agent")).not.toBeInTheDocument();
    });

    it("labels a code step with its kind instead of a model", () => {
      renderNode({ agent: { ...AGENT, mechanical: "assemble_prototype" } });

      expect(screen.getByText("assemble prototype")).toBeInTheDocument();
      expect(screen.queryByText("Default")).not.toBeInTheDocument();
    });

    it("shows the model pill as Default, the catalog label, or the raw id", () => {
      const { unmount } = renderNode();
      expect(screen.getByText("Default")).toBeInTheDocument();
      unmount();

      const second = renderNode({ selection: { model: "model-opus" } });
      expect(screen.getByText("Opus 4.5")).toBeInTheDocument();
      second.unmount();

      renderNode({ selection: { model: "unlisted-model" } });
      expect(screen.getByText("unlisted-model")).toBeInTheDocument();
    });

    it("shows a Core badge only for locked agents", () => {
      const { unmount } = renderNode({ pipelineType: "prototype" as WorkflowType });
      expect(screen.getByText("Core")).toBeInTheDocument();
      unmount();

      renderNode({ pipelineType: "custom" as WorkflowType });
      expect(screen.queryByText("Core")).not.toBeInTheDocument();
    });
  });

  describe("selection", () => {
    it("selects on click", async () => {
      const user = userEvent.setup();
      const { onSelect } = renderNode();

      await user.click(card());

      expect(onSelect).toHaveBeenCalledTimes(1);
    });

    it.each([["{Enter}"], [" "]])("selects from the keyboard with %j", async (key) => {
      const user = userEvent.setup();
      const { onSelect } = renderNode();
      card().focus();

      await user.keyboard(key);

      expect(onSelect).toHaveBeenCalledTimes(1);
    });

    it("ignores other keys", async () => {
      const user = userEvent.setup();
      const { onSelect } = renderNode();
      card().focus();

      await user.keyboard("a");

      expect(onSelect).not.toHaveBeenCalled();
    });

    it("reports the selected state on the card", () => {
      renderNode({ selected: true });

      expect(card()).toHaveAttribute("data-selected", "true");
    });

    it("reports the unselected state on the card", () => {
      renderNode({ selected: false });

      expect(card()).toHaveAttribute("data-selected", "false");
    });

    it("forwards a mouse-down on the card for free-drag", () => {
      const onCardMouseDown = vi.fn();
      renderNode({ onCardMouseDown });

      fireEvent.mouseDown(card());

      expect(onCardMouseDown).toHaveBeenCalledTimes(1);
    });
  });

  describe("removal", () => {
    it("removes an optional agent without selecting it", async () => {
      const user = userEvent.setup();
      const { onRemove, onSelect } = renderNode({ pipelineType: "custom" as WorkflowType });

      const remove = screen.getByRole("button", { name: "Remove Plan Agent" });
      expect(remove).toHaveAttribute("title", "Remove agent");
      await user.click(remove);

      expect(onRemove).toHaveBeenCalledTimes(1);
      expect(onSelect).not.toHaveBeenCalled();
    });

    it("disables removal of a core agent", async () => {
      const user = userEvent.setup();
      const { onRemove } = renderNode({ pipelineType: "prototype" as WorkflowType });

      const remove = screen.getByRole("button", { name: "Remove Plan Agent" });
      expect(remove).toBeDisabled();
      expect(remove).toHaveAttribute("title", "Core agents can't be removed");
      await user.click(remove);

      expect(onRemove).not.toHaveBeenCalled();
    });
  });

  describe("renaming", () => {
    it("offers no rename affordance without an onRename handler", () => {
      renderNode();

      expect(screen.queryByRole("button", { name: "Rename Plan Agent" })).not.toBeInTheDocument();
    });

    it("does not start renaming on double-click without an onRename handler", async () => {
      const user = userEvent.setup();
      renderNode();

      await user.dblClick(screen.getByRole("heading", { name: "Plan" }));

      expect(screen.queryByRole("textbox", { name: "Rename Plan Agent" })).not.toBeInTheDocument();
    });

    it("commits a trimmed new name on Enter without selecting the card", async () => {
      const user = userEvent.setup();
      const onRename = vi.fn();
      const { onSelect } = renderNode({ onRename });

      await user.click(screen.getByRole("button", { name: "Rename Plan Agent" }));
      const input = screen.getByRole("textbox", { name: "Rename Plan Agent" });
      expect(input).toHaveValue("Plan Agent");
      await user.clear(input);
      await user.type(input, "  Builder  {Enter}");

      expect(onRename).toHaveBeenCalledWith("prototype-plan", "Builder");
      expect(screen.queryByRole("textbox", { name: "Rename Plan Agent" })).not.toBeInTheDocument();
      expect(onSelect).not.toHaveBeenCalled();
    });

    it("commits from the confirm button", async () => {
      const user = userEvent.setup();
      const onRename = vi.fn();
      renderNode({ onRename });

      await user.click(screen.getByRole("button", { name: "Rename Plan Agent" }));
      const input = screen.getByRole("textbox", { name: "Rename Plan Agent" });
      await user.clear(input);
      await user.type(input, "Builder");
      await user.click(screen.getByRole("button", { name: "Confirm rename" }));

      expect(onRename).toHaveBeenCalledWith("prototype-plan", "Builder");
    });

    it("starts renaming on a double-click of the title", async () => {
      const user = userEvent.setup();
      renderNode({ onRename: vi.fn() });

      await user.dblClick(screen.getByRole("heading", { name: "Plan" }));

      expect(screen.getByRole("textbox", { name: "Rename Plan Agent" })).toHaveValue("Plan Agent");
    });

    it("does not rename when the name is unchanged", async () => {
      const user = userEvent.setup();
      const onRename = vi.fn();
      renderNode({ onRename });

      await user.click(screen.getByRole("button", { name: "Rename Plan Agent" }));
      await user.click(screen.getByRole("button", { name: "Confirm rename" }));

      expect(onRename).not.toHaveBeenCalled();
      expect(screen.queryByRole("textbox", { name: "Rename Plan Agent" })).not.toBeInTheDocument();
    });

    it("does not rename to a blank name", async () => {
      const user = userEvent.setup();
      const onRename = vi.fn();
      renderNode({ onRename });

      await user.click(screen.getByRole("button", { name: "Rename Plan Agent" }));
      await user.clear(screen.getByRole("textbox", { name: "Rename Plan Agent" }));
      await user.keyboard("{Enter}");

      expect(onRename).not.toHaveBeenCalled();
      expect(screen.getByRole("heading", { name: "Plan" })).toBeInTheDocument();
    });

    it("abandons the edit on Escape and restores the original name", async () => {
      const user = userEvent.setup();
      const onRename = vi.fn();
      renderNode({ onRename });

      await user.click(screen.getByRole("button", { name: "Rename Plan Agent" }));
      await user.type(screen.getByRole("textbox", { name: "Rename Plan Agent" }), "XYZ{Escape}");

      expect(onRename).not.toHaveBeenCalled();
      expect(screen.getByRole("heading", { name: "Plan" })).toBeInTheDocument();
    });

    it("hides the move controls while renaming", async () => {
      const user = userEvent.setup();
      renderNode({ onRename: vi.fn(), onMoveEarlier: vi.fn(), onMoveLater: vi.fn() });
      expect(screen.getByRole("button", { name: "Move Plan Agent earlier" })).toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: "Rename Plan Agent" }));

      expect(screen.queryByRole("button", { name: "Move Plan Agent earlier" })).not.toBeInTheDocument();
    });
  });

  describe("override chips", () => {
    it("shows the retry count only when retries are configured", () => {
      const { unmount } = renderNode({ selection: { retry: 2 } });
      expect(screen.getByText("Retry ·2")).toBeInTheDocument();
      unmount();

      renderNode({ selection: { retry: 0 } });
      expect(screen.getByText("Retry")).toBeInTheDocument();
      expect(screen.queryByText(/Retry ·/)).not.toBeInTheDocument();
    });

    it("explains a restricted Tools chip and leaves an unrestricted one unexplained", () => {
      const { unmount } = renderNode({ selection: { tools: { write_files: false } } });
      expect(screen.getByText("Tools")).toHaveAttribute(
        "title",
        "Tool grants are restricted — open Config to view",
      );
      unmount();

      renderNode({ selection: undefined });
      expect(screen.getByText("Tools")).not.toHaveAttribute("title");
    });

    it("opens the config rail from the Gate chip without selecting the card", async () => {
      const user = userEvent.setup();
      const onOpenConfig = vi.fn();
      const { onSelect } = renderNode({ onOpenConfig });

      await user.click(screen.getByRole("button", { name: "Gate" }));

      expect(onOpenConfig).toHaveBeenCalledTimes(1);
      expect(onSelect).not.toHaveBeenCalled();
    });

    it("tolerates a Gate chip click when no config handler is supplied", async () => {
      const user = userEvent.setup();
      const { onSelect } = renderNode();

      await user.click(screen.getByRole("button", { name: "Gate" }));

      expect(onSelect).not.toHaveBeenCalled();
    });
  });

  describe("conditional routing", () => {
    const conditional = { gates: ["conditional"] };

    it("shows no route badge for an unconditional step", () => {
      renderNode({ selection: { gates: ["approval"] } });

      expect(screen.queryByTestId("canvas-node-route-prototype-plan")).not.toBeInTheDocument();
      expect(screen.queryByTestId("canvas-route-connect-prototype-plan")).not.toBeInTheDocument();
    });

    it.each([
      [0, "no outcomes yet"],
      [1, "1 outcome"],
      [3, "3 outcomes"],
    ])("summarises %i route outcome(s) as %j", (count, text) => {
      const outcomes = Object.fromEntries(
        Array.from({ length: count }, (_, i) => [`outcome_${i + 1}`, { trigger: "step" as const, target: `t${i}` }]),
      );
      renderNode({ selection: conditional, agent: { ...AGENT, route: { outcomes } } });

      const badge = screen.getByTestId("canvas-node-route-prototype-plan");
      expect(within(badge).getByText("Route")).toBeInTheDocument();
      expect(within(badge).getByText(text)).toBeInTheDocument();
      expect(screen.getByTestId("canvas-route-connect-prototype-plan")).toBeInTheDocument();
    });

    it("treats a conditional step with no route object as having no outcomes", () => {
      renderNode({ selection: conditional });

      expect(screen.getByText("no outcomes yet")).toBeInTheDocument();
    });

    it("opens the config rail from the route badge without selecting the card", async () => {
      const user = userEvent.setup();
      const onOpenConfig = vi.fn();
      const { onSelect } = renderNode({ selection: conditional, onOpenConfig });

      await user.click(screen.getByTestId("canvas-node-route-prototype-plan"));

      expect(onOpenConfig).toHaveBeenCalledTimes(1);
      expect(onSelect).not.toHaveBeenCalled();
    });

    it("tolerates a route badge click when no config handler is supplied", async () => {
      const user = userEvent.setup();
      const { onSelect } = renderNode({ selection: conditional, selected: true });

      await user.click(screen.getByTestId("canvas-node-route-prototype-plan"));

      expect(onSelect).not.toHaveBeenCalled();
    });
  });

  describe("detached step", () => {
    it("warns that a detached step is not connected", () => {
      renderNode({ agent: { ...AGENT, detached: true } });

      expect(screen.getByTestId("canvas-node-detached-prototype-plan")).toHaveTextContent(
        "Not connected — point a route at this step, or remove it.",
      );
    });

    it("shows no warning for a connected step", () => {
      renderNode();

      expect(screen.queryByTestId("canvas-node-detached-prototype-plan")).not.toBeInTheDocument();
    });

    it("exposes a drag handle for re-attaching only while a chain-connect handler is supplied", () => {
      const onChainConnectMouseDown = vi.fn();
      const { unmount } = renderNode({ onChainConnectMouseDown });

      fireEvent.mouseDown(screen.getByTitle("Drag onto the unconnected step to attach it here"));
      expect(onChainConnectMouseDown).toHaveBeenCalledTimes(1);
      unmount();

      renderNode();
      expect(screen.queryByTitle("Drag onto the unconnected step to attach it here")).not.toBeInTheDocument();
    });
  });

  describe("attached skills", () => {
    const withSkills = { ...AGENT, skills: ["alpha", "beta"] };

    it("lists each skill and removes only the clicked one without selecting the card", async () => {
      const user = userEvent.setup();
      const onSkillsChange = vi.fn();
      const { onSelect } = renderNode({ agent: withSkills, onSkillsChange });

      expect(screen.getByText("alpha")).toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "Remove alpha" }));

      expect(onSkillsChange).toHaveBeenCalledWith("prototype-plan", ["beta"]);
      expect(onSelect).not.toHaveBeenCalled();
    });

    it("shows the skills read-only when no change handler is supplied", () => {
      renderNode({ agent: withSkills });

      expect(screen.getByText("beta")).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Remove beta" })).not.toBeInTheDocument();
    });

    it("shows no skill chips when the agent has none", () => {
      renderNode({ agent: { ...AGENT, skills: [] } });

      expect(screen.queryByRole("button", { name: /^Remove (?!Plan Agent)/ })).not.toBeInTheDocument();
    });
  });

  describe("sub-agents", () => {
    it("offers no sub-agent button without an onAddChild handler", () => {
      renderNode();

      expect(screen.queryByRole("button", { name: "Add sub-agent to Plan Agent" })).not.toBeInTheDocument();
    });

    it("adds a sub-agent to this node without selecting it", async () => {
      const user = userEvent.setup();
      const onAddChild = vi.fn();
      const { onSelect } = renderNode({ onAddChild });

      await user.click(screen.getByRole("button", { name: "Add sub-agent to Plan Agent" }));

      expect(onAddChild).toHaveBeenCalledWith("prototype-plan");
      expect(onSelect).not.toHaveBeenCalled();
    });

    it("disables the button and explains why when a nesting cap is reached", async () => {
      const user = userEvent.setup();
      const onAddChild = vi.fn();
      renderNode({ onAddChild, addChildDisabledReason: "Maximum nesting depth reached" });

      const button = screen.getByRole("button", { name: "Add sub-agent to Plan Agent" });
      expect(button).toBeDisabled();
      expect(screen.getByRole("tooltip")).toHaveTextContent("Maximum nesting depth reached");
      await user.click(button);

      expect(onAddChild).not.toHaveBeenCalled();
    });

    it("shows no tooltip while adding is allowed", () => {
      renderNode({ onAddChild: vi.fn() });

      expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
    });
  });

  describe("reordering", () => {
    it("shows no move controls when neither direction is supplied", () => {
      renderNode();

      expect(screen.queryByRole("button", { name: /^Move Plan Agent/ })).not.toBeInTheDocument();
    });

    it("moves the step earlier and later without selecting it", async () => {
      const user = userEvent.setup();
      const onMoveEarlier = vi.fn();
      const onMoveLater = vi.fn();
      const { onSelect } = renderNode({ onMoveEarlier, onMoveLater });

      await user.click(screen.getByRole("button", { name: "Move Plan Agent earlier" }));
      await user.click(screen.getByRole("button", { name: "Move Plan Agent later" }));

      expect(onMoveEarlier).toHaveBeenCalledTimes(1);
      expect(onMoveLater).toHaveBeenCalledTimes(1);
      expect(onSelect).not.toHaveBeenCalled();
    });

    it("disables 'earlier' for the first step", () => {
      renderNode({ onMoveLater: vi.fn() });

      const earlier = screen.getByRole("button", { name: "Move Plan Agent earlier" });
      expect(earlier).toBeDisabled();
      expect(earlier).toHaveAttribute("title", "Already first");
      expect(screen.getByRole("button", { name: "Move Plan Agent later" })).toBeEnabled();
    });

    it("disables 'later' for the last step", () => {
      renderNode({ onMoveEarlier: vi.fn() });

      const later = screen.getByRole("button", { name: "Move Plan Agent later" });
      expect(later).toBeDisabled();
      expect(later).toHaveAttribute("title", "Already last");
      expect(screen.getByRole("button", { name: "Move Plan Agent earlier" })).toBeEnabled();
    });
  });
});

describe("ExternalWorkflowNode", () => {
  const names = new Map([
    ["ppt", "Slide Deck"],
    ["abc-uuid", "My Flow"],
  ]);

  function renderExternal(props: Partial<ComponentProps<typeof ExternalWorkflowNode>> = {}) {
    return render(
      <ExternalWorkflowNode workflowId="ppt" workflowNameById={names} left={5} top={7} {...props} />,
    );
  }

  it("shows the resolved name, the divert marker and the authored short name", () => {
    renderExternal({ workflowShortNameById: new Map([["ppt", "PPT"]]) });

    const node = screen.getByTestId("canvas-external-workflow-ppt");
    expect(within(node).getByText("Slide Deck")).toBeInTheDocument();
    expect(within(node).getByText("PPT")).toBeInTheDocument();
    expect(within(node).getByText("Diverts run")).toBeInTheDocument();
    expect(node).toHaveAttribute("title", "Slide Deck");
    expect(node.style.width).toBe(`${EXTERNAL_NODE_W}px`);
  });

  it("labels a self target as SELF", () => {
    renderExternal({ workflowId: "self" });

    const node = screen.getByTestId("canvas-external-workflow-self");
    expect(within(node).getByText("SELF")).toBeInTheDocument();
    expect(within(node).getByText("self (this workflow)")).toBeInTheDocument();
  });

  it("labels a user workflow without a short name as CUSTOM", () => {
    renderExternal({ workflowId: "abc-uuid", workflowKindById: new Map([["abc-uuid", "user"]]) });

    expect(within(screen.getByTestId("canvas-external-workflow-abc-uuid")).getByText("CUSTOM")).toBeInTheDocument();
  });

  it("falls back to the upper-cased id for a system workflow without a short name", () => {
    renderExternal({ workflowKindById: new Map([["ppt", "system"]]) });

    expect(within(screen.getByTestId("canvas-external-workflow-ppt")).getByText("PPT")).toBeInTheDocument();
  });

  it("shows the raw id when the catalog does not know it", () => {
    renderExternal({ workflowId: "mystery" });

    const node = screen.getByTestId("canvas-external-workflow-mystery");
    expect(within(node).getByText("MYSTERY")).toBeInTheDocument();
    expect(within(node).getByText("mystery")).toBeInTheDocument();
  });

  it("falls back to a generic eyebrow and a placeholder label for an empty target", () => {
    renderExternal({ workflowId: "" });

    const node = screen.getByTestId("canvas-external-workflow-node");
    expect(within(node).getByText("WORKFLOW")).toBeInTheDocument();
    expect(within(node).getByText("Select a workflow…")).toBeInTheDocument();
  });

  it("reports its selected state", () => {
    const { unmount } = renderExternal({ selected: true });
    expect(screen.getByTestId("canvas-external-workflow-ppt")).toHaveAttribute("data-selected", "true");
    unmount();

    renderExternal();
    expect(screen.getByTestId("canvas-external-workflow-ppt")).toHaveAttribute("data-selected", "false");
  });

  it("selects on click, Enter and Space but not other keys", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    renderExternal({ onSelect });
    const node = screen.getByTestId("canvas-external-workflow-ppt");

    await user.click(node);
    node.focus();
    await user.keyboard("{Enter}");
    await user.keyboard(" ");
    await user.keyboard("a");

    expect(onSelect).toHaveBeenCalledTimes(3);
  });

  it("tolerates keyboard activation without a select handler", async () => {
    const user = userEvent.setup();
    renderExternal();
    screen.getByTestId("canvas-external-workflow-ppt").focus();

    await user.keyboard("{Enter}");

    expect(screen.getByTestId("canvas-external-workflow-ppt")).toBeInTheDocument();
  });

  it("forwards a mouse-down so it can be dragged", () => {
    const onMouseDown = vi.fn();
    renderExternal({ onMouseDown });

    fireEvent.mouseDown(screen.getByTestId("canvas-external-workflow-ppt"));

    expect(onMouseDown).toHaveBeenCalledTimes(1);
  });
});

describe("route helpers", () => {
  describe("resolveWorkflowTarget", () => {
    const names = new Map([["ppt", "Slide Deck"]]);

    it("resolves a known id to its name", () => {
      expect(resolveWorkflowTarget("ppt", names)).toEqual({
        id: "ppt",
        isSelf: false,
        isUnresolved: false,
        label: "Slide Deck",
      });
    });

    it("trims the id before resolving", () => {
      expect(resolveWorkflowTarget("  ppt ", names).label).toBe("Slide Deck");
    });

    it("treats self as resolved with its own label", () => {
      expect(resolveWorkflowTarget("self", names)).toEqual({
        id: "self",
        isSelf: true,
        isUnresolved: false,
        label: "self (this workflow)",
      });
    });

    it("marks an unknown id unresolved and shows it verbatim", () => {
      expect(resolveWorkflowTarget("nope", names)).toEqual({
        id: "nope",
        isSelf: false,
        isUnresolved: true,
        label: "nope",
      });
    });

    it("prompts for a selection when the id is blank", () => {
      expect(resolveWorkflowTarget("   ", names)).toMatchObject({
        id: "",
        isUnresolved: true,
        label: "Select a workflow…",
      });
    });
  });

  describe("applyRoutePatch", () => {
    it("starts from an empty outcomes map when there is no route", () => {
      expect(applyRoutePatch(undefined, { default_next: "b" })).toEqual({ outcomes: {}, default_next: "b" });
    });

    it("overlays the patch on the existing route", () => {
      const route = { outcomes: { a: { trigger: "step" as const, target: "x" } }, default_next: "old" };

      expect(applyRoutePatch(route, { default_next: "new" })).toEqual({
        outcomes: { a: { trigger: "step", target: "x" } },
        default_next: "new",
      });
    });
  });

  describe("applyOutcomePatch", () => {
    it("creates a step outcome with an empty target when the key is new", () => {
      expect(applyOutcomePatch(undefined, "outcome_1", { target: "b" })).toEqual({
        outcomes: { outcome_1: { trigger: "step", target: "b" } },
      });
    });

    it("merges into an existing outcome and keeps the others", () => {
      const route = {
        outcomes: {
          a: { trigger: "step" as const, target: "x" },
          b: { trigger: "step" as const, target: "y" },
        },
      };

      expect(applyOutcomePatch(route, "a", { trigger: "workflow" })).toEqual({
        outcomes: {
          a: { trigger: "workflow", target: "x" },
          b: { trigger: "step", target: "y" },
        },
      });
    });
  });

  describe("nextOutcomeKey", () => {
    it("starts at outcome_1 for a missing route", () => {
      expect(nextOutcomeKey(undefined)).toBe("outcome_1");
    });

    it("continues the numbering after existing outcomes", () => {
      const route = { outcomes: { outcome_1: { trigger: "step" as const, target: "" } } };

      expect(nextOutcomeKey(route)).toBe("outcome_2");
    });

    it("skips a key that is already taken", () => {
      const route = {
        outcomes: {
          outcome_2: { trigger: "step" as const, target: "" },
          other: { trigger: "step" as const, target: "" },
        },
      };

      expect(nextOutcomeKey(route)).toBe("outcome_3");
    });
  });

  it("caps a conditional gate at five outcomes", () => {
    expect(MAX_ROUTE_OUTCOMES).toBe(5);
  });
});

describe("WorkflowTargetPicker", () => {
  const WORKFLOWS: WorkflowPickerOption[] = [
    { id: "ppt", name: "Slide Deck", kind: "system", launchable: true, isBeta: false },
    { id: "user_stories", name: "User Stories", kind: "system", launchable: true, isBeta: false },
  ];

  beforeEach(() => {
    // jsdom lacks scrollIntoView, which the picker modal calls.
    Object.defineProperty(Element.prototype, "scrollIntoView", {
      configurable: true,
      writable: true,
      value: vi.fn(),
    });
  });

  afterEach(() => {
    delete (Element.prototype as unknown as Record<string, unknown>).scrollIntoView;
  });

  it("falls back to a free-text target with a warning when the catalog failed to load", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<WorkflowTargetPicker value="" onChange={onChange} workflows={null} fetchFailed />);

    expect(screen.getByText("Couldn't load workflows — enter the target id directly.")).toBeInTheDocument();
    await user.type(screen.getByRole("textbox", { name: "Target" }), "x");

    expect(onChange).toHaveBeenCalledWith("x");
  });

  it("prompts to pick a workflow when no target is set", () => {
    render(<WorkflowTargetPicker value="" onChange={vi.fn()} workflows={WORKFLOWS} fetchFailed={false} />);

    expect(screen.getByRole("button", { name: "Target" })).toHaveTextContent("Pick a workflow…");
  });

  it("shows the chosen workflow's name", () => {
    render(<WorkflowTargetPicker value="ppt" onChange={vi.fn()} workflows={WORKFLOWS} fetchFailed={false} />);

    expect(screen.getByRole("button", { name: "Target" })).toHaveTextContent("Slide Deck");
  });

  it("shows the raw id while the catalog has not loaded", () => {
    render(<WorkflowTargetPicker value="ppt" onChange={vi.fn()} workflows={null} fetchFailed={false} />);

    expect(screen.getByRole("button", { name: "Target" })).toHaveTextContent("ppt");
  });

  it("commits the workflow picked in the modal and closes it", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<WorkflowTargetPicker value="" onChange={onChange} workflows={WORKFLOWS} fetchFailed={false} />);

    await user.click(screen.getByRole("button", { name: "Target" }));
    await user.click(await screen.findByTestId("workflow-picker-row-user_stories"));
    await user.click(screen.getByRole("button", { name: "Pick workflow" }));

    expect(onChange).toHaveBeenCalledWith("user_stories");
    expect(screen.queryByRole("dialog", { name: "Pick a workflow" })).not.toBeInTheDocument();
  });

  it("closes the modal without changing the target when cancelled", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<WorkflowTargetPicker value="" onChange={onChange} workflows={WORKFLOWS} fetchFailed={false} />);

    await user.click(screen.getByRole("button", { name: "Target" }));
    await screen.findByRole("dialog", { name: "Pick a workflow" });
    await user.keyboard("{Escape}");

    expect(screen.queryByRole("dialog", { name: "Pick a workflow" })).not.toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe("useWorkflowPickerOptions", () => {
  // The hook caches its fetch in a module-level promise, so every case loads a
  // fresh copy of the module to start from an empty cache.
  async function loadHook() {
    vi.resetModules();
    const mod = await import("./CanvasNode");
    return mod.useWorkflowPickerOptions;
  }

  const SYSTEM = {
    id: "ppt",
    name: "ppt",
    display_name: "Slide Deck",
    short_name: "PPT",
    description: "Builds decks",
    step_count: 4,
    steps: [],
    user_launchable: true,
    is_beta: true,
    icon: "Presentation",
  };

  beforeEach(() => {
    mocks.getToken.mockReturnValue("test-token");
    mocks.getWorkflowDefinitions.mockResolvedValue([SYSTEM]);
    mocks.listUserWorkflows.mockResolvedValue([
      { id: "u1", name: "Mine", description: "Personal", agent_ids: ["a", "b", "c"] },
    ]);
  });

  it("does not fetch while disabled", async () => {
    const useWorkflowPickerOptions = await loadHook();

    const { result } = renderHook(() => useWorkflowPickerOptions(false));

    expect(result.current).toEqual({ workflows: null, fetchFailed: false });
    expect(mocks.getWorkflowDefinitions).not.toHaveBeenCalled();
    expect(mocks.listUserWorkflows).not.toHaveBeenCalled();
  });

  it("combines the system catalog and the user's workflows into tagged options", async () => {
    const useWorkflowPickerOptions = await loadHook();

    const { result } = renderHook(() => useWorkflowPickerOptions(true));

    await waitFor(() => expect(result.current.workflows).not.toBeNull());
    expect(mocks.getWorkflowDefinitions).toHaveBeenCalledWith("test-token");
    expect(result.current.workflows).toEqual([
      {
        id: "ppt",
        name: "Slide Deck",
        shortName: "PPT",
        kind: "system",
        launchable: true,
        isBeta: true,
        description: "Builds decks",
        stepCount: 4,
        icon: "Presentation",
      },
      {
        id: "u1",
        name: "Mine",
        kind: "user",
        launchable: true,
        isBeta: false,
        description: "Personal",
        stepCount: 3,
      },
    ]);
    expect(result.current.fetchFailed).toBe(false);
  });

  it("falls back to the plain name and drops empty optional fields", async () => {
    mocks.getWorkflowDefinitions.mockResolvedValue([
      {
        id: "bare",
        name: "Bare",
        display_name: null,
        short_name: null,
        description: "",
        step_count: 1,
        steps: [],
        user_launchable: false,
        icon: "",
      },
    ]);
    mocks.listUserWorkflows.mockResolvedValue([{ id: "u2", name: "Empty", description: "" }]);
    const useWorkflowPickerOptions = await loadHook();

    const { result } = renderHook(() => useWorkflowPickerOptions(true));

    await waitFor(() => expect(result.current.workflows).not.toBeNull());
    expect(result.current.workflows).toEqual([
      {
        id: "bare",
        name: "Bare",
        shortName: undefined,
        kind: "system",
        launchable: false,
        isBeta: false,
        description: undefined,
        stepCount: 1,
        icon: undefined,
      },
      {
        id: "u2",
        name: "Empty",
        kind: "user",
        launchable: true,
        isBeta: false,
        description: undefined,
        stepCount: undefined,
      },
    ]);
  });

  it("skips the system catalog when there is no auth token", async () => {
    mocks.getToken.mockReturnValue(null);
    const useWorkflowPickerOptions = await loadHook();

    const { result } = renderHook(() => useWorkflowPickerOptions(true));

    await waitFor(() => expect(result.current.workflows).not.toBeNull());
    expect(mocks.getWorkflowDefinitions).not.toHaveBeenCalled();
    expect(result.current.workflows?.map((w) => w.id)).toEqual(["u1"]);
  });

  it("still offers the other catalog when one of the two fetches fails", async () => {
    mocks.getWorkflowDefinitions.mockRejectedValue(new Error("500"));
    mocks.listUserWorkflows.mockRejectedValue(new Error("500"));
    const useWorkflowPickerOptions = await loadHook();

    const { result } = renderHook(() => useWorkflowPickerOptions(true));

    await waitFor(() => expect(result.current.workflows).toEqual([]));
    expect(result.current.fetchFailed).toBe(false);
  });

  it("shares one fetch between every consumer", async () => {
    const useWorkflowPickerOptions = await loadHook();

    const first = renderHook(() => useWorkflowPickerOptions(true));
    const second = renderHook(() => useWorkflowPickerOptions(true));

    await waitFor(() => expect(first.result.current.workflows).not.toBeNull());
    await waitFor(() => expect(second.result.current.workflows).not.toBeNull());
    expect(mocks.getWorkflowDefinitions).toHaveBeenCalledTimes(1);
    expect(mocks.listUserWorkflows).toHaveBeenCalledTimes(1);
  });

  it("reports a failure when the catalog cannot be processed, then retries on the next mount", async () => {
    mocks.getWorkflowDefinitions.mockResolvedValueOnce([null]);
    const useWorkflowPickerOptions = await loadHook();

    const failed = renderHook(() => useWorkflowPickerOptions(true));
    await waitFor(() => expect(failed.result.current.fetchFailed).toBe(true));
    expect(failed.result.current.workflows).toBeNull();

    const retried = renderHook(() => useWorkflowPickerOptions(true));
    await waitFor(() => expect(retried.result.current.workflows).not.toBeNull());
    expect(retried.result.current.fetchFailed).toBe(false);
    expect(mocks.getWorkflowDefinitions).toHaveBeenCalledTimes(2);
  });

  it("ignores a response that arrives after the consumer unmounted", async () => {
    let resolveUser: (v: unknown[]) => void = () => {};
    mocks.listUserWorkflows.mockReturnValue(
      new Promise((resolve) => {
        resolveUser = resolve;
      }),
    );
    const useWorkflowPickerOptions = await loadHook();
    const { result, unmount } = renderHook(() => useWorkflowPickerOptions(true));

    unmount();
    await act(async () => {
      resolveUser([]);
    });

    expect(result.current.workflows).toBeNull();
  });

  it("starts fetching once it becomes enabled", async () => {
    const useWorkflowPickerOptions = await loadHook();
    const { result, rerender } = renderHook(({ on }) => useWorkflowPickerOptions(on), {
      initialProps: { on: false },
    });
    expect(mocks.getWorkflowDefinitions).not.toHaveBeenCalled();

    rerender({ on: true });

    await waitFor(() => expect(result.current.workflows).not.toBeNull());
    expect(mocks.getWorkflowDefinitions).toHaveBeenCalledTimes(1);
  });
});
