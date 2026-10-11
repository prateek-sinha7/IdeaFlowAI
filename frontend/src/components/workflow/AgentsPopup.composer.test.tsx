/**
 * Behaviour tests for the main `AgentsPopup` composer modal: header, tabs,
 * Cancel-restores-snapshot, in-modal edits, agent library hand-offs, and the
 * Save-workflow flow.
 *
 * Boundaries controlled here:
 *  - `./composer/CanvasView` — the heavy hand-rolled node-graph editor, replaced
 *    by a thin shell that renders what AgentsPopup passes in and exposes buttons
 *    that call the callbacks AgentsPopup hands to the canvas. The canvas itself
 *    is covered by its own tests; the subject here is AgentsPopup.
 *  - `@/lib/api` — token and network.
 * Redux catalogs, SkillsHooksProvider, AgentLibrary and NameWorkflowModal are real.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderWithProviders, screen, waitFor, within } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";
import globalReducer from "@/store/slices/globalSlice";
import type { AgentDef, ManifestStep } from "@/types/index";
import type { WorkflowSummary } from "@/store/api/workflows";

const api = vi.hoisted(() => ({
  getToken: vi.fn(),
  getCapabilities: vi.fn(),
  saveUserWorkflow: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  getToken: api.getToken,
  getCapabilities: api.getCapabilities,
  saveUserWorkflow: api.saveUserWorkflow,
}));

vi.mock("./composer/CanvasView", async () => {
  const { createElement: h } = await import("react");
  type Props = import("react").ComponentProps<typeof import("./composer/CanvasView").CanvasView>;

  function CanvasViewShell(p: Props) {
    return h(
      "div",
      { "data-testid": "canvas-shell" },
      h("ul", { "aria-label": "canvas agents" }, p.pipelineAgents.map((a) => h("li", { key: a.id }, a.name))),
      h("output", { "aria-label": "canvas selections" }, JSON.stringify(p.selections)),
      h("output", { "aria-label": "canvas can-add-more" }, String(p.canAddMore)),
      h("output", { "aria-label": "canvas reset signal" }, String(p.resetLayoutSignal)),
      h("output", { "aria-label": "canvas declared" }, p.declaredCapabilities.join(",")),
      h("button", { onClick: () => p.onSelection("opt-1", { model: "m1" }) }, "shell select model"),
      h("button", { onClick: () => p.onSelection("opt-1", undefined) }, "shell clear selection undefined"),
      h("button", { onClick: () => p.onSelection("opt-1", {}) }, "shell clear selection empty"),
      h("button", { onClick: () => p.onRemoveAgent("opt-1") }, "shell remove optional"),
      h("button", { onClick: () => p.onRemoveAgent("domain-analyst") }, "shell remove locked"),
      h("button", { onClick: () => p.onAddAgent() }, "shell add"),
      h("button", { onClick: () => p.onAddAgent("opt-1") }, "shell add before"),
      h(
        "button",
        { onClick: () => p.onTreeChange?.([{ ...p.pipelineAgents[0], name: "Renamed on canvas" }]) },
        "shell change tree",
      ),
      h("button", { onClick: () => p.onRequestAddSubAgent?.("opt-1") }, "shell request sub-agent"),
    );
  }

  return { CanvasView: CanvasViewShell };
});

import { AgentsPopup, type SelectionsMap } from "./AgentsPopup";

// ─── Builders ────────────────────────────────────────────────────────────────

function makeAgent(id: string, name: string, overrides: Partial<AgentDef> = {}): AgentDef {
  return {
    id,
    name,
    role: "role",
    description: `${name} description`,
    pipeline_type: "user_stories",
    order: 1,
    icon: "🧪",
    estimated_duration: 30,
    has_skill: false,
    ...overrides,
  };
}

const LOCKED = makeAgent("domain-analyst", "Domain Analyst");
const OPTIONAL = makeAgent("opt-1", "Optional One");
const LIB_PICK = makeAgent("lib-pick", "Library Pick");
const ROSTER = [LOCKED, OPTIONAL];

function preloaded(workflows: WorkflowSummary[] = []) {
  return {
    agents: {
      agents: [LOCKED, OPTIONAL, LIB_PICK],
      totalCount: 3,
      pipelines: {},
      status: "succeeded" as const,
      error: null,
    },
    global: { ...globalReducer(undefined, { type: "@@test/init" }), workflows },
  };
}

type PopupProps = React.ComponentProps<typeof AgentsPopup>;

function renderPopup(overrides: Partial<PopupProps> = {}, workflows: WorkflowSummary[] = []) {
  const props: PopupProps = {
    isOpen: true,
    onClose: vi.fn(),
    agents: ROSTER,
    pipelineType: "user_stories",
    onAddAgent: vi.fn(),
    onRemoveAgent: vi.fn(),
    onReorder: vi.fn(),
    onSelectionsChange: vi.fn(),
    ...overrides,
  };
  const view = renderWithProviders(<AgentsPopup {...props} />, { preloadedState: preloaded(workflows) });
  return { ...view, props };
}

function shellSelections(): SelectionsMap {
  return JSON.parse(screen.getByLabelText("canvas selections").textContent ?? "{}") as SelectionsMap;
}

/** The library's close control is an icon-only button right after its search box. */
function libraryCloseButton(): HTMLElement {
  return screen.getByRole("textbox", { name: "Search agents" }).parentElement!.nextElementSibling as HTMLElement;
}

