import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderWithProviders, screen, fireEvent, waitFor, within } from "@/test/renderWithProviders";
import userEvent from "@testing-library/user-event";
import type { AgentDef, AgentRunState, PipelineRunState } from "@/types/index";

// Browser speech API wrapper: the only boundary controlled in this file. The
// returned state is mutable so a test can flip it and rerender.
const speech = vi.hoisted(() => ({
  state: { isListening: false, transcript: "", isSupported: true },
  startListening: vi.fn(),
  stopListening: vi.fn(),
}));

vi.mock("@/hooks/useSpeechRecognition", () => ({
  useSpeechRecognition: () => ({
    ...speech.state,
    startListening: speech.startListening,
    stopListening: speech.stopListening,
  }),
}));

import { WorkflowView } from "./WorkflowView";

function makeAgent(overrides: Partial<AgentDef> & Pick<AgentDef, "id" | "name">): AgentDef {
  return {
    role: "role",
    description: `${overrides.name} description`,
    pipeline_type: "user_stories",
    order: 1,
    icon: "🧪",
    estimated_duration: 60,
    has_skill: false,
    ...overrides,
  };
}

const ALPHA = makeAgent({ id: "alpha", name: "Alpha Agent", order: 1, estimated_duration: 90 });
const BETA = makeAgent({ id: "beta", name: "Beta Agent", order: 2, estimated_duration: 60 });
const PPT_AGENT = makeAgent({ id: "deck", name: "Deck Agent", pipeline_type: "ppt", order: 1 });
const SHARED_AGENT = makeAgent({
  id: "shared",
  name: "Shared Agent",
  pipeline_type: ["ppt", "prototype"],
  order: 3,
});
const CUSTOM_TEMPLATE = makeAgent({
  id: "custom-agent",
  name: "Custom Agent",
  pipeline_type: "custom",
  order: 1,
});

function stateWith(agents: AgentDef[]) {
  return {
    agents: { agents, totalCount: agents.length, pipelines: {}, status: "succeeded" as const, error: null },
  };
}

function makeRunAgent(id: string, status: AgentRunState["status"]): AgentRunState {
  return {
    id,
    name: `Run ${id}`,
    role: "role",
    icon: "🤖",
    status,
    output: "",
    thinking: "",
    duration: null,
    error: null,
    index: 0,
  };
}

function makeRunState(overrides: Partial<PipelineRunState> = {}): PipelineRunState {
  return {
    isRunning: false,
    pipeline_type: "",
    agents: [],
    currentAgentIndex: -1,
    totalDuration: null,
    completedCount: 0,
    ...overrides,
  };
}

interface ViewProps {
  pipelineType?: "user_stories" | "ppt" | "prototype";
  userMessage?: string;
  onClose?: () => void;
  pipelineState?: PipelineRunState;
  onStartPipeline?: (type: string, message: string, agentIds?: string[]) => void;
  onResetPipeline?: () => void;
  onViewResults?: (pipelineType: string) => void;
}

function view(props: ViewProps = {}) {
  return (
    <WorkflowView
      pipelineType={props.pipelineType ?? "user_stories"}
      userMessage={props.userMessage ?? ""}
      onClose={props.onClose ?? vi.fn()}
      pipelineState={props.pipelineState}
      onStartPipeline={props.onStartPipeline}
      onResetPipeline={props.onResetPipeline}
      onViewResults={props.onViewResults}
    />
  );
}

function renderView(props: ViewProps = {}, agents: AgentDef[] = [ALPHA, BETA, PPT_AGENT, SHARED_AGENT]) {
  return renderWithProviders(view(props), { preloadedState: stateWith(agents) });
}

function agentRows(): string[] {
  return screen.queryAllByText(/^(Alpha|Beta|Deck|Shared) Agent$|^New agent$/).map((el) => el.textContent ?? "");
}

function rowOf(name: string): HTMLElement {
  // Rows are native-draggable containers; there is no role for them.
  return screen.getByText(name).closest('[draggable="true"]') as HTMLElement;
}

function fileInput(container: HTMLElement): HTMLInputElement {
  // The file input is visually hidden and unlabeled, so it has no semantic query.
  return container.querySelector('input[type="file"]') as HTMLInputElement;
}

