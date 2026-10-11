/**
 * IdeaInputPage — launch context: the `migration` meta-pipeline sub-path
 * selector, catalog-derived page copy, saved-workflow seeds (`initial*` props),
 * the review-gate payload rules, and the Advanced summary line.
 *
 * Boundaries: AgentsPopup and ReviewGatesSection are doubles that expose only the
 * props/callbacks the PAGE owns; speech is stubbed; Redux is preloaded.
 */
import { act, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { combineReducers, configureStore } from "@reduxjs/toolkit";
import { describe, expect, it, vi } from "vitest";

import { IdeaInputPage } from "./IdeaInputPage";
import renderWithProviders from "@/test/renderWithProviders";
import { useSkillsHooks } from "@/context/SkillsHooksContext";
import agentsReducer, { fetchAgentLibrary } from "@/store/slices/agentsSlice";
import globalReducer from "@/store/slices/globalSlice";
import type { AgentDef, WorkflowType } from "@/types/index";

interface PopupHandle {
  agents: AgentDef[];
  isOpen: boolean;
  onClose: () => void;
}

vi.mock("./AgentsPopup", () => ({
  AgentsPopup: (props: PopupHandle) => (
    <div>
      <ul aria-label="Popup roster">
        {props.agents.map((a) => (
          <li key={a.id}>{a.id}</li>
        ))}
      </ul>
      <p role="status" aria-label="Popup open">{String(props.isOpen)}</p>
      <button type="button" onClick={props.onClose}>close popup</button>
    </div>
  ),
}));

interface GatesHandle {
  initialGateIds?: string[];
  onChange: (ids: string[], touched: boolean) => void;
}

vi.mock("./ReviewGatesSection", () => ({
  ReviewGatesSection: (props: GatesHandle) => (
    <section aria-label="Review gates">
      <p>{`seed: ${JSON.stringify(props.initialGateIds ?? null)}`}</p>
      <button type="button" onClick={() => props.onChange(["domain-analyst"], true)}>check gate</button>
      <button type="button" onClick={() => props.onChange([], false)}>untouch gates</button>
    </section>
  ),
}));

vi.mock("@/hooks/useSpeechRecognition", () => ({
  useSpeechRecognition: () => ({
    isListening: false,
    transcript: "",
    startListening: vi.fn(),
    stopListening: vi.fn(),
    isSupported: false,
  }),
}));

function lib(id: string, pipelineType: string, order = 1, duration = 0): AgentDef {
  return {
    id,
    name: `${id} Agent`,
    role: "role",
    description: `${id} description`,
    pipeline_type: pipelineType,
    order,
    icon: "x",
    estimated_duration: duration,
    has_skill: false,
  };
}

const DOMAIN = lib("domain-analyst", "user_stories", 1);
const EPIC = lib("epic-architect", "user_stories", 2);
const STORY_AGENTS = [DOMAIN, EPIC];
const MIGRATION_PLANNER = lib("migration-planner", "migration");
const MULE = lib("mule-agent", "mulesoft_to_springboot");
const DOTNET = lib("dotnet-agent", "dotnet_to_azure");

type PageProps = React.ComponentProps<typeof IdeaInputPage>;

function pageElement(workflowType: WorkflowType, onRun: PageProps["onRun"], extra: Partial<PageProps> = {}) {
  return <IdeaInputPage workflowType={workflowType} onBack={vi.fn()} onRun={onRun} {...extra} />;
}

function renderPage(
  workflowType: WorkflowType,
  agents: AgentDef[],
  extra: Partial<PageProps> = {},
  workflows: unknown[] = [],
) {
  const onRun = vi.fn();
  const result = renderWithProviders(pageElement(workflowType, onRun, extra), {
    preloadedState: {
      agents: { agents, totalCount: agents.length, pipelines: {}, status: "succeeded", error: null },
      global: { workflows } as never,
    },
  });
  return {
    onRun,
    rerenderPage: (nextType: WorkflowType, nextExtra: Partial<PageProps> = {}) =>
      result.rerender(pageElement(nextType, onRun, nextExtra)),
  };
}

const rosterIds = () =>
  within(screen.getByRole("list", { name: "Popup roster" }))
    .queryAllByRole("listitem")
    .map((li) => li.textContent);
const brief = () => screen.getByRole("textbox", { name: "Brief description" });

describe("IdeaInputPage migration meta-pipeline", () => {
  const AGENTS = [MIGRATION_PLANNER, MULE, DOTNET];

  it("blocks Run, Save and the Ctrl+Enter shortcut until a migration path is chosen", async () => {
    const user = userEvent.setup();
    const { onRun } = renderPage("migration", AGENTS);
    await user.type(brief(), "Move our estate");

    expect(screen.getByRole("heading", { name: "Modernise a legacy estate" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Pick a migration path" })).toBeDisabled();
    expect(screen.getByRole("button", { name: /save workflow/i })).toBeDisabled();
    await user.keyboard("{Control>}{Enter}{/Control}");

    expect(onRun).not.toHaveBeenCalled();
  });

  it("hides the review-gates section until a migration path is chosen", async () => {
    const user = userEvent.setup();
    renderPage("migration", AGENTS);
    expect(screen.queryByRole("region", { name: "Review gates" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Mulesoft → Spring Boot/ }));

    expect(screen.getByRole("region", { name: "Review gates" })).toBeInTheDocument();
  });

  it("switches heading, roster and the dispatched pipeline to the chosen sub-pipeline", async () => {
    const user = userEvent.setup();
    const { onRun } = renderPage("migration", AGENTS);
    await user.type(brief(), "Move our estate");

    await user.click(screen.getByRole("button", { name: /Mulesoft → Spring Boot/ }));

    expect(screen.getByRole("heading", { name: "Modernise off Mulesoft" })).toBeInTheDocument();
    expect(rosterIds()).toEqual(["mule-agent"]);
    await user.click(screen.getByRole("button", { name: "Run workflow" }));
    expect(onRun).toHaveBeenCalledWith("Move our estate", ["mule-agent"], "mulesoft_to_springboot", {
      gate_agent_ids: [],
    });
  });

  it("lets the user change the migration path to the .NET pipeline", async () => {
    const user = userEvent.setup();
    const { onRun } = renderPage("migration", AGENTS);
    await user.type(brief(), "Move our estate");
    await user.click(screen.getByRole("button", { name: /Mulesoft → Spring Boot/ }));

    await user.click(screen.getByRole("button", { name: /\.NET → Azure/ }));
    await user.click(screen.getByRole("button", { name: "Run workflow" }));

    expect(onRun.mock.calls[0][1]).toEqual(["dotnet-agent"]);
    expect(onRun.mock.calls[0][2]).toBe("dotnet_to_azure");
  });

  it("keeps Save as my version disabled until a migration path is chosen", async () => {
    const user = userEvent.setup();
    renderPage("migration", AGENTS, { workflowId: "migration" });

    expect(screen.getByRole("button", { name: /save as my version/i })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: /\.NET → Azure/ }));

    expect(screen.getByRole("button", { name: /save as my version/i })).toBeEnabled();
  });

  it("forgets the chosen path when the parent leaves and re-enters the migration type", async () => {
    const user = userEvent.setup();
    const { rerenderPage } = renderPage("migration", AGENTS);
    await user.click(screen.getByRole("button", { name: /Mulesoft → Spring Boot/ }));

    rerenderPage("user_stories");
    rerenderPage("migration");

    expect(await screen.findByRole("button", { name: "Pick a migration path" })).toBeDisabled();
  });
});

describe("IdeaInputPage page copy", () => {
  it("uses the curated copy for a hand-written workflow type", () => {
    renderPage("ppt", []);

    expect(screen.getByRole("heading", { name: "Specify the topic" })).toBeInTheDocument();
    expect(screen.getByText("Build an executive presentation")).toBeInTheDocument();
  });

  it("derives the copy from the live catalog row for a type with no curated copy", () => {
    renderPage("ex_A1_loop" as WorkflowType, [], {}, [
      { id: "ex_A1_loop", name: "ex_a1", display_name: "Loop Demo", description: "Runs a loop." },
    ]);

    expect(screen.getByText("Loop Demo")).toBeInTheDocument();
    expect(screen.getByText("Runs a loop.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Provide the brief" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Brief description" })).toHaveAttribute(
      "placeholder",
      "e.g. Describe what you'd like this workflow to do.",
    );
  });

  it("falls back to the catalog name and a generic subtitle when the row has no display name or description", () => {
    renderPage("ex_A1_loop" as WorkflowType, [], {}, [
      { id: "ex_A1_loop", name: "Loop Demo", display_name: null, description: "" },
    ]);

    expect(screen.getByText("Loop Demo")).toBeInTheDocument();
    expect(
      screen.getByText("Describe what you want and this workflow will run its steps."),
    ).toBeInTheDocument();
  });

  it("falls back to a generic page when the catalog has no row for the type", () => {
    renderPage("ex_A1_loop" as WorkflowType, []);

    expect(screen.getByText("Run a workflow")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Provide the brief" })).toBeInTheDocument();
  });
});

describe("IdeaInputPage saved-workflow seeds", () => {
  it("prefills the brief from initialInput", () => {
    renderPage("user_stories", STORY_AGENTS, { initialInput: "Saved brief text" });

    expect(brief()).toHaveValue("Saved brief text");
  });

  it("seeds the roster from initialAgentIds in saved order and drops ids the library does not know", async () => {
    const user = userEvent.setup();
    const { onRun } = renderPage("user_stories", STORY_AGENTS, {
      initialAgentIds: ["epic-architect", "ghost-agent", "domain-analyst"],
    });
    await user.type(brief(), "Rerun it");

    expect(rosterIds()).toEqual(["epic-architect", "domain-analyst"]);
    await user.click(screen.getByRole("button", { name: "Run workflow" }));
    expect(onRun.mock.calls[0][1]).toEqual(["epic-architect", "domain-analyst"]);
  });

  it("restores the saved roster once the agent library finishes loading after mount", async () => {
    const testStore = configureStore({
      reducer: combineReducers({ agents: agentsReducer, global: globalReducer }),
    });
    renderWithProviders(pageElement("user_stories", vi.fn(), { initialAgentIds: ["epic-architect"] }), {
      store: testStore as never,
    });
    expect(rosterIds()).toEqual([]);

    act(() => {
      testStore.dispatch(
        fetchAgentLibrary.fulfilled({ agents: STORY_AGENTS, total_count: 2, pipelines: {} }, "request-1", undefined),
      );
    });

    expect(rosterIds()).toEqual(["epic-architect"]);
  });

  it("keeps the roster empty when none of the saved agent ids exist in the library that loads later", () => {
    const testStore = configureStore({
      reducer: combineReducers({ agents: agentsReducer, global: globalReducer }),
    });
    renderWithProviders(pageElement("user_stories", vi.fn(), { initialAgentIds: ["ghost-agent"] }), {
      store: testStore as never,
    });

    act(() => {
      testStore.dispatch(
        fetchAgentLibrary.fulfilled({ agents: STORY_AGENTS, total_count: 2, pipelines: {} }, "request-1", undefined),
      );
    });

    expect(rosterIds()).toEqual([]);
  });

  it("returns to the workflow's default roster once the saved agent ids are cleared", () => {
    const { rerenderPage } = renderPage("user_stories", STORY_AGENTS, { initialAgentIds: ["epic-architect"] });
    expect(rosterIds()).toEqual(["epic-architect"]);

    rerenderPage("user_stories", { initialAgentIds: undefined });

    expect(rosterIds()).toEqual(["domain-analyst", "epic-architect"]);
  });

  it("empties the roster when a built-in workflow is switched to custom", () => {
    const { rerenderPage } = renderPage("user_stories", STORY_AGENTS);
    expect(rosterIds()).toEqual(["domain-analyst", "epic-architect"]);

    rerenderPage("custom");

    expect(rosterIds()).toEqual([]);
  });

  it("re-sends saved selections without the front-end-only _wizard key, plus saved model overrides", async () => {
    const user = userEvent.setup();
    const { onRun } = renderPage("user_stories", STORY_AGENTS, {
      initialSelections: { _wizard: { brief: "old" }, "domain-analyst": { retry: 1 } },
      initialModelOverrides: { "domain-analyst": "model-x" },
    });
    await user.type(brief(), "Rerun it");

    await user.click(screen.getByRole("button", { name: "Run workflow" }));

    expect(onRun.mock.calls[0][3]).toEqual({
      gate_agent_ids: [],
      selections: { "domain-analyst": { retry: 1 } },
      model_overrides: { "domain-analyst": "model-x" },
    });
  });

  it("passes the saved gate ids to the review-gates section", () => {
    renderPage("user_stories", STORY_AGENTS, { initialGateIds: ["epic-architect"] });

    expect(screen.getByText('seed: ["epic-architect"]')).toBeInTheDocument();
  });
});

describe("IdeaInputPage review-gate payload", () => {
  it("sends the checked gate ids once the user has touched the review gates", async () => {
    const user = userEvent.setup();
    const { onRun } = renderPage("user_stories", STORY_AGENTS);
    await user.type(brief(), "Review me");

    await user.click(screen.getByRole("button", { name: "check gate" }));
    await user.click(screen.getByRole("button", { name: "Run workflow" }));

    expect(onRun.mock.calls[0][3]).toEqual({ gate_agent_ids: ["domain-analyst"] });
  });

  it("sends only the other launch fields, without gate ids, when the gates report untouched", async () => {
    const user = userEvent.setup();
    const { onRun } = renderPage("user_stories", STORY_AGENTS, {
      initialModelOverrides: { "domain-analyst": "model-x" },
    });
    await user.type(brief(), "Review me");

    await user.click(screen.getByRole("button", { name: "untouch gates" }));
    await user.click(screen.getByRole("button", { name: "Run workflow" }));

    expect(onRun.mock.calls[0][3]).toEqual({ model_overrides: { "domain-analyst": "model-x" } });
  });

  it("omits extraParams entirely when the gates report untouched and nothing else is set", async () => {
    const user = userEvent.setup();
    const { onRun } = renderPage("user_stories", STORY_AGENTS);
    await user.type(brief(), "Review me");

    await user.click(screen.getByRole("button", { name: "untouch gates" }));
    await user.click(screen.getByRole("button", { name: "Run workflow" }));

    expect(onRun.mock.calls[0][3]).toBeUndefined();
  });
});

function HookAttacher() {
  const { attachHook } = useSkillsHooks();
  return (
    <>
      {["h1", "h2"].map((id) => (
        <button
          key={id}
          type="button"
          onClick={() => attachHook({ id, name: id, event: "e", trigger: "t" })}
        >
          {`attach ${id}`}
        </button>
      ))}
    </>
  );
}

describe("IdeaInputPage Advanced summary", () => {
  function renderSummary(agents: AgentDef[]) {
    renderWithProviders(
      <>
        {pageElement("user_stories", vi.fn())}
        <HookAttacher />
      </>,
      {
        preloadedState: {
          agents: { agents, totalCount: agents.length, pipelines: {}, status: "succeeded", error: null },
        },
      },
    );
    return screen.getByRole("button", { name: /^advanced/i });
  }

  it("shows a singular agent count and no duration when estimates are zero", () => {
    const summary = renderSummary([DOMAIN]);

    expect(summary).toHaveTextContent(/^Advanced1 agent$/);
  });

  it("shows the total estimate in seconds when it is under a minute", () => {
    const summary = renderSummary([lib("domain-analyst", "user_stories", 1, 20), lib("epic-architect", "user_stories", 2, 25)]);

    expect(summary).toHaveTextContent("2 agents · ~45s");
  });

  it("shows the total estimate in minutes from one minute upward", () => {
    const summary = renderSummary([lib("domain-analyst", "user_stories", 1, 60), lib("epic-architect", "user_stories", 2, 60)]);

    expect(summary).toHaveTextContent("2 agents · ~2m");
  });

  it("counts attached hooks with correct pluralisation", async () => {
    const user = userEvent.setup();
    renderSummary([DOMAIN]);

    await user.click(screen.getByRole("button", { name: "attach h1" }));
    expect(screen.getByRole("button", { name: /^advanced/i })).toHaveTextContent("1 agent · 1 hook");

    await user.click(screen.getByRole("button", { name: "attach h2" }));
    expect(screen.getByRole("button", { name: /^advanced/i })).toHaveTextContent("1 agent · 2 hooks");
  });

  it("opens the agents popup from Advanced and closes it again", async () => {
    const user = userEvent.setup();
    renderSummary([DOMAIN]);
    expect(screen.getByRole("status", { name: "Popup open" })).toHaveTextContent("false");

    await user.click(screen.getByRole("button", { name: /^advanced/i }));
    expect(screen.getByRole("status", { name: "Popup open" })).toHaveTextContent("true");

    await user.click(screen.getByRole("button", { name: "close popup" }));
    expect(screen.getByRole("status", { name: "Popup open" })).toHaveTextContent("false");
  });
});