describe("AgentsPopup", () => {
  let consoleLog: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.clearAllMocks();
    api.getToken.mockReturnValue("tok");
    api.getCapabilities.mockResolvedValue({ capabilities: [], model_catalog: [] });
    api.saveUserWorkflow.mockResolvedValue({ id: "wf-1" });
    // The component logs its mount seed; keep the test output clean.
    consoleLog = vi.spyOn(console, "log").mockImplementation(() => undefined);
  });

  afterEach(() => {
    consoleLog.mockRestore();
  });

  describe("visibility and header", () => {
    it("renders nothing when closed", () => {
      renderPopup({ isOpen: false });

      expect(screen.queryByText(/Advanced Workflow Configuration/)).not.toBeInTheDocument();
    });

    it("falls back to the pipeline type in the title when no workflow matches", () => {
      renderPopup();

      expect(screen.getByRole("heading", { name: /Advanced Workflow Configuration\s*— user_stories$/ })).toBeInTheDocument();
    });

    it("uses the matching workflow's name in the title", () => {
      const workflow = { id: "user_stories", name: "Backlog Builder", display_name: "Display Name" } as WorkflowSummary;

      renderPopup({}, [workflow]);

      expect(screen.getByRole("heading", { name: /Advanced Workflow Configuration\s*— Backlog Builder$/ })).toBeInTheDocument();
    });

    it("uses the display name when the workflow has no name", () => {
      const workflow = { id: "user_stories", name: "", display_name: "Display Name" } as WorkflowSummary;

      renderPopup({}, [workflow]);

      expect(screen.getByRole("heading", { name: /Advanced Workflow Configuration\s*— Display Name$/ })).toBeInTheDocument();
    });

    it("shows the agent count and pipeline label on the Agents tab", () => {
      renderPopup();

      expect(screen.getByText("2 agents · User Stories")).toBeInTheDocument();
      expect(screen.getByText("(2)")).toBeInTheDocument();
      expect(screen.getByText("Core = locked")).toBeInTheDocument();
    });

    it("falls back to the raw pipeline type when it has no label", () => {
      renderPopup({ pipelineType: "my_flow" as PopupProps["pipelineType"] });

      expect(screen.getByText("2 agents · my_flow")).toBeInTheDocument();
    });
  });

  describe("canvas hand-off", () => {
    it("passes the roster, selections and add capability to the canvas", () => {
      renderPopup({ initialSelections: { "opt-1": { retry: 2 } } });

      const list = within(screen.getByRole("list", { name: "canvas agents" }));
      expect(list.getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Domain Analyst", "Optional One"]);
      expect(shellSelections()).toEqual({ "opt-1": { retry: 2 } });
      expect(screen.getByLabelText("canvas can-add-more")).toHaveTextContent("true");
    });

    it("forwards canAddMore=false to the canvas", () => {
      renderPopup({ canAddMore: false });

      expect(screen.getByLabelText("canvas can-add-more")).toHaveTextContent("false");
    });

    it("flattens and de-duplicates declared capabilities for the canvas", () => {
      renderPopup({
        declaredCapabilities: [
          { step: "s1", capabilities: ["a", "b"] },
          { step: "s2", capabilities: ["b", "c"] },
        ],
      });

      expect(screen.getByLabelText("canvas declared")).toHaveTextContent("a,b,c");
    });

    it("builds the canvas from manifest steps and seeds their declared gates", () => {
      const steps: ManifestStep[] = [{ agent: "opt-1", gates: ["human"] }];

      renderPopup({ manifestSteps: steps });

      expect(within(screen.getByRole("list", { name: "canvas agents" })).getAllByRole("listitem")).toHaveLength(1);
      expect(shellSelections()).toEqual({ "opt-1": { gates: ["human"] } });
    });

    it("lets the user's own live selection win over a manifest declaration", async () => {
      const user = userEvent.setup();
      renderPopup({ manifestSteps: [{ agent: "opt-1", gates: ["human"] }] });

      await user.click(screen.getByRole("button", { name: "shell select model" }));

      expect(shellSelections()).toEqual({ "opt-1": { model: "m1" } });
    });

    it("renders from the caller-owned selections when they are supplied", async () => {
      const user = userEvent.setup();
      const { props } = renderPopup({
        selections: { "opt-1": { retry: 3 } },
        initialSelections: { "opt-1": { retry: 1 } },
      });
      expect(shellSelections()).toEqual({ "opt-1": { retry: 3 } });

      await user.click(screen.getByRole("button", { name: "shell select model" }));

      // The edit is reported upward, but the controlled map still drives rendering.
      expect(props.onSelectionsChange).toHaveBeenCalledWith({ "opt-1": { model: "m1" } });
      expect(shellSelections()).toEqual({ "opt-1": { retry: 3 } });
    });
  });

  describe("selection edits", () => {
    it("reports a lever chosen on the canvas as a new selections map", async () => {
      const user = userEvent.setup();
      const { props } = renderPopup();

      await user.click(screen.getByRole("button", { name: "shell select model" }));

      expect(props.onSelectionsChange).toHaveBeenCalledWith({ "opt-1": { model: "m1" } });
      expect(shellSelections()).toEqual({ "opt-1": { model: "m1" } });
    });

    it.each(["shell clear selection undefined", "shell clear selection empty"])(
      "drops the agent's entry when the canvas reports an empty selection (%s)",
      async (buttonName) => {
        const user = userEvent.setup();
        const { props } = renderPopup({ initialSelections: { "opt-1": { retry: 2 } } });

        await user.click(screen.getByRole("button", { name: buttonName }));

        expect(props.onSelectionsChange).toHaveBeenCalledWith({});
        expect(shellSelections()).toEqual({});
      },
    );

    it("forwards a tree change from the canvas to onReorder", async () => {
      const user = userEvent.setup();
      const { props } = renderPopup();

      await user.click(screen.getByRole("button", { name: "shell change tree" }));

      expect(props.onReorder).toHaveBeenCalledWith([{ ...LOCKED, name: "Renamed on canvas" }]);
    });
  });

  describe("removing agents", () => {
    it("removes an optional agent", async () => {
      const user = userEvent.setup();
      const { props } = renderPopup();

      await user.click(screen.getByRole("button", { name: "shell remove optional" }));

      expect(props.onRemoveAgent).toHaveBeenCalledWith("opt-1");
    });

    it("refuses to remove a locked core agent", async () => {
      const user = userEvent.setup();
      const { props } = renderPopup();

      await user.click(screen.getByRole("button", { name: "shell remove locked" }));

      expect(props.onRemoveAgent).not.toHaveBeenCalled();
    });
  });

  describe("cancelling", () => {
    it.each([
      ["footer Cancel button", () => screen.getByRole("button", { name: "Cancel" })],
      [
        "header close button",
        () => screen.getByRole("heading", { name: /Advanced Workflow Configuration/ }).nextElementSibling!.lastElementChild as HTMLElement,
      ],
    ])("dismisses an untouched session via the %s without re-emitting anything", async (_label, target) => {
      const user = userEvent.setup();
      const { props } = renderPopup();

      await user.click(target());

      expect(props.onClose).toHaveBeenCalledTimes(1);
      expect(props.onReorder).not.toHaveBeenCalled();
      expect(props.onSelectionsChange).not.toHaveBeenCalled();
    });

    it("dismisses via the backdrop", async () => {
      const user = userEvent.setup();
      const { props } = renderPopup();
      const heading = screen.getByRole("heading", { name: /Advanced Workflow Configuration/ });
      // The backdrop is the panel's previous sibling inside the fixed overlay.
      const panel = heading.closest("div.relative") as HTMLElement;

      await user.click(panel.previousElementSibling as HTMLElement);

      expect(props.onClose).toHaveBeenCalledTimes(1);
    });

    it("restores the original selections when cancelled after a lever edit", async () => {
      const user = userEvent.setup();
      const original = { "opt-1": { retry: 1 } };
      const { props } = renderPopup({ initialSelections: original });
      await user.click(screen.getByRole("button", { name: "shell select model" }));
      expect(props.onSelectionsChange).toHaveBeenLastCalledWith({ "opt-1": { model: "m1" } });

      await user.click(screen.getByRole("button", { name: "Cancel" }));

      expect(props.onSelectionsChange).toHaveBeenLastCalledWith(original);
      expect(props.onReorder).toHaveBeenCalledWith(ROSTER);
      expect(props.onClose).toHaveBeenCalledTimes(1);
    });

    it("restores the original roster when cancelled after a tree edit", async () => {
      const user = userEvent.setup();
      const { props } = renderPopup();
      await user.click(screen.getByRole("button", { name: "shell change tree" }));

      await user.click(screen.getByRole("button", { name: "Cancel" }));

      expect(props.onReorder).toHaveBeenLastCalledWith(ROSTER);
      expect(props.onClose).toHaveBeenCalledTimes(1);
    });

    it("snapshots only the first edit so a later edit cannot overwrite the restore point", async () => {
      const user = userEvent.setup();
      const { props } = renderPopup();
      await user.click(screen.getByRole("button", { name: "shell select model" }));
      await user.click(screen.getByRole("button", { name: "shell clear selection undefined" }));
      await user.click(screen.getByRole("button", { name: "shell select model" }));

      await user.click(screen.getByRole("button", { name: "Cancel" }));

      expect(props.onSelectionsChange).toHaveBeenLastCalledWith({});
    });

    it("stages an edit when an agent is removed so Cancel restores the roster", async () => {
      const user = userEvent.setup();
      const { props } = renderPopup();
      await user.click(screen.getByRole("button", { name: "shell remove optional" }));

      await user.click(screen.getByRole("button", { name: "Cancel" }));

      expect(props.onReorder).toHaveBeenCalledWith(ROSTER);
    });
  });

  describe("open in full canvas and override toggle", () => {
    it("offers Open in full canvas only when a handler is supplied", async () => {
      const user = userEvent.setup();
      const onOpenInCanvas = vi.fn();
      const { unmount } = renderPopup({ onOpenInCanvas });

      await user.click(screen.getByRole("button", { name: /open in full canvas/i }));
      expect(onOpenInCanvas).toHaveBeenCalledTimes(1);
      unmount();

      renderPopup();
      expect(screen.queryByRole("button", { name: /open in full canvas/i })).not.toBeInTheDocument();
    });

    it("shows the override checkbox reflecting the active state and reports toggles", async () => {
      const user = userEvent.setup();
      const onToggleOverride = vi.fn();
      renderPopup({ overrideAvailable: true, overrideActive: false, onToggleOverride });
      const checkbox = screen.getByRole("checkbox", { name: "Use my version" });
      expect(checkbox).not.toBeChecked();

      await user.click(checkbox);

      expect(onToggleOverride).toHaveBeenCalledWith(true);
    });

    it("shows the override checkbox checked while the override is active", () => {
      renderPopup({ overrideAvailable: true, overrideActive: true, onToggleOverride: vi.fn() });

      expect(screen.getByRole("checkbox", { name: "Use my version" })).toBeChecked();
    });

    it.each([
      ["no override saved", { overrideAvailable: false, onToggleOverride: vi.fn() }],
      ["no toggle handler", { overrideAvailable: true }],
    ])("hides the override checkbox when there is %s", (_label, extra) => {
      renderPopup(extra);

      expect(screen.queryByRole("checkbox", { name: "Use my version" })).not.toBeInTheDocument();
    });
  });

  describe("tabs", () => {
    it("switches to the Workflow tab with hooks and capabilities, and back", async () => {
      const user = userEvent.setup();
      renderPopup();

      await user.click(screen.getByRole("button", { name: /^workflow/i }));

      expect(screen.getByText(/No hooks attached/)).toBeInTheDocument();
      expect(await screen.findByText("No capabilities available")).toBeInTheDocument();
      expect(screen.queryByTestId("canvas-shell")).not.toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: /^agents/i }));
      expect(screen.getByTestId("canvas-shell")).toBeInTheDocument();
    });

    it("shows how many hooks are attached on the Workflow tab", async () => {
      const user = userEvent.setup();
      renderWithProviders(<AgentsPopup isOpen onClose={vi.fn()} agents={ROSTER} pipelineType="user_stories" />, {
        preloadedState: {
          ...preloaded(),
          hooks: {
            hooks: [
              {
                id: "h1",
                name: "h1",
                display_name: "Hook One",
                description: "d",
                content: "",
                event: "Stop",
                trigger: "t",
                compatible_agents: [],
                tags: [],
              },
            ],
            totalCount: 1,
            hookEvents: [],
            status: "succeeded" as const,
            error: null,
          },
        },
      });
      await user.click(screen.getByRole("button", { name: /^workflow/i }));
      await user.click(screen.getByRole("button", { name: /add hook/i }));

      await user.click(screen.getByRole("button", { name: "Add" }));

      expect(screen.getByRole("button", { name: /^workflow\s*1$/i })).toBeInTheDocument();
    });
  });

  describe("agent library", () => {
    it("adds a picked agent at the end when the library is opened from Browse", async () => {
      const user = userEvent.setup();
      const { props } = renderPopup();

      await user.click(screen.getByRole("button", { name: /browse agent library/i }));
      await user.click(within(await screen.findByTestId("library-card-lib-pick")).getByRole("button", { name: "+ Add" }));

      expect(props.onAddAgent).toHaveBeenCalledWith(LIB_PICK, undefined);
      await waitFor(() => expect(screen.queryByRole("heading", { name: "Add agent" })).not.toBeInTheDocument());
    });

    it("hides agents that are already in the roster from the library", async () => {
      const user = userEvent.setup();
      renderPopup();

      await user.click(screen.getByRole("button", { name: /browse agent library/i }));
      await screen.findByTestId("library-card-lib-pick");

      expect(screen.queryByTestId("library-card-opt-1")).not.toBeInTheDocument();
    });

    it("passes the canvas insert position through to onAddAgent", async () => {
      const user = userEvent.setup();
      const { props } = renderPopup();

      await user.click(screen.getByRole("button", { name: "shell add before" }));
      await user.click(within(await screen.findByTestId("library-card-lib-pick")).getByRole("button", { name: "+ Add" }));

      expect(props.onAddAgent).toHaveBeenCalledWith(LIB_PICK, "opt-1");
    });

    it("forgets the insert position when the library is closed without a pick", async () => {
      const user = userEvent.setup();
      const { props } = renderPopup();
      await user.click(screen.getByRole("button", { name: "shell add before" }));
      await screen.findByRole("heading", { name: "Add agent" });
      await user.click(libraryCloseButton());
      await waitFor(() => expect(screen.queryByRole("heading", { name: "Add agent" })).not.toBeInTheDocument());

      await user.click(screen.getByRole("button", { name: /browse agent library/i }));
      await user.click(within(await screen.findByTestId("library-card-lib-pick")).getByRole("button", { name: "+ Add" }));

      expect(props.onAddAgent).toHaveBeenCalledWith(LIB_PICK, undefined);
    });

    it("stages an edit when an agent is added so Cancel restores the roster", async () => {
      const user = userEvent.setup();
      const { props } = renderPopup();
      await user.click(screen.getByRole("button", { name: "shell add" }));
      await user.click(within(await screen.findByTestId("library-card-lib-pick")).getByRole("button", { name: "+ Add" }));
      await waitFor(() => expect(screen.queryByRole("heading", { name: "Add agent" })).not.toBeInTheDocument());

      await user.click(screen.getByRole("button", { name: "Cancel" }));

      expect(props.onReorder).toHaveBeenCalledWith(ROSTER);
    });

    it("does not add anything when the host supplies no onAddAgent handler", async () => {
      const user = userEvent.setup();
      renderPopup({ onAddAgent: undefined });

      await user.click(screen.getByRole("button", { name: /browse agent library/i }));
      await user.click(within(await screen.findByTestId("library-card-lib-pick")).getByRole("button", { name: "+ Add" }));

      await waitFor(() => expect(screen.queryByRole("heading", { name: "Add agent" })).not.toBeInTheDocument());
    });

    it("nests a picked agent under the requested parent as a sub-agent", async () => {
      const user = userEvent.setup();
      const { props } = renderPopup();

      await user.click(screen.getByRole("button", { name: "shell request sub-agent" }));
      const card = await screen.findByTestId("library-card-lib-pick");
      expect(within(card).getByRole("button", { name: "+ Sub-agent" })).toHaveAttribute(
        "title",
        "Add as sub-agent of Optional One",
      );
      await user.click(within(card).getByTestId("library-add-sub-lib-pick"));

      expect(props.onReorder).toHaveBeenCalledWith([
        LOCKED,
        { ...OPTIONAL, children: [LIB_PICK], strategy: "sequential" },
      ]);
      await waitFor(() => expect(screen.queryByRole("heading", { name: "Add agent" })).not.toBeInTheDocument());
    });

    it("drops the sub-agent target when the library is reopened from Browse", async () => {
      const user = userEvent.setup();
      renderPopup();
      await user.click(screen.getByRole("button", { name: "shell request sub-agent" }));
      await screen.findByTestId("library-add-sub-lib-pick");
      await user.click(libraryCloseButton());
      await waitFor(() => expect(screen.queryByRole("heading", { name: "Add agent" })).not.toBeInTheDocument());

      await user.click(screen.getByRole("button", { name: /browse agent library/i }));

      await screen.findByTestId("library-card-lib-pick");
      expect(screen.queryByTestId("library-add-sub-lib-pick")).not.toBeInTheDocument();
    });
  });

  describe("saving the workflow", () => {
    async function saveAs(user: ReturnType<typeof userEvent.setup>, name: string, description?: string) {
      await user.click(screen.getByRole("button", { name: "Save workflow" }));
      await user.type(await screen.findByLabelText("Workflow name"), name);
      if (description) await user.type(screen.getByLabelText(/Description/), description);
      await user.click(screen.getByRole("button", { name: "Save" }));
    }

    it("saves a new workflow with its name, description and ordered agent ids, then closes", async () => {
      const user = userEvent.setup();
      const { props } = renderPopup();

      await saveAs(user, "My flow", "What it makes");

      await waitFor(() => expect(props.onClose).toHaveBeenCalledTimes(1));
      expect(api.saveUserWorkflow).toHaveBeenCalledWith("tok", undefined, {
        name: "My flow",
        description: "What it makes",
        base_pipeline_type: "user_stories",
        agent_ids: ["domain-analyst", "opt-1"],
      });
    });

    it("omits an empty description from the payload", async () => {
      const user = userEvent.setup();
      renderPopup();

      await saveAs(user, "No description");

      await waitFor(() => expect(api.saveUserWorkflow).toHaveBeenCalledTimes(1));
      expect(api.saveUserWorkflow.mock.calls[0][2]).not.toHaveProperty("description");
    });

    it("includes the live selections in the payload when any lever is set", async () => {
      const user = userEvent.setup();
      renderPopup();
      await user.click(screen.getByRole("button", { name: "shell select model" }));

      await saveAs(user, "With levers");

      await waitFor(() => expect(api.saveUserWorkflow).toHaveBeenCalledTimes(1));
      expect(api.saveUserWorkflow.mock.calls[0][2].selections).toEqual({ "opt-1": { model: "m1" } });
    });

    it("keeps the saved edits instead of restoring the snapshot after a successful save", async () => {
      const user = userEvent.setup();
      const onSelectionsChange = vi.fn();
      const { props } = renderPopup({ onSelectionsChange });
      await user.click(screen.getByRole("button", { name: "shell select model" }));
      const callsBeforeSave = onSelectionsChange.mock.calls.length;

      await saveAs(user, "Keep edits");

      await waitFor(() => expect(props.onClose).toHaveBeenCalledTimes(1));
      expect(onSelectionsChange).toHaveBeenCalledTimes(callsBeforeSave);
      expect(props.onReorder).not.toHaveBeenCalled();
    });

    it("bumps the canvas layout reset signal when saving starts", async () => {
      const user = userEvent.setup();
      renderPopup();
      expect(screen.getByLabelText("canvas reset signal")).toHaveTextContent("0");

      await saveAs(user, "Layout");

      await waitFor(() => expect(screen.getByLabelText("canvas reset signal")).toHaveTextContent("1"));
    });

    it("updates a reopened workflow in place without asking for a name", async () => {
      const user = userEvent.setup();
      const { props } = renderPopup({
        userWorkflowId: "wf-9",
        savedName: "Existing",
        savedDescription: "Existing description",
      });

      await user.click(screen.getByRole("button", { name: "Save workflow" }));

      await waitFor(() => expect(props.onClose).toHaveBeenCalledTimes(1));
      expect(screen.queryByLabelText("Workflow name")).not.toBeInTheDocument();
      expect(api.saveUserWorkflow).toHaveBeenCalledWith("tok", "wf-9", {
        name: "Existing",
        description: "Existing description",
        base_pipeline_type: "user_stories",
        agent_ids: ["domain-analyst", "opt-1"],
      });
    });

    it("updates in place without a description when the saved one is missing", async () => {
      const user = userEvent.setup();
      renderPopup({ userWorkflowId: "wf-9", savedName: "Existing" });

      await user.click(screen.getByRole("button", { name: "Save workflow" }));

      await waitFor(() => expect(api.saveUserWorkflow).toHaveBeenCalledTimes(1));
      expect(api.saveUserWorkflow.mock.calls[0][2]).not.toHaveProperty("description");
    });

    it("asks for a name when the workflow id is known but it has no saved name", async () => {
      const user = userEvent.setup();
      renderPopup({ userWorkflowId: "wf-9" });

      await user.click(screen.getByRole("button", { name: "Save workflow" }));

      expect(await screen.findByLabelText("Workflow name")).toBeInTheDocument();
      expect(api.saveUserWorkflow).not.toHaveBeenCalled();
    });

    it("shows the server's error message and keeps the modal open when saving fails", async () => {
      const user = userEvent.setup();
      api.saveUserWorkflow.mockRejectedValue(new Error("name already taken"));
      const { props } = renderPopup();

      await saveAs(user, "Dup");

      expect(await screen.findByRole("alert")).toHaveTextContent("name already taken");
      expect(props.onClose).not.toHaveBeenCalled();
    });

    it("falls back to a generic error when the failure carries no message", async () => {
      const user = userEvent.setup();
      api.saveUserWorkflow.mockRejectedValue(undefined);
      renderPopup();

      await saveAs(user, "Dup");

      expect(await screen.findByRole("alert")).toHaveTextContent("Failed to save workflow.");
    });

    it("reports not-authenticated without calling the API when there is no token", async () => {
      const user = userEvent.setup();
      api.getToken.mockReturnValue(null);
      renderPopup();

      await saveAs(user, "Anon");

      expect(await screen.findByRole("alert")).toHaveTextContent("Not authenticated.");
      expect(api.saveUserWorkflow).not.toHaveBeenCalled();
    });

    it("clears a previous save error when Save workflow is clicked again", async () => {
      const user = userEvent.setup();
      api.saveUserWorkflow.mockRejectedValueOnce(new Error("first failure"));
      renderPopup();
      await saveAs(user, "Retry");
      await screen.findByRole("alert");

      await user.click(screen.getByRole("button", { name: "Save workflow" }));

      await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
    });

    it("closes the name dialog from its own Cancel without closing the popup", async () => {
      const user = userEvent.setup();
      const { props } = renderPopup();
      await user.click(screen.getByRole("button", { name: "Save workflow" }));
      const dialogTitle = await screen.findByRole("heading", { name: "Save workflow" });
      const modal = dialogTitle.closest("div.max-w-\\[340px\\]") as HTMLElement;

      await user.click(within(modal).getByRole("button", { name: "Cancel" }));

      await waitFor(() => expect(screen.queryByLabelText("Workflow name")).not.toBeInTheDocument());
      expect(props.onClose).not.toHaveBeenCalled();
    });

    it("does not let the name dialog be cancelled while a save is in flight", async () => {
      const user = userEvent.setup();
      api.saveUserWorkflow.mockReturnValue(new Promise(() => undefined));
      renderPopup();
      await user.click(screen.getByRole("button", { name: "Save workflow" }));
      const dialogTitle = await screen.findByRole("heading", { name: "Save workflow" });
      const modal = dialogTitle.closest("div.max-w-\\[340px\\]") as HTMLElement;
      await user.type(within(modal).getByLabelText("Workflow name"), "Slow");
      await user.click(within(modal).getByRole("button", { name: "Save" }));
      await waitFor(() => expect(api.saveUserWorkflow).toHaveBeenCalledTimes(1));

      await user.click(within(modal).getByRole("button", { name: "Cancel" }));

      expect(screen.getByLabelText("Workflow name")).toBeInTheDocument();
    });
  });
});