function textFile(name: string, bytes = 10): File {
  return new File([new Uint8Array(bytes)], name, { type: "text/plain" });
}

describe("WorkflowView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    speech.state = { isListening: false, transcript: "", isSupported: true };
    // jsdom lacks scrollIntoView, which PipelineGraph calls on the active agent.
    Element.prototype.scrollIntoView = vi.fn();
  });

  afterEach(() => {
    // @ts-expect-error restoring the jsdom default (property is absent there)
    delete Element.prototype.scrollIntoView;
  });

  describe("build step header and agent list", () => {
    it("shows the selected feature label with agent count and estimated minutes", () => {
      renderView();

      expect(screen.getByRole("heading", { name: "User Stories" })).toBeInTheDocument();
      // ALPHA 90s + BETA 60s = 150s => ceil(2.5) = 3 min
      expect(screen.getByText("2 agents • ~3 min")).toBeInTheDocument();
    });

    it("lists only agents for the pipeline type, ordered by their order field", () => {
      renderView({}, [BETA, ALPHA, PPT_AGENT]);

      expect(agentRows()).toEqual(["Alpha Agent", "Beta Agent"]);
    });

    it("includes multi-pipeline agents whose list contains the selected type", () => {
      renderView({ pipelineType: "prototype" });

      expect(agentRows()).toEqual(["Shared Agent"]);
      expect(screen.getByRole("heading", { name: "Prototype" })).toBeInTheDocument();
    });

    it("falls back to the Presentation label for the ppt type", () => {
      renderView({ pipelineType: "ppt" });

      expect(screen.getByRole("heading", { name: "Presentation" })).toBeInTheDocument();
      expect(agentRows()).toEqual(["Deck Agent", "Shared Agent"]);
    });

    it("shows an empty list with a zero count when the library has no matching agents", () => {
      renderView({}, []);

      expect(screen.getByText("(0)")).toBeInTheDocument();
      expect(screen.getByText("0 agents • ~0 min")).toBeInTheDocument();
      expect(agentRows()).toEqual([]);
    });

    it("shows each agent's estimated duration in seconds", () => {
      renderView();

      expect(within(rowOf("Alpha Agent")).getByText("~90s")).toBeInTheDocument();
      expect(within(rowOf("Beta Agent")).getByText("~60s")).toBeInTheDocument();
    });

    it("expands an agent's description on click and collapses it on a second click", async () => {
      const user = userEvent.setup();
      renderView();

      await user.click(screen.getByText("Alpha Agent"));
      expect(screen.getByText("Alpha Agent description")).toBeInTheDocument();

      await user.click(screen.getByText("Alpha Agent"));
      expect(screen.queryByText("Alpha Agent description")).not.toBeInTheDocument();
    });

    it("keeps only one agent description expanded at a time", async () => {
      const user = userEvent.setup();
      renderView();

      await user.click(screen.getByText("Alpha Agent"));
      await user.click(screen.getByText("Beta Agent"));

      expect(screen.queryByText("Alpha Agent description")).not.toBeInTheDocument();
      expect(screen.getByText("Beta Agent description")).toBeInTheDocument();
    });

    it("removes an agent and updates the count when its Remove button is clicked", async () => {
      const user = userEvent.setup();
      renderView();

      await user.click(within(rowOf("Alpha Agent")).getByRole("button", { name: "Remove" }));

      expect(agentRows()).toEqual(["Beta Agent"]);
      expect(screen.getByText("(1)")).toBeInTheDocument();
    });
  });

  describe("closing", () => {
    it("calls onClose from the Back button in the build step", async () => {
      const user = userEvent.setup();
      const onClose = vi.fn();
      renderView({ onClose });

      await user.click(screen.getByRole("button", { name: "Back" }));

      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it("calls onClose from the Close button", async () => {
      const user = userEvent.setup();
      const onClose = vi.fn();
      renderView({ onClose });

      await user.click(screen.getByRole("button", { name: "Close" }));

      expect(onClose).toHaveBeenCalledTimes(1);
    });
  });

  describe("idea input", () => {
    it("is labelled and prefilled from the userMessage prop", () => {
      renderView({ userMessage: "Build a todo app" });

      expect(screen.getByLabelText("Describe your idea")).toHaveValue("Build a todo app");
    });

    it("updates as the user types", async () => {
      const user = userEvent.setup();
      renderView();

      await user.type(screen.getByLabelText("Describe your idea"), "hello");

      expect(screen.getByLabelText("Describe your idea")).toHaveValue("hello");
    });
  });

  describe("running a workflow", () => {
    it("disables Run Workflow for an empty or whitespace-only brief", async () => {
      const user = userEvent.setup();
      renderView();
      const run = screen.getByRole("button", { name: /run workflow/i });
      expect(run).toBeDisabled();

      await user.type(screen.getByLabelText("Describe your idea"), "   ");

      expect(run).toBeDisabled();
    });

    it("starts the pipeline with the type, trimmed brief and ordered agent ids", async () => {
      const user = userEvent.setup();
      const onStartPipeline = vi.fn();
      renderView({ onStartPipeline, userMessage: "  My brief  " });

      await user.click(screen.getByRole("button", { name: /run workflow/i }));

      expect(onStartPipeline).toHaveBeenCalledTimes(1);
      expect(onStartPipeline).toHaveBeenCalledWith("user_stories", "My brief", ["alpha", "beta"]);
    });

    it("omits a removed agent from the started pipeline", async () => {
      const user = userEvent.setup();
      const onStartPipeline = vi.fn();
      renderView({ onStartPipeline, userMessage: "brief" });
      await user.click(within(rowOf("Alpha Agent")).getByRole("button", { name: "Remove" }));

      await user.click(screen.getByRole("button", { name: /run workflow/i }));

      expect(onStartPipeline).toHaveBeenCalledWith("user_stories", "brief", ["beta"]);
    });

    it("does not throw when Run Workflow is clicked without an onStartPipeline handler", async () => {
      const user = userEvent.setup();
      renderView({ userMessage: "brief" });

      await user.click(screen.getByRole("button", { name: /run workflow/i }));

      expect(screen.getByRole("button", { name: /run workflow/i })).toBeEnabled();
    });

    it("starts the pipeline with Cmd+Enter in the idea input", async () => {
      const user = userEvent.setup();
      const onStartPipeline = vi.fn();
      renderView({ onStartPipeline, userMessage: "brief" });

      screen.getByLabelText("Describe your idea").focus();
      await user.keyboard("{Meta>}{Enter}{/Meta}");

      expect(onStartPipeline).toHaveBeenCalledWith("user_stories", "brief", ["alpha", "beta"]);
    });

    it("does not start on a plain Enter", async () => {
      const user = userEvent.setup();
      const onStartPipeline = vi.fn();
      renderView({ onStartPipeline, userMessage: "brief" });

      screen.getByLabelText("Describe your idea").focus();
      await user.keyboard("{Enter}");

      expect(onStartPipeline).not.toHaveBeenCalled();
    });

    it("does not start on Cmd+Enter when the brief is empty", async () => {
      const user = userEvent.setup();
      const onStartPipeline = vi.fn();
      renderView({ onStartPipeline });

      screen.getByLabelText("Describe your idea").focus();
      await user.keyboard("{Meta>}{Enter}{/Meta}");

      expect(onStartPipeline).not.toHaveBeenCalled();
    });

    it("does not start on Cmd+Enter when every agent was removed", async () => {
      const user = userEvent.setup();
      const onStartPipeline = vi.fn();
      renderView({ onStartPipeline, userMessage: "brief" }, [ALPHA]);
      await user.click(within(rowOf("Alpha Agent")).getByRole("button", { name: "Remove" }));

      screen.getByLabelText("Describe your idea").focus();
      await user.keyboard("{Meta>}{Enter}{/Meta}");

      expect(onStartPipeline).not.toHaveBeenCalled();
      expect(screen.getByRole("button", { name: /run workflow/i })).toBeDisabled();
    });
  });

  describe("drag to reorder", () => {
    // user-event has no drag-and-drop API, so these use fireEvent to dispatch
    // the native dragstart / dragover / drop / dragend events the handlers read.
    it("moves a dragged agent to the drop position and runs in the new order", async () => {
      const user = userEvent.setup();
      const onStartPipeline = vi.fn();
      renderView({ onStartPipeline, userMessage: "brief" });

      fireEvent.dragStart(rowOf("Alpha Agent"));
      fireEvent.dragOver(rowOf("Beta Agent"));
      fireEvent.drop(rowOf("Beta Agent"));

      expect(agentRows()).toEqual(["Beta Agent", "Alpha Agent"]);
      await user.click(screen.getByRole("button", { name: /run workflow/i }));
      expect(onStartPipeline).toHaveBeenCalledWith("user_stories", "brief", ["beta", "alpha"]);
    });

    it("keeps the order when an agent is dropped on itself", () => {
      renderView();

      fireEvent.dragStart(rowOf("Alpha Agent"));
      fireEvent.drop(rowOf("Alpha Agent"));

      expect(agentRows()).toEqual(["Alpha Agent", "Beta Agent"]);
    });

    it("keeps the order when a drop happens without a drag start", () => {
      renderView();

      fireEvent.drop(rowOf("Beta Agent"));

      expect(agentRows()).toEqual(["Alpha Agent", "Beta Agent"]);
    });

    it("forgets the dragged agent after dragend so a later drop does nothing", () => {
      renderView();

      fireEvent.dragStart(rowOf("Alpha Agent"));
      fireEvent.dragEnd(rowOf("Alpha Agent"));
      fireEvent.drop(rowOf("Beta Agent"));

      expect(agentRows()).toEqual(["Alpha Agent", "Beta Agent"]);
    });

    it("allows dropping by cancelling the default dragover behaviour", () => {
      renderView();

      const notCancelled = fireEvent.dragOver(rowOf("Beta Agent"));

      expect(notCancelled).toBe(false);
    });
  });

  describe("agent library", () => {
    it.each(["Browse Library", "Add Agent"])("opens the library from the %s button", async (label) => {
      const user = userEvent.setup();
      renderView();

      await user.click(screen.getByRole("button", { name: new RegExp(label, "i") }));

      expect(await screen.findByRole("heading", { name: "Add agent" })).toBeInTheDocument();
    });

    it("adds an agent picked from the library and closes the library", async () => {
      const user = userEvent.setup();
      renderView({}, [ALPHA, PPT_AGENT]);
      await user.click(screen.getByRole("button", { name: /browse library/i }));
      const card = await screen.findByTestId("library-card-deck");

      await user.click(within(card).getByRole("button", { name: "+ Add" }));

      await waitFor(() => expect(screen.queryByRole("heading", { name: "Add agent" })).not.toBeInTheDocument());
      expect(agentRows()).toEqual(["Alpha Agent", "Deck Agent"]);
      expect(screen.getByText("(2)")).toBeInTheDocument();
    });

    it("assigns an added agent the next order position at the end of the pipeline", async () => {
      const user = userEvent.setup();
      const onStartPipeline = vi.fn();
      renderView({ onStartPipeline, userMessage: "brief" }, [ALPHA, PPT_AGENT]);
      await user.click(screen.getByRole("button", { name: /browse library/i }));
      await user.click(within(await screen.findByTestId("library-card-deck")).getByRole("button", { name: "+ Add" }));

      await user.click(screen.getByRole("button", { name: /run workflow/i }));

      expect(onStartPipeline).toHaveBeenCalledWith("user_stories", "brief", ["alpha", "deck"]);
    });

    it("does not add an agent that is already in the pipeline", async () => {
      const user = userEvent.setup();
      renderView({}, [ALPHA]);
      await user.click(screen.getByRole("button", { name: /browse library/i }));

      await user.click(within(await screen.findByTestId("library-card-alpha")).getByRole("button", { name: "+ Add" }));

      await waitFor(() => expect(screen.queryByRole("heading", { name: "Add agent" })).not.toBeInTheDocument());
      expect(agentRows()).toEqual(["Alpha Agent"]);
    });

    it("mints a fresh instance for each add of the blank custom-agent template", async () => {
      const user = userEvent.setup();
      renderView({}, [ALPHA, CUSTOM_TEMPLATE]);

      for (let added = 1; added <= 2; added += 1) {
        await user.click(screen.getByRole("button", { name: /browse library/i }));
        await user.click(
          within(await screen.findByTestId("library-card-custom-agent")).getByRole("button", { name: "+ Add" }),
        );
        await waitFor(() =>
          expect(screen.queryByRole("heading", { name: "Add agent" })).not.toBeInTheDocument(),
        );
        expect(screen.getAllByText("New agent")).toHaveLength(added);
      }
    });

    it("closes the library without adding when its close control is used", async () => {
      const user = userEvent.setup();
      renderView({}, [ALPHA, PPT_AGENT]);
      await user.click(screen.getByRole("button", { name: /browse library/i }));
      await screen.findByRole("heading", { name: "Add agent" });

      // The library's close control is an icon-only button with no accessible
      // name, so it is the nameless button right after the search box.
      const search = screen.getByRole("textbox", { name: "Search agents" });
      const closeButton = search.parentElement!.nextElementSibling as HTMLElement;
      await user.click(closeButton);

      await waitFor(() => expect(screen.queryByRole("heading", { name: "Add agent" })).not.toBeInTheDocument());
      expect(agentRows()).toEqual(["Alpha Agent"]);
    });
  });

  describe("attachments", () => {
    it("opens the native file picker from the attach button", async () => {
      const user = userEvent.setup();
      const { container } = renderView();
      const click = vi.spyOn(fileInput(container), "click");

      await user.click(screen.getByRole("button", { name: /attach file/i }));

      expect(click).toHaveBeenCalledTimes(1);
    });

    it("lists the attached file with its size and appends a marker to an empty brief", async () => {
      const user = userEvent.setup();
      const { container } = renderView();

      await user.upload(fileInput(container), textFile("notes.txt", 500));

      expect(screen.getByText("notes.txt")).toBeInTheDocument();
      expect(screen.getByText("(500B)")).toBeInTheDocument();
      expect(screen.getByLabelText("Describe your idea")).toHaveValue("[Attached: notes.txt]");
    });

    it("appends the marker after existing brief text separated by a blank line", async () => {
      const user = userEvent.setup();
      const { container } = renderView({ userMessage: "My brief" });

      await user.upload(fileInput(container), textFile("notes.txt"));

      expect(screen.getByLabelText("Describe your idea")).toHaveValue("My brief\n\n[Attached: notes.txt]");
    });

    it("joins several files from one selection into one marker", async () => {
      const user = userEvent.setup();
      const { container } = renderView();

      await user.upload(fileInput(container), [textFile("a.txt"), textFile("b.txt")]);

      expect(screen.getByLabelText("Describe your idea")).toHaveValue("[Attached: a.txt, b.txt]");
    });

    it.each([
      [1023, "(1023B)"],
      [1024, "(1.0KB)"],
      [2048, "(2.0KB)"],
      [1048575, "(1024.0KB)"],
      [1048576, "(1.0MB)"],
      [1572864, "(1.5MB)"],
    ])("formats a %s byte file as %s", async (bytes, label) => {
      const user = userEvent.setup();
      const { container } = renderView();

      await user.upload(fileInput(container), textFile("sized.txt", bytes));

      expect(screen.getByText(label)).toBeInTheDocument();
    });

    it("removes only the chosen file's marker when files were attached in separate selections", async () => {
      const user = userEvent.setup();
      const { container } = renderView();
      await user.upload(fileInput(container), textFile("a.txt"));
      await user.upload(fileInput(container), textFile("b.txt"));
      expect(screen.getByLabelText("Describe your idea")).toHaveValue("[Attached: a.txt]\n\n[Attached: b.txt]");

      // Remove b first: the first marker does not name it and must be left alone.
      const chipB = screen.getByText("b.txt").closest("span") as HTMLElement;
      await user.click(within(chipB).getByRole("button"));

      expect(screen.getByLabelText("Describe your idea")).toHaveValue("[Attached: a.txt]");
      expect(screen.queryByText("b.txt")).not.toBeInTheDocument();
    });

    it("leaves a later marker intact when the first marker's file is removed", async () => {
      const user = userEvent.setup();
      const { container } = renderView();
      await user.upload(fileInput(container), textFile("a.txt"));
      await user.upload(fileInput(container), textFile("b.txt"));

      const chipA = screen.getByText("a.txt").closest("span") as HTMLElement;
      await user.click(within(chipA).getByRole("button"));

      expect(screen.getByLabelText("Describe your idea")).toHaveValue("[Attached: b.txt]");
    });

    it("does not touch the brief when the removed file's name is not in any marker", async () => {
      const user = userEvent.setup();
      const { container } = renderView();
      await user.upload(fileInput(container), textFile("a.txt"));
      const textarea = screen.getByLabelText("Describe your idea");
      // The user hand-edits the marker away; removing the chip must not corrupt the text.
      await user.clear(textarea);
      await user.type(textarea, "plain text");

      const chip = screen.getByText("a.txt").closest("span") as HTMLElement;
      await user.click(within(chip).getByRole("button"));

      expect(textarea).toHaveValue("plain text");
    });

    it("clears the file input value so the same file can be picked again", async () => {
      const user = userEvent.setup();
      const { container } = renderView();
      const input = fileInput(container);

      await user.upload(input, textFile("a.txt"));

      expect(input.value).toBe("");
    });
  });

  describe("voice input", () => {
    it("disables the mic and explains why when speech recognition is unsupported", () => {
      speech.state = { isListening: false, transcript: "", isSupported: false };
      renderView();

      expect(
        screen.getByRole("button", { name: "Speech recognition not supported in this browser" }),
      ).toBeDisabled();
    });

    it("starts listening from the voice button", async () => {
      const user = userEvent.setup();
      renderView();

      await user.click(screen.getByRole("button", { name: "Voice input" }));

      expect(speech.startListening).toHaveBeenCalledTimes(1);
      expect(speech.stopListening).not.toHaveBeenCalled();
    });

    it("shows the listening placeholder and stops listening from the same button", async () => {
      const user = userEvent.setup();
      speech.state = { isListening: true, transcript: "", isSupported: true };
      renderView();

      expect(screen.getByPlaceholderText("🎙️ Listening... speak your idea")).toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "Stop listening" }));

      expect(speech.stopListening).toHaveBeenCalledTimes(1);
      expect(speech.startListening).not.toHaveBeenCalled();
    });

    it("uses the transcript alone as the brief when nothing was typed before", () => {
      speech.state = { isListening: true, transcript: "build a todo app", isSupported: true };
      renderView();

      expect(screen.getByLabelText("Describe your idea")).toHaveValue("build a todo app");
    });

    it("replaces, not appends, the transcript after the text typed before listening", async () => {
      const user = userEvent.setup();
      const { rerender } = renderView({ userMessage: "Existing" });
      await user.click(screen.getByRole("button", { name: "Voice input" }));

      speech.state = { isListening: true, transcript: "spoken", isSupported: true };
      rerender(view({ userMessage: "Existing" }));
      expect(screen.getByLabelText("Describe your idea")).toHaveValue("Existing spoken");

      speech.state = { isListening: true, transcript: "spoken more", isSupported: true };
      rerender(view({ userMessage: "Existing" }));
      expect(screen.getByLabelText("Describe your idea")).toHaveValue("Existing spoken more");
    });

    it("leaves the brief alone while listening until a transcript arrives", () => {
      speech.state = { isListening: true, transcript: "", isSupported: true };
      renderView({ userMessage: "Typed" });

      expect(screen.getByLabelText("Describe your idea")).toHaveValue("Typed");
    });
  });

  describe("running and complete steps", () => {
    const runAgents = [makeRunAgent("r1", "running"), makeRunAgent("r2", "idle")];

    it("switches to the running view and hides the Back button while a pipeline runs", async () => {
      renderView({ pipelineState: makeRunState({ isRunning: true, agents: runAgents, currentAgentIndex: 0 }) });

      expect(await screen.findByRole("heading", { name: "Running Pipeline" })).toBeInTheDocument();
      // The graph mounts once the build view finishes its exit animation.
      expect(await screen.findByText("0 of 2 agents complete")).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Back" })).not.toBeInTheDocument();
      expect(screen.queryByLabelText("Describe your idea")).not.toBeInTheDocument();
    });

    it("labels the running graph with the selected type when the run has no pipeline type", async () => {
      renderView({ pipelineState: makeRunState({ isRunning: true, agents: runAgents }) });

      await screen.findByText("0 of 2 agents complete");

      expect(screen.getByText("User Stories")).toBeInTheDocument();
    });

    it("labels the running graph with the run's own pipeline type when it has one", async () => {
      renderView({
        pipelineState: makeRunState({ isRunning: true, pipeline_type: "ppt", agents: runAgents }),
      });

      await screen.findByText("0 of 2 agents complete");

      expect(screen.getByText("Presentation")).toBeInTheDocument();
    });

    it("moves to the complete view with results actions once every agent has finished", async () => {
      const done = [makeRunAgent("r1", "done"), makeRunAgent("r2", "done")];
      const { rerender } = renderView({
        pipelineState: makeRunState({ isRunning: true, agents: runAgents, currentAgentIndex: 0 }),
      });
      await screen.findByRole("heading", { name: "Running Pipeline" });

      rerender(
        view({
          pipelineState: makeRunState({
            isRunning: false,
            agents: done,
            completedCount: 2,
            currentAgentIndex: 1,
            totalDuration: 12.34,
          }),
        }),
      );

      expect(await screen.findByRole("heading", { name: "Pipeline Complete" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /view results/i })).toHaveTextContent("(12.3s)");
      expect(screen.getByRole("button", { name: /run another pipeline/i })).toBeInTheDocument();
    });

    it("omits the duration on View Results when the total duration is unknown", async () => {
      const done = [makeRunAgent("r1", "done")];
      const { rerender } = renderView({
        pipelineState: makeRunState({ isRunning: true, agents: done }),
      });
      await screen.findByRole("heading", { name: "Running Pipeline" });

      rerender(
        view({ pipelineState: makeRunState({ isRunning: false, agents: done, completedCount: 1, totalDuration: null }) }),
      );

      const viewResults = await screen.findByRole("button", { name: /view results/i });
      expect(viewResults).not.toHaveTextContent("(");
    });

    it("stays in the running view when the run stops before every agent completed", async () => {
      const partial = [makeRunAgent("r1", "done"), makeRunAgent("r2", "error")];
      const { rerender } = renderView({
        pipelineState: makeRunState({ isRunning: true, agents: partial }),
      });
      await screen.findByRole("heading", { name: "Running Pipeline" });

      rerender(view({ pipelineState: makeRunState({ isRunning: false, agents: partial, completedCount: 1 }) }));

      expect(screen.getByRole("heading", { name: "Running Pipeline" })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /view results/i })).not.toBeInTheDocument();
    });

    it("does not jump to the complete view for a finished run that never ran in this session", () => {
      const done = [makeRunAgent("r1", "done")];
      renderView({ pipelineState: makeRunState({ isRunning: false, agents: done, completedCount: 1 }) });

      expect(screen.getByRole("heading", { name: "User Stories" })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /view results/i })).not.toBeInTheDocument();
    });

    async function renderComplete(props: ViewProps) {
      const done = [makeRunAgent("r1", "done")];
      const handlers = { ...props };
      const { rerender } = renderView({
        ...handlers,
        pipelineState: makeRunState({ isRunning: true, agents: done }),
      });
      await screen.findByRole("heading", { name: "Running Pipeline" });
      rerender(
        view({
          ...handlers,
          pipelineState: makeRunState({ isRunning: false, agents: done, completedCount: 1, totalDuration: 5 }),
        }),
      );
      await screen.findByRole("heading", { name: "Pipeline Complete" });
    }

    it("reports the selected pipeline type when View Results is clicked", async () => {
      const user = userEvent.setup();
      const onViewResults = vi.fn();
      await renderComplete({ pipelineType: "ppt", onViewResults });

      await user.click(screen.getByRole("button", { name: /view results/i }));

      expect(onViewResults).toHaveBeenCalledWith("ppt");
    });

    it("does not throw when View Results is clicked without a handler", async () => {
      const user = userEvent.setup();
      await renderComplete({});

      await user.click(screen.getByRole("button", { name: /view results/i }));

      expect(screen.getByRole("button", { name: /view results/i })).toBeEnabled();
    });

    it("resets the pipeline and returns home when Run Another Pipeline is clicked", async () => {
      const user = userEvent.setup();
      const onResetPipeline = vi.fn();
      const onClose = vi.fn();
      await renderComplete({ onResetPipeline, onClose });

      await user.click(screen.getByRole("button", { name: /run another pipeline/i }));

      expect(onResetPipeline).toHaveBeenCalledTimes(1);
      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it("still returns home when Run Another Pipeline is clicked without a reset handler", async () => {
      const user = userEvent.setup();
      const onClose = vi.fn();
      await renderComplete({ onClose });

      await user.click(screen.getByRole("button", { name: /run another pipeline/i }));

      expect(onClose).toHaveBeenCalledTimes(1);
    });
  });
});
