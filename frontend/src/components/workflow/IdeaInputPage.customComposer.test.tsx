/**
 * IdeaInputPage — the `custom` (compose-your-own) launch flow: brief-driven
 * agent suggestions, the companion-pipeline banner, roster editing callbacks
 * (add / insert / cap / template / remove / reorder), the Output-format control
 * (ISS-777) and the deliverable override each agent group pins at launch.
 *
 * Boundaries: AgentsPopup is a double that renders the roster/limits the PAGE
 * computes and hands the page's callbacks back to the test (the real popup is
 * covered by its own tests); ReviewGatesSection is inert; speech is stubbed.
 */
import { act, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { IdeaInputPage } from "./IdeaInputPage";
import renderWithProviders from "@/test/renderWithProviders";
import type { AgentDef, WorkflowType } from "@/types/index";

interface PopupHandle {
  agents: AgentDef[];
  canAddMore?: boolean;
  onAddAgent?: (agent: AgentDef, insertBeforeId?: string) => void;
  onRemoveAgent?: (agentId: string) => void;
  onReorder?: (agents: AgentDef[]) => void;
}

const popup = vi.hoisted(() => ({ current: null as PopupHandle | null }));

vi.mock("./AgentsPopup", () => ({
  AgentsPopup: (props: PopupHandle) => {
    popup.current = props;
    return (
      <div>
        <ul aria-label="Popup roster">
          {props.agents.map((a) => (
            <li key={a.id}>{`${a.id} #${a.order} ${a.name}`}</li>
          ))}
        </ul>
        <p role="status" aria-label="Can add more">{String(props.canAddMore)}</p>
      </div>
    );
  },
}));

vi.mock("./ReviewGatesSection", () => ({ ReviewGatesSection: () => null }));

vi.mock("@/hooks/useSpeechRecognition", () => ({
  useSpeechRecognition: () => ({
    isListening: false,
    transcript: "",
    startListening: vi.fn(),
    stopListening: vi.fn(),
    isSupported: false,
  }),
}));

function lib(id: string, pipelineType: string, name = `${id} Agent`, order = 1): AgentDef {
  return {
    id,
    name,
    role: "role",
    description: `${id} description`,
    pipeline_type: pipelineType,
    order,
    icon: "x",
    estimated_duration: 0,
    has_skill: false,
  };
}

const STORY_IDS = [
  "domain-analyst",
  "epic-architect",
  "story-estimator",
  "nfr-specialist",
  "backlog-reviewer",
  "backlog-compiler",
];
const STORY_AGENTS = STORY_IDS.map((id, i) => lib(id, "user_stories", `${id} Agent`, i + 1));
const SECURITY = lib("security-auditor", "custom", "Security Auditor Agent");
const DOCS = lib("documentation-agent", "custom", "Documentation Agent");
const PROTOTYPE_BUILD = lib("prototype-build", "prototype", "Prototype Builder");
const TEMPLATE = lib("custom-agent", "custom", "Custom agent");

function renderPage(
  workflowType: WorkflowType,
  agents: AgentDef[],
  extra: Partial<React.ComponentProps<typeof IdeaInputPage>> = {},
  onRun = vi.fn(),
) {
  renderWithProviders(
    <IdeaInputPage workflowType={workflowType} onBack={vi.fn()} onRun={onRun} {...extra} />,
    {
      preloadedState: {
        agents: { agents, totalCount: agents.length, pipelines: {}, status: "succeeded", error: null },
      },
    },
  );
  return { onRun };
}

const roster = () =>
  within(screen.getByRole("list", { name: "Popup roster" }))
    .queryAllByRole("listitem")
    .map((li) => li.textContent);
const rosterIds = () => roster().map((t) => t?.split(" ")[0]);
const addAgent = (agent: AgentDef, before?: string) =>
  act(() => popup.current!.onAddAgent!(agent, before));
const brief = () => screen.getByRole("textbox", { name: "Brief description" });

describe("IdeaInputPage custom workflow", () => {
  it("starts with an empty roster and a disabled Run button that asks for agents", () => {
    renderPage("custom", STORY_AGENTS);

    expect(screen.getByRole("heading", { name: "What do you want to achieve?" })).toBeInTheDocument();
    expect(rosterIds()).toEqual([]);
    expect(screen.getByRole("button", { name: "Add agents first" })).toBeDisabled();
  });

  it("suggests the matching agents once the brief is long enough to infer intent", async () => {
    const user = userEvent.setup();
    renderPage("custom", STORY_AGENTS);

    await user.type(brief(), "short");
    expect(screen.queryByText("Suggested agents for your brief")).not.toBeInTheDocument();

    await user.type(brief(), " but now: write user stories for refunds");

    expect(screen.getByText("Suggested agents for your brief")).toBeInTheDocument();
    // " Agent" is stripped from each chip label; the pipeline order is preserved.
    const chips = STORY_IDS.map((id) => screen.getByRole("button", { name: id }));
    expect(chips).toHaveLength(6);
  });

  it("adds a suggested agent to the roster and removes it from the suggestions", async () => {
    const user = userEvent.setup();
    renderPage("custom", STORY_AGENTS);
    await user.type(brief(), "Write user stories for refunds");

    await user.click(screen.getByRole("button", { name: "epic-architect" }));

    expect(rosterIds()).toEqual(["epic-architect"]);
    expect(screen.queryByRole("button", { name: "epic-architect" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run workflow" })).toBeEnabled();
  });

  it("hides the suggestions after Dismiss is clicked", async () => {
    const user = userEvent.setup();
    renderPage("custom", STORY_AGENTS);
    await user.type(brief(), "Write user stories for refunds");

    await user.click(screen.getByRole("button", { name: "Dismiss" }));

    expect(screen.queryByText("Suggested agents for your brief")).not.toBeInTheDocument();
  });

  it("offers to complete a partially added pipeline and puts the full group first, keeping other agents after it", async () => {
    const user = userEvent.setup();
    renderPage("custom", [...STORY_AGENTS, SECURITY]);
    addAgent(SECURITY);
    addAgent(STORY_AGENTS[1]);

    expect(await screen.findByText("Complete User Stories Pipeline")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Add 5 missing" }));

    expect(rosterIds()).toEqual([...STORY_IDS, "security-auditor"]);
    expect(screen.queryByText("Complete User Stories Pipeline")).not.toBeInTheDocument();
  });

  it("does not offer a companion banner when the roster is empty or already complete", () => {
    renderPage("custom", STORY_AGENTS);
    expect(screen.queryByText("Complete User Stories Pipeline")).not.toBeInTheDocument();

    STORY_AGENTS.forEach((a) => addAgent(a));

    expect(rosterIds()).toEqual(STORY_IDS);
    expect(screen.queryByText("Complete User Stories Pipeline")).not.toBeInTheDocument();
  });

  it("appends an added agent to the end of a custom roster", () => {
    renderPage("custom", [SECURITY, DOCS, PROTOTYPE_BUILD]);

    addAgent(SECURITY);
    addAgent(DOCS);

    expect(roster()).toEqual(["security-auditor #1 Security Auditor Agent", "documentation-agent #2 Documentation Agent"]);
  });

  it("inserts an agent before the named slot and renumbers every step", () => {
    renderPage("custom", [SECURITY, DOCS, PROTOTYPE_BUILD]);
    addAgent(SECURITY);
    addAgent(PROTOTYPE_BUILD);

    addAgent(DOCS, "prototype-build");

    expect(roster()).toEqual([
      "security-auditor #1 Security Auditor Agent",
      "documentation-agent #2 Documentation Agent",
      "prototype-build #3 Prototype Builder",
    ]);
  });

  it("appends when the named insertion slot is not in the roster", () => {
    renderPage("custom", [SECURITY, DOCS]);
    addAgent(SECURITY);

    addAgent(DOCS, "no-such-step");

    expect(rosterIds()).toEqual(["security-auditor", "documentation-agent"]);
  });

  it("ignores an add for an agent that is already in the roster", () => {
    renderPage("custom", [SECURITY]);
    addAgent(SECURITY);

    addAgent(SECURITY);

    expect(rosterIds()).toEqual(["security-auditor"]);
  });

  it("mints a fresh instance id for the blank custom-agent template on every add", () => {
    renderPage("custom", [TEMPLATE]);

    addAgent(TEMPLATE);
    addAgent(TEMPLATE);

    const entries = roster();
    expect(entries).toHaveLength(2);
    entries.forEach((entry) => expect(entry).toMatch(/^[a-z0-9][a-z0-9-]* #\d New agent$/));
    expect(new Set(rosterIds()).size).toBe(2);
    expect(rosterIds()).not.toContain("custom-agent");
  });

  it("places the first added agent at the start of an empty built-in roster", () => {
    renderPage("user_stories", [SECURITY]);
    expect(rosterIds()).toEqual([]);

    addAgent(SECURITY);

    expect(roster()).toEqual(["security-auditor #1 Security Auditor Agent"]);
  });

  it("removes an agent via the popup callback", () => {
    renderPage("custom", [SECURITY, DOCS]);
    addAgent(SECURITY);
    addAgent(DOCS);

    act(() => popup.current!.onRemoveAgent!("security-auditor"));

    expect(rosterIds()).toEqual(["documentation-agent"]);
  });

  it("adopts the order the popup reports when agents are reordered", () => {
    renderPage("custom", [SECURITY, DOCS]);
    addAgent(SECURITY);
    addAgent(DOCS);

    act(() => popup.current!.onReorder!([DOCS, SECURITY]));

    expect(rosterIds()).toEqual(["documentation-agent", "security-auditor"]);
  });

  it("stops accepting agents at the 16-agent cap of a custom workflow", () => {
    const many = Array.from({ length: 17 }, (_, i) => lib(`agent-${i + 1}`, "custom"));
    renderPage("custom", many, { initialAgentIds: many.slice(0, 16).map((a) => a.id) });
    expect(screen.getByRole("status", { name: "Can add more" })).toHaveTextContent("false");

    addAgent(many[16]);

    expect(rosterIds()).toHaveLength(16);
    expect(rosterIds()).not.toContain("agent-17");
  });

  it("stops accepting optional agents at the 5-agent cap of a built-in workflow and inserts before the final step", () => {
    const extras = Array.from({ length: 6 }, (_, i) => lib(`extra-${i + 1}`, "other"));
    renderPage("user_stories", [...STORY_AGENTS, ...extras]);
    expect(screen.getByRole("status", { name: "Can add more" })).toHaveTextContent("true");

    extras.forEach((a) => addAgent(a));

    // Each unpositioned add lands before the last (compiler) step, and the 6th is refused.
    expect(rosterIds()).toEqual([
      ...STORY_IDS.slice(0, 5),
      "extra-1",
      "extra-2",
      "extra-3",
      "extra-4",
      "extra-5",
      "backlog-compiler",
    ]);
    expect(screen.getByRole("status", { name: "Can add more" })).toHaveTextContent("false");
  });
});

describe("IdeaInputPage Output format and deliverable launch", () => {
  it("shows the Output format control, defaulting to markdown, for an agent set no group pins", async () => {
    const user = userEvent.setup();
    const { onRun } = renderPage("custom", [SECURITY]);
    addAgent(SECURITY);
    await user.type(brief(), "Audit the system");

    expect(screen.getByRole("combobox", { name: "Output format" })).toHaveValue(".md");
    await user.click(screen.getByRole("button", { name: "Run workflow" }));

    expect(onRun).toHaveBeenCalledWith("Audit the system", ["security-auditor"], "custom", {
      gate_agent_ids: [],
      selections: {
        __deliverable__: { strategy: "streamed_text", name: "output.md", mimetype: "text/markdown" },
      },
    });
  });

  it("launches an HTML deliverable when the user picks the HTML output format", async () => {
    const user = userEvent.setup();
    const { onRun } = renderPage("custom", [SECURITY]);
    addAgent(SECURITY);
    await user.type(brief(), "Audit the system");

    await user.selectOptions(screen.getByRole("combobox", { name: "Output format" }), ".html");
    await user.click(screen.getByRole("button", { name: "Run workflow" }));

    expect(onRun.mock.calls[0][3]).toEqual({
      gate_agent_ids: [],
      selections: {
        __deliverable__: { strategy: "streamed_text", name: "output.html", mimetype: "text/html" },
      },
    });
  });

  it("hides the Output format control and pins prototype.html with the task_loop strategy for a prototype build", async () => {
    const user = userEvent.setup();
    const { onRun } = renderPage("custom", [PROTOTYPE_BUILD]);
    addAgent(PROTOTYPE_BUILD);
    await user.type(brief(), "Build the prototype");

    expect(screen.queryByRole("combobox", { name: "Output format" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Run workflow" }));

    expect(onRun).toHaveBeenCalledWith("Build the prototype", ["prototype-build"], "custom", {
      gate_agent_ids: [],
      selections: {
        __deliverable__: { strategy: "single_file", name: "prototype.html", mimetype: "text/html" },
        "prototype-build": { strategy: "task_loop" },
      },
    });
  });

  it("does not offer an Output format control on a built-in workflow", () => {
    renderPage("user_stories", STORY_AGENTS);

    expect(screen.queryByRole("combobox", { name: "Output format" })).not.toBeInTheDocument();
  });
});
