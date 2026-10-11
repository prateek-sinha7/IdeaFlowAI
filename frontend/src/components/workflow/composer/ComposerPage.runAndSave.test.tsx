/**
 * ComposerPage — Run once, Save, design-picker, add/reorder/remove and
 * declared-capability behaviour.
 *
 * Gap-closing companion to ComposerPage.test.tsx (chrome / identity / summary)
 * and ComposerPage.manifestPersistence.test.tsx (built-in manifest saves).
 *
 * Boundaries controlled here:
 *   - `@/lib/api` (token, save, workflow detail, capability/prompt fetchers)
 *   - `./DesignPickerModal` — replaced by a tiny shell exposing its public
 *     props (`open`, `designMode`, `onChange` updater, `onClose`). The real
 *     modal fetches catalogs from two further API modules and has its own
 *     tests; ComposerPage only owns the open/close + selection plumbing.
 * HTML5 drag-and-drop is dispatched with `fireEvent` because user-event cannot
 * express dragstart/dragover/drop.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  renderWithProviders,
  screen,
  within,
  waitFor,
  fireEvent,
} from "@/test/renderWithProviders";
import { act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useEffect } from "react";
import type { CapabilitiesPalette } from "@/lib/api";
import type { AgentDef, WorkflowRunConfig, WorkflowType } from "@/types/index";
import type { ManifestStep } from "@/store/api/userWorkflows";
import { useSkillsHooks } from "@/context/SkillsHooksContext";

const mockGetToken = vi.fn<() => string | null>();
const mockGetCapabilities = vi.fn();
const mockSaveUserWorkflow = vi.fn();
const mockGetWorkflowDetail = vi.fn();
vi.mock("@/lib/api", () => ({
  getToken: () => mockGetToken(),
  getCapabilities: (t: string) => mockGetCapabilities(t),
  saveUserWorkflow: (...a: unknown[]) => mockSaveUserWorkflow(...a),
  getWorkflowDetail: (...a: unknown[]) => mockGetWorkflowDetail(...a),
  getAgentPrompt: vi.fn().mockResolvedValue({ prompt_body: "", override: null, has_override: false }),
  saveAgentPromptOverride: vi.fn(),
  deleteAgentPromptOverride: vi.fn(),
}));

vi.mock("./DesignPickerModal", () => ({
  DesignPickerModal: (props: {
    open: boolean;
    designMode: string;
    onClose: () => void;
    onChange: (update: (prev: Record<string, unknown>) => Record<string, unknown>) => void;
  }) =>
    props.open ? (
      <div role="dialog" aria-label="Choose a design" data-mode={props.designMode}>
        <button
          type="button"
          onClick={() =>
            props.onChange((prev) => ({
              ...prev,
              templateId: "tpl-1",
              templateName: "Landing page",
              customTemplateBody: "<html/>",
            }))
          }
        >
          pick template
        </button>
        <button
          type="button"
          onClick={() =>
            props.onChange((prev) => ({
              ...prev,
              designSystemId: "ds-1",
              designSystemName: "Material",
              customDsBody: "tokens",
            }))
          }
        >
          pick design system
        </button>
        <button type="button" onClick={props.onClose}>
          close design picker
        </button>
      </div>
    ) : null,
}));

import { ComposerPage } from "./ComposerPage";

const PALETTE: CapabilitiesPalette = { capabilities: [], model_catalog: [] };

function agentDef(id: string, name: string, overrides: Partial<AgentDef> = {}): AgentDef {
  return {
    id,
    name,
    role: `${name} role`,
    description: `${name} description`,
    pipeline_type: "custom",
    order: 1,
    icon: "",
    estimated_duration: 60,
    has_skill: false,
    ...overrides,
  };
}

const ALPHA = agentDef("alpha-agent", "Alpha Agent");
const BETA = agentDef("beta-agent", "Beta Agent");
const GAMMA = agentDef("gamma-agent", "Gamma Agent");
const USER_STORY_LIBRARY = [
  agentDef("domain-analyst", "Domain Discovery Agent", { pipeline_type: "user_stories" }),
  agentDef("epic-architect", "Backlog Architecture Agent", { pipeline_type: "user_stories" }),
  agentDef("story-estimator", "Story Estimator Agent", { pipeline_type: "user_stories" }),
  agentDef("nfr-specialist", "NFR Specialist Agent", { pipeline_type: "user_stories" }),
  agentDef("backlog-reviewer", "Backlog Reviewer Agent", { pipeline_type: "user_stories" }),
  agentDef("backlog-compiler", "Backlog Compiler Agent", { pipeline_type: "user_stories" }),
];
const PROTOTYPE_BUILD = agentDef("prototype-build", "Prototype Builder Agent", {
  pipeline_type: "prototype",
});
const LIBRARY: AgentDef[] = [ALPHA, BETA, GAMMA, ...USER_STORY_LIBRARY, PROTOTYPE_BUILD];

function renderComposer(
  props: Record<string, unknown> = {},
  library: AgentDef[] = LIBRARY,
  children?: React.ReactNode,
) {
  const onBack = vi.fn();
  const utils = renderWithProviders(
    <>
      {children}
      <ComposerPage workflowType={"custom" as WorkflowType} onBack={onBack} {...props} />
    </>,
    {
      preloadedState: {
        agents: {
          agents: library,
          totalCount: library.length,
          pipelines: {},
          status: "succeeded",
          error: null,
        },
      },
    },
  );
  return { onBack, ...utils };
}

const customStep = (instance: string, extra: Partial<ManifestStep> = {}): ManifestStep => ({
  agent: "custom-agent",
  instance_id: instance,
  name: instance.toUpperCase(),
  prompt: `do ${instance}`,
  gates: [],
  depends_on: [],
  ...extra,
});

const DESIGN_RUN_CONFIG: WorkflowRunConfig = {
  deliverable: { strategy: "streamed_text", name: "output.md" },
  planner: "skip",
  clarify: { mode: "skip", defaults: [] },
  contextProvider: "opendesign",
};

type OnRunArgs = [string, string, string[], Record<string, unknown> | undefined];

async function toSimple(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: /^Simple$/ }));
}

async function typeBrief(user: ReturnType<typeof userEvent.setup>, text: string) {
  await user.type(screen.getByRole("textbox", { name: "Brief description" }), text);
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGetToken.mockReturnValue("test-token");
  mockGetCapabilities.mockResolvedValue(PALETTE);
  mockGetWorkflowDetail.mockResolvedValue({ steps: [] });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("ComposerPage — header chrome", () => {
  it("calls onBack from the Back button", async () => {
    const user = userEvent.setup();
    const { onBack } = renderComposer();

    await user.click(screen.getByRole("button", { name: "Back" }));

    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it("labels a built-in canvas as a copy of the named workflow and offers 'Save as copy'", () => {
    renderComposer({
      builtinCanvasType: "ppt",
      initialName: "Slide Deck",
      initialManifestSteps: [{ agent: "ppt-composer" }] as ManifestStep[],
    });

    expect(screen.getByText("Slide Deck · copy")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Save as copy/ })).toBeInTheDocument();
  });

  it("falls back to the built-in type in the eyebrow when no name was provided", () => {
    renderComposer({
      builtinCanvasType: "ppt",
      initialManifestSteps: [{ agent: "ppt-composer" }] as ManifestStep[],
    });

    expect(screen.getByText("ppt · copy")).toBeInTheDocument();
  });

  it("shows live agent count, singular review-gate label and rounded duration in the header summary", () => {
    renderComposer({
      initialAgentIds: ["alpha-agent", "beta-agent", "gamma-agent"],
      initialSelections: { "alpha-agent": { gates: ["human"] } },
    });

    const summary = screen.getByTestId("composer-header-summary");
    expect(summary).toHaveTextContent("3 agents");
    expect(summary).toHaveTextContent("1 review gate");
    expect(summary).toHaveTextContent("~3m");
  });

  it("never reports less than ~1m for an empty roster", () => {
    renderComposer();

    expect(screen.getByTestId("composer-header-summary")).toHaveTextContent("~1m");
  });

  it("disables Run once with an explanatory title when the parent supplies no onRun", () => {
    renderComposer();

    const run = screen.getByRole("button", { name: "Run once" });
    expect(run).toBeDisabled();
    expect(run).toHaveAttribute("title", "Run wiring lands in 41-06");
  });

  it("explains why Run once cannot go yet when onRun exists but the roster is empty", () => {
    renderComposer({ onRun: vi.fn() });

    expect(screen.getByRole("button", { name: "Run once" })).toHaveAttribute(
      "title",
      "Add at least one agent first",
    );
  });

  it("asks for a brief in the Run once title when agents exist but the brief is short", () => {
    renderComposer({ onRun: vi.fn(), initialAgentIds: ["alpha-agent"] });

    expect(screen.getByRole("button", { name: "Run once" })).toHaveAttribute(
      "title",
      "Add a brief first",
    );
  });
});

describe("ComposerPage — Run once validation", () => {
  it("reports a too-short brief from the Canvas view without launching", async () => {
    const user = userEvent.setup();
    const onRun = vi.fn();
    renderComposer({ onRun, initialAgentIds: ["alpha-agent"] });

    await user.click(screen.getByRole("button", { name: "Run once" }));

    expect(
      screen.getByText("Add a brief of at least 3 characters before running."),
    ).toBeInTheDocument();
    expect(onRun).not.toHaveBeenCalled();
  });

  it("reports a too-short brief from the Simple view and focuses the brief box", async () => {
    const user = userEvent.setup();
    const onRun = vi.fn();
    renderComposer({ onRun, initialAgentIds: ["alpha-agent"] });
    await toSimple(user);
    await typeBrief(user, "ab");

    await user.click(screen.getByRole("button", { name: "Run once" }));

    expect(
      screen.getByText("Add a brief of at least 3 characters before running."),
    ).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Brief description" })).toHaveFocus();
    expect(onRun).not.toHaveBeenCalled();
  });

  it("refuses to launch an empty roster even with a valid brief", async () => {
    const user = userEvent.setup();
    const onRun = vi.fn();
    renderComposer({ onRun });
    await toSimple(user);
    await typeBrief(user, "Build something");

    await user.click(screen.getByRole("button", { name: "Run once" }));

    expect(screen.getByText("Add at least one agent before running.")).toBeInTheDocument();
    expect(onRun).not.toHaveBeenCalled();
  });

  it("clears a previous run error once a valid launch is made", async () => {
    const user = userEvent.setup();
    const onRun = vi.fn();
    renderComposer({ onRun, initialAgentIds: ["alpha-agent"] });
    await toSimple(user);
    await user.click(screen.getByRole("button", { name: "Run once" }));
    expect(
      screen.getByText("Add a brief of at least 3 characters before running."),
    ).toBeInTheDocument();

    await typeBrief(user, "Build something");
    await user.click(screen.getByRole("button", { name: "Run once" }));

    expect(
      screen.queryByText("Add a brief of at least 3 characters before running."),
    ).not.toBeInTheDocument();
    expect(onRun).toHaveBeenCalledTimes(1);
  });
});

describe("ComposerPage — Run once launch payload", () => {
  it("launches a flat custom roster with the live Workflow-tab settings", async () => {
    const user = userEvent.setup();
    const onRun = vi.fn();
    renderComposer({
      onRun,
      initialAgentIds: ["alpha-agent", "beta-agent"],
      initialSelections: { "alpha-agent": { retry: 2 } },
    });
    await toSimple(user);
    await typeBrief(user, "Build something");

    await user.click(screen.getByRole("button", { name: "Run once" }));

    expect(onRun).toHaveBeenCalledTimes(1);
    const [type, brief, ids, extra] = onRun.mock.calls[0] as OnRunArgs;
    expect(type).toBe("custom");
    expect(brief).toBe("Build something");
    expect(ids).toEqual(["alpha-agent", "beta-agent"]);
    expect(extra).toEqual({
      selections: {
        "alpha-agent": { retry: 2 },
        __deliverable__: { strategy: "streamed_text", name: "output.md" },
      },
      deliverable: { strategy: "streamed_text", name: "output.md" },
      planner: "skip",
      clarify: { mode: "skip", defaults: [] },
      capabilities: {},
    });
  });

  it("trims whitespace around the brief that is passed to onRun", async () => {
    const user = userEvent.setup();
    const onRun = vi.fn();
    renderComposer({ onRun, initialAgentIds: ["alpha-agent"] });
    await toSimple(user);
    await typeBrief(user, "   Build something   ");

    await user.click(screen.getByRole("button", { name: "Run once" }));

    expect((onRun.mock.calls[0] as OnRunArgs)[1]).toBe("Build something");
  });

  it("launches from Ctrl+Enter in the brief box, and ignores a second shortcut once submitting", async () => {
    const user = userEvent.setup();
    const onRun = vi.fn();
    renderComposer({ onRun, initialAgentIds: ["alpha-agent"] });
    await toSimple(user);
    await typeBrief(user, "Build something");

    await user.keyboard("{Control>}{Enter}{/Control}");
    await user.keyboard("{Control>}{Enter}{/Control}");

    expect(onRun).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Run once" })).toBeDisabled();
  });

  it("does not launch from a plain Enter in the brief box", async () => {
    const user = userEvent.setup();
    const onRun = vi.fn();
    renderComposer({ onRun, initialAgentIds: ["alpha-agent"] });
    await toSimple(user);
    await typeBrief(user, "Build something{Enter}");

    expect(onRun).not.toHaveBeenCalled();
  });

  it("sends an unsaved composition with custom steps as an inline manifest", async () => {
    const user = userEvent.setup();
    const onRun = vi.fn();
    renderComposer({
      onRun,
      initialManifestSteps: [customStep("one"), customStep("two", { depends_on: ["custom-agent:one"] })],
    });
    await toSimple(user);
    await typeBrief(user, "Build something");

    await user.click(screen.getByRole("button", { name: "Run once" }));

    const [, , ids, extra] = onRun.mock.calls[0] as OnRunArgs;
    expect(ids).toEqual(["one", "two"]);
    const manifest = extra?.manifest as { steps: { instance_id?: string }[] };
    expect(manifest.steps.map((s) => s.instance_id)).toEqual(["one", "two"]);
    expect(extra).not.toHaveProperty("user_workflow_id");
  });

  it("sends the saved row id instead of an inline manifest when the workflow was already saved", async () => {
    const user = userEvent.setup();
    const onRun = vi.fn();
    renderComposer({
      onRun,
      initialUserWorkflowId: "wf-9",
      initialManifestSteps: [customStep("one")],
    });
    await toSimple(user);
    await typeBrief(user, "Build something");

    await user.click(screen.getByRole("button", { name: "Run once" }));

    const extra = (onRun.mock.calls[0] as OnRunArgs)[3];
    expect(extra?.user_workflow_id).toBe("wf-9");
    expect(extra).not.toHaveProperty("manifest");
  });

  it("folds per-agent skills into the run selections", async () => {
    const user = userEvent.setup();
    const onRun = vi.fn();
    renderComposer({
      onRun,
      initialManifestSteps: [customStep("one", { skills: ["research", "summarise"] })],
    });
    await toSimple(user);
    await typeBrief(user, "Build something");

    await user.click(screen.getByRole("button", { name: "Run once" }));

    const selections = (onRun.mock.calls[0] as OnRunArgs)[3]?.selections as Record<
      string,
      { skills?: string[] }
    >;
    expect(selections.one.skills).toEqual(["research", "summarise"]);
  });

  it("launches prototype-build on the task_loop strategy when the deliverable is prototype.html", async () => {
    const user = userEvent.setup();
    const onRun = vi.fn();
    renderComposer({
      onRun,
      initialAgentIds: ["prototype-build"],
      initialRunConfig: {
        deliverable: { strategy: "single_file", name: "prototype.html" },
        planner: "skip",
        clarify: { mode: "skip", defaults: [] },
      },
    });
    await toSimple(user);
    await typeBrief(user, "Build a prototype");

    await user.click(screen.getByRole("button", { name: "Run once" }));

    const selections = (onRun.mock.calls[0] as OnRunArgs)[3]?.selections as Record<
      string,
      { strategy?: string }
    >;
    expect(selections["prototype-build"].strategy).toBe("task_loop");
  });

  it("launches an unmodified built-in as itself with no agent ids or composed extras", async () => {
    const user = userEvent.setup();
    const onRun = vi.fn();
    renderComposer({
      onRun,
      builtinCanvasType: "ppt",
      initialManifestSteps: [{ agent: "ppt-brief-analyst" }, { agent: "ppt-composer" }] as ManifestStep[],
    });
    await toSimple(user);
    await typeBrief(user, "Build the deck");

    await user.click(screen.getByRole("button", { name: "Run once" }));

    expect(onRun).toHaveBeenCalledWith("ppt", "Build the deck", [], undefined);
  });
});

describe("ComposerPage — design context", () => {
  it("shows no design controls for a workflow that declares no context provider", async () => {
    const user = userEvent.setup();
    renderComposer({ initialAgentIds: ["alpha-agent"] });
    await toSimple(user);

    expect(screen.queryByRole("button", { name: /Attach design/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Choose a design" })).not.toBeInTheDocument();
  });

  it("flags a missing design system for web mode and opens the picker instead of launching", async () => {
    const user = userEvent.setup();
    const onRun = vi.fn();
    renderComposer({
      onRun,
      initialAgentIds: ["alpha-agent"],
      initialRunConfig: DESIGN_RUN_CONFIG,
    });
    await toSimple(user);
    await typeBrief(user, "Build something");
    expect(screen.getByRole("button", { name: "Design system required" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run once" })).toHaveAttribute(
      "title",
      "Pick a design system first",
    );

    await user.click(screen.getByRole("button", { name: "Run once" }));

    expect(screen.getByRole("dialog", { name: "Choose a design" })).toHaveAttribute(
      "data-mode",
      "web",
    );
    expect(onRun).not.toHaveBeenCalled();
  });

  it("flags a missing template for deck mode", async () => {
    const user = userEvent.setup();
    renderComposer({
      onRun: vi.fn(),
      initialAgentIds: ["alpha-agent"],
      initialRunConfig: { ...DESIGN_RUN_CONFIG, designMode: "deck" },
    });
    await toSimple(user);
    await typeBrief(user, "Build something");

    expect(screen.getByRole("button", { name: "Template required" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run once" })).toHaveAttribute(
      "title",
      "Pick a template first",
    );
  });

  it("opens the picker instead of launching on Ctrl+Enter when the design is missing", async () => {
    const user = userEvent.setup();
    const onRun = vi.fn();
    renderComposer({
      onRun,
      initialAgentIds: ["alpha-agent"],
      initialRunConfig: DESIGN_RUN_CONFIG,
    });
    await toSimple(user);
    await typeBrief(user, "Build something");

    await user.keyboard("{Control>}{Enter}{/Control}");

    expect(screen.getByRole("dialog", { name: "Choose a design" })).toBeInTheDocument();
    expect(onRun).not.toHaveBeenCalled();
  });

  it("opens the picker from '+ Attach design' and closes it again", async () => {
    const user = userEvent.setup();
    renderComposer({ initialAgentIds: ["alpha-agent"], initialRunConfig: DESIGN_RUN_CONFIG });
    await toSimple(user);

    await user.click(screen.getByRole("button", { name: /Attach design/ }));
    expect(screen.getByRole("dialog", { name: "Choose a design" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "close design picker" }));
    expect(screen.queryByRole("dialog", { name: "Choose a design" })).not.toBeInTheDocument();
  });

  it("lists the picked design as removable chips and launches with its ids and custom bodies", async () => {
    const user = userEvent.setup();
    const onRun = vi.fn();
    renderComposer({
      onRun,
      initialAgentIds: ["alpha-agent"],
      initialRunConfig: DESIGN_RUN_CONFIG,
    });
    await toSimple(user);
    await user.click(screen.getByRole("button", { name: /Attach design/ }));
    await user.click(screen.getByRole("button", { name: "pick template" }));
    await user.click(screen.getByRole("button", { name: "pick design system" }));
    await user.click(screen.getByRole("button", { name: "close design picker" }));

    expect(screen.getByText("Landing page")).toBeInTheDocument();
    expect(screen.getByText("Material")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Design system required" })).not.toBeInTheDocument();

    await typeBrief(user, "Build something");
    await user.click(screen.getByRole("button", { name: "Run once" }));

    const extra = (onRun.mock.calls[0] as OnRunArgs)[3];
    expect(extra).toMatchObject({
      template_id: "tpl-1",
      design_system_id: "ds-1",
      custom_template_body: "<html/>",
      custom_ds_body: "tokens",
    });
  });

  it("removes the template chip and the design-system chip independently", async () => {
    const user = userEvent.setup();
    renderComposer({
      onRun: vi.fn(),
      initialAgentIds: ["alpha-agent"],
      initialRunConfig: DESIGN_RUN_CONFIG,
    });
    await toSimple(user);
    await user.click(screen.getByRole("button", { name: /Attach design/ }));
    await user.click(screen.getByRole("button", { name: "pick template" }));
    await user.click(screen.getByRole("button", { name: "pick design system" }));
    await user.click(screen.getByRole("button", { name: "close design picker" }));

    await user.click(screen.getByRole("button", { name: "Remove template" }));
    expect(screen.queryByText("Landing page")).not.toBeInTheDocument();
    expect(screen.getByText("Material")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Remove design system" }));
    expect(screen.queryByText("Material")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Design system required" })).toBeInTheDocument();
  });

  it("passes the design ids through for an unmodified built-in", async () => {
    const user = userEvent.setup();
    const onRun = vi.fn();
    renderComposer({
      onRun,
      builtinCanvasType: "prototype",
      initialManifestSteps: [{ agent: "prototype-build" }] as ManifestStep[],
      initialRunConfig: DESIGN_RUN_CONFIG,
    });
    await toSimple(user);
    await user.click(screen.getByRole("button", { name: /Attach design/ }));
    await user.click(screen.getByRole("button", { name: "pick design system" }));
    await user.click(screen.getByRole("button", { name: "close design picker" }));
    await typeBrief(user, "Build a prototype");

    await user.click(screen.getByRole("button", { name: "Run once" }));

    expect(onRun).toHaveBeenCalledWith("prototype", "Build a prototype", [], {
      design_system_id: "ds-1",
      custom_ds_body: "tokens",
    });
  });
});

describe("ComposerPage — Save", () => {
  it("asks for a name and focuses the name field instead of saving an unnamed workflow", async () => {
    const user = userEvent.setup();
    renderComposer({ initialAgentIds: ["alpha-agent"] });

    await user.click(screen.getByRole("button", { name: /Save workflow/ }));

    expect(screen.getByText("Name the workflow first, then save.")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Workflow name" })).toHaveFocus();
    expect(mockSaveUserWorkflow).not.toHaveBeenCalled();
  });

  it("creates a workflow with the trimmed name and description and shows a transient 'Saved' state", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockSaveUserWorkflow.mockResolvedValue({ id: "wf-1" });
    renderComposer({
      initialAgentIds: ["alpha-agent", "beta-agent"],
      initialName: "  Flow  ",
      initialDescription: " Does things ",
    });

    await user.click(screen.getByRole("button", { name: /Save workflow/ }));

    expect(await screen.findByRole("button", { name: /Saved/ })).toBeInTheDocument();
    expect(mockSaveUserWorkflow).toHaveBeenCalledWith("test-token", undefined, {
      name: "Flow",
      description: "Does things",
      base_pipeline_type: "custom",
      agent_ids: ["alpha-agent", "beta-agent"],
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1800);
    });
    expect(screen.getByRole("button", { name: /Save workflow/ })).toBeInTheDocument();
  });

  it("omits an empty description on create", async () => {
    const user = userEvent.setup();
    mockSaveUserWorkflow.mockResolvedValue({ id: "wf-1" });
    renderComposer({ initialAgentIds: ["alpha-agent"], initialName: "Flow" });

    await user.click(screen.getByRole("button", { name: /Save workflow/ }));
    await waitFor(() => expect(mockSaveUserWorkflow).toHaveBeenCalled());

    const payload = mockSaveUserWorkflow.mock.calls[0][2] as Record<string, unknown>;
    expect(payload).not.toHaveProperty("description");
  });

  it("updates the same row on a second save and always sends the description so it can be cleared", async () => {
    const user = userEvent.setup();
    mockSaveUserWorkflow.mockResolvedValue({ id: "wf-1" });
    renderComposer({ initialAgentIds: ["alpha-agent"], initialName: "Flow" });

    await user.click(screen.getByRole("button", { name: /Save workflow/ }));
    await waitFor(() => expect(mockSaveUserWorkflow).toHaveBeenCalledTimes(1));
    await user.click(await screen.findByRole("button", { name: /Saved|Save workflow/ }));
    await waitFor(() => expect(mockSaveUserWorkflow).toHaveBeenCalledTimes(2));

    const [, secondId, secondPayload] = mockSaveUserWorkflow.mock.calls[1] as [
      string,
      string | undefined,
      Record<string, unknown>,
    ];
    expect(secondId).toBe("wf-1");
    expect(secondPayload.description).toBe("");
  });

  it("PATCHes the existing row when editing a saved workflow", async () => {
    const user = userEvent.setup();
    mockSaveUserWorkflow.mockResolvedValue({ id: "wf-7" });
    renderComposer({
      initialAgentIds: ["alpha-agent"],
      initialName: "Flow",
      initialUserWorkflowId: "wf-7",
    });

    await user.click(screen.getByRole("button", { name: /Save workflow/ }));
    await waitFor(() => expect(mockSaveUserWorkflow).toHaveBeenCalled());

    expect(mockSaveUserWorkflow.mock.calls[0][1]).toBe("wf-7");
  });

  it("disables the button and shows 'Saving…' while the request is in flight", async () => {
    const user = userEvent.setup();
    let resolveSave: (v: { id: string }) => void = () => {};
    mockSaveUserWorkflow.mockImplementation(
      () => new Promise((resolve) => { resolveSave = resolve; }),
    );
    renderComposer({ initialAgentIds: ["alpha-agent"], initialName: "Flow" });

    await user.click(screen.getByRole("button", { name: /Save workflow/ }));

    const saving = await screen.findByRole("button", { name: /Saving/ });
    expect(saving).toBeDisabled();
    await act(async () => resolveSave({ id: "wf-1" }));
    expect(await screen.findByRole("button", { name: /Saved/ })).toBeEnabled();
    expect(mockSaveUserWorkflow).toHaveBeenCalledTimes(1);
  });

  it("reports 'Not authenticated.' without calling the API, then saves once a token exists", async () => {
    const user = userEvent.setup();
    mockSaveUserWorkflow.mockResolvedValue({ id: "wf-1" });
    renderComposer({ initialAgentIds: ["alpha-agent"], initialName: "Flow" });
    mockGetToken.mockReturnValue(null);

    await user.click(screen.getByRole("button", { name: /Save workflow/ }));
    expect(screen.getByText("Not authenticated.")).toBeInTheDocument();
    expect(mockSaveUserWorkflow).not.toHaveBeenCalled();

    mockGetToken.mockReturnValue("test-token");
    await user.click(screen.getByRole("button", { name: /Save workflow/ }));

    await waitFor(() => expect(mockSaveUserWorkflow).toHaveBeenCalledTimes(1));
    expect(screen.queryByText("Not authenticated.")).not.toBeInTheDocument();
  });

  it("shows the server's message when the save is rejected", async () => {
    const user = userEvent.setup();
    mockSaveUserWorkflow.mockRejectedValue(new Error("Workflow name already exists"));
    renderComposer({ initialAgentIds: ["alpha-agent"], initialName: "Flow" });

    await user.click(screen.getByRole("button", { name: /Save workflow/ }));

    expect(await screen.findByText("Workflow name already exists")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Save workflow/ })).toBeEnabled();
  });

  it("falls back to a generic message when the rejection carries no message", async () => {
    const user = userEvent.setup();
    mockSaveUserWorkflow.mockRejectedValue(undefined);
    renderComposer({ initialAgentIds: ["alpha-agent"], initialName: "Flow" });

    await user.click(screen.getByRole("button", { name: /Save workflow/ }));

    expect(await screen.findByText("Failed to save workflow.")).toBeInTheDocument();
  });

  it("sends the selections map when only per-agent levers changed", async () => {
    const user = userEvent.setup();
    mockSaveUserWorkflow.mockResolvedValue({ id: "wf-1" });
    renderComposer({
      initialAgentIds: ["alpha-agent"],
      initialName: "Flow",
      initialSelections: { "alpha-agent": { retry: 2 } },
    });

    await user.click(screen.getByRole("button", { name: /Save workflow/ }));
    await waitFor(() => expect(mockSaveUserWorkflow).toHaveBeenCalled());

    const payload = mockSaveUserWorkflow.mock.calls[0][2] as Record<string, unknown>;
    expect(payload.selections).toEqual({ "alpha-agent": { retry: 2 } });
    expect(payload).not.toHaveProperty("manifest");
  });

  it("sends attached run-level hooks with a derived description fallback", async () => {
    const user = userEvent.setup();
    mockSaveUserWorkflow.mockResolvedValue({ id: "wf-1" });
    function AttachHook() {
      const { attachHook } = useSkillsHooks();
      useEffect(() => {
        attachHook({ id: "h1", name: "Lint", event: "post_step", trigger: "on done" });
        attachHook({ id: "h2", name: "Audit", event: "pre_step", trigger: "always", description: "Audits" });
      }, [attachHook]);
      return null;
    }
    renderComposer({ initialAgentIds: ["alpha-agent"], initialName: "Flow" }, LIBRARY, <AttachHook />);

    await user.click(screen.getByRole("button", { name: /Save workflow/ }));
    await waitFor(() => expect(mockSaveUserWorkflow).toHaveBeenCalled());

    const payload = mockSaveUserWorkflow.mock.calls[0][2] as {
      attached_hooks: { id: string; description: string }[];
    };
    expect(payload.attached_hooks).toEqual([
      { id: "h1", name: "Lint", event: "post_step", trigger: "on done", description: "Lint: on done" },
      { id: "h2", name: "Audit", event: "pre_step", trigger: "always", description: "Audits" },
    ]);
  });

  it("keeps the on-screen order when the server returns ids that do not match the roster", async () => {
    const user = userEvent.setup();
    mockSaveUserWorkflow.mockResolvedValue({ id: "wf-1", agent_ids: ["alpha-agent", "unknown"] });
    renderComposer({ initialAgentIds: ["beta-agent", "alpha-agent"], initialName: "Flow" });
    await toSimple(user);

    await user.click(screen.getByRole("button", { name: /Save workflow/ }));
    await waitFor(() => expect(mockSaveUserWorkflow).toHaveBeenCalled());

    const rows = screen.getAllByTestId(/^agent-row-/).map((r) => r.getAttribute("data-testid"));
    expect(rows).toEqual(["agent-row-beta-agent", "agent-row-alpha-agent"]);
  });

  it("blocks saving a detached step and names it", async () => {
    const user = userEvent.setup();
    renderComposer({
      initialName: "Flow",
      initialSelections: { a: { gates: ["conditional"] } },
      initialManifestSteps: [
        customStep("a", { route: { outcomes: { go: { trigger: "step", target: "c" } } } }),
        customStep("b"),
        customStep("c"),
      ],
    });

    await user.click(screen.getByRole("button", { name: /Save workflow/ }));

    expect(await screen.findByText(/“B” isn.t connected to anything/)).toBeInTheDocument();
    expect(mockSaveUserWorkflow).not.toHaveBeenCalled();
  });

  it("lists every detached step when more than one is unreachable", async () => {
    const user = userEvent.setup();
    renderComposer({
      initialName: "Flow",
      // Two branching gates (a → c, c → e) each orphan the step that follows
      // them in the chain: b and d.
      initialSelections: { a: { gates: ["conditional"] }, c: { gates: ["conditional"] } },
      initialManifestSteps: [
        customStep("a", { route: { outcomes: { go: { trigger: "step", target: "c" } } } }),
        customStep("b"),
        customStep("c", { route: { outcomes: { go: { trigger: "step", target: "e" } } } }),
        customStep("d"),
        customStep("e"),
      ],
    });

    await user.click(screen.getByRole("button", { name: /Save workflow/ }));

    expect(
      await screen.findByText(/2 steps aren.t connected to anything \(B, D\)/),
    ).toBeInTheDocument();
    expect(mockSaveUserWorkflow).not.toHaveBeenCalled();
  });
});

describe("ComposerPage — unsaved-work reporting", () => {
  it("reports clean on mount, dirty after an edit, and clean again on unmount", async () => {
    const user = userEvent.setup();
    const onUnsavedChange = vi.fn();
    const { unmount } = renderComposer({
      initialAgentIds: ["alpha-agent"],
      initialName: "Flow",
      onUnsavedChange,
    });
    expect(onUnsavedChange).toHaveBeenLastCalledWith(false);

    await user.type(screen.getByRole("textbox", { name: "Workflow name" }), "!");
    expect(onUnsavedChange).toHaveBeenLastCalledWith(true);

    unmount();
    expect(onUnsavedChange).toHaveBeenLastCalledWith(false);
  });
});

describe("ComposerPage — Simple view roster editing", () => {
  it("adds a library agent through 'Add agent' and closes the library", async () => {
    const user = userEvent.setup();
    renderComposer({ initialAgentIds: ["alpha-agent"] });
    await toSimple(user);

    await user.click(screen.getByRole("button", { name: /Add agent/ }));
    const card = await screen.findByTestId("library-card-gamma-agent");
    await user.click(within(card).getByRole("button", { name: "+ Add" }));

    expect(screen.getByTestId("agent-row-gamma-agent")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByTestId("library-card-gamma-agent")).not.toBeInTheDocument(),
    );
  });

  it("hides agents that are already on the roster from the library", async () => {
    const user = userEvent.setup();
    renderComposer({ initialAgentIds: ["alpha-agent"] });
    await toSimple(user);

    await user.click(screen.getByRole("button", { name: /Add agent/ }));

    expect(await screen.findByTestId("library-card-beta-agent")).toBeInTheDocument();
    expect(screen.queryByTestId("library-card-alpha-agent")).not.toBeInTheDocument();
  });

  it("disables 'Add agent' and shows a cap tooltip once the optional-agent limit is reached", async () => {
    const user = userEvent.setup();
    const bulk = Array.from({ length: 16 }, (_, i) => agentDef(`bulk-${i}`, `Bulk ${i} Agent`));
    renderComposer({ initialAgentIds: bulk.map((a) => a.id) }, [...LIBRARY, ...bulk]);
    await toSimple(user);

    expect(screen.getByRole("button", { name: /Add agent/ })).toBeDisabled();
    expect(screen.getByRole("tooltip")).toHaveTextContent(/Maximum \d+ root agents are allowed/);
  });

  it("shows an empty-state message when the roster has no agents", async () => {
    const user = userEvent.setup();
    renderComposer();
    await toSimple(user);

    expect(
      screen.getByText("No agents yet — add one from the catalogue to start composing."),
    ).toBeInTheDocument();
  });

  it("moves an agent up", async () => {
    const user = userEvent.setup();
    renderComposer({ initialAgentIds: ["alpha-agent", "beta-agent", "gamma-agent"] });
    await toSimple(user);

    await user.click(screen.getByRole("button", { name: "Move Gamma Agent up" }));

    expect(
      screen.getAllByTestId(/^agent-row-/).map((r) => r.getAttribute("data-testid")),
    ).toEqual(["agent-row-alpha-agent", "agent-row-gamma-agent", "agent-row-beta-agent"]);
  });

  it("disables moving the first agent up and the last agent down", async () => {
    const user = userEvent.setup();
    renderComposer({ initialAgentIds: ["alpha-agent", "beta-agent"] });
    await toSimple(user);

    expect(screen.getByRole("button", { name: "Move Alpha Agent up" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Move Beta Agent down" })).toBeDisabled();
  });

  it("removes an optional agent, and its gate no longer counts in the header", async () => {
    const user = userEvent.setup();
    renderComposer({
      initialAgentIds: ["alpha-agent", "beta-agent"],
      initialSelections: { "alpha-agent": { gates: ["human"] } },
    });
    await toSimple(user);
    expect(screen.getByTestId("composer-header-summary")).toHaveTextContent("1 review gate");

    await user.click(screen.getByRole("button", { name: "Remove Alpha Agent" }));

    expect(screen.queryByTestId("agent-row-alpha-agent")).not.toBeInTheDocument();
    expect(screen.getByTestId("composer-header-summary")).toHaveTextContent("0 review gates");
    expect(screen.getByTestId("composer-header-summary")).toHaveTextContent("1 agents");
  });

  it("removes a skill chip from an agent row", async () => {
    const user = userEvent.setup();
    renderComposer({
      initialManifestSteps: [customStep("one", { skills: ["research", "summarise"] })],
    });
    await toSimple(user);

    await user.click(screen.getByRole("button", { name: "Remove research" }));

    expect(screen.queryByRole("button", { name: "Remove research" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove summarise" })).toBeInTheDocument();
  });

  it("renders a read-only list for sub-agents nested under a step", async () => {
    const user = userEvent.setup();
    renderComposer({
      initialManifestSteps: [
        customStep("parent", {
          subagents: { mode: "sequential", steps: [customStep("kid", { name: "Kid Helper" })] },
        } as Partial<ManifestStep>),
      ],
    });
    await toSimple(user);

    expect(screen.getByText("Kid Helper")).toBeInTheDocument();
  });
});

describe("ComposerPage — drag reorder", () => {
  const rowIds = () =>
    screen.getAllByTestId(/^agent-row-/).map((r) => r.getAttribute("data-testid"));

  it("moves a dragged agent to the drop position", async () => {
    const user = userEvent.setup();
    renderComposer({ initialAgentIds: ["alpha-agent", "beta-agent", "gamma-agent"] });
    await toSimple(user);

    fireEvent.dragStart(screen.getByTestId("agent-row-alpha-agent"));
    fireEvent.dragOver(screen.getByTestId("agent-row-gamma-agent"));
    fireEvent.drop(screen.getByTestId("agent-row-gamma-agent"));
    fireEvent.dragEnd(screen.getByTestId("agent-row-alpha-agent"));

    expect(rowIds()).toEqual(["agent-row-beta-agent", "agent-row-gamma-agent", "agent-row-alpha-agent"]);
  });

  it("leaves the order alone when an agent is dropped on itself", async () => {
    const user = userEvent.setup();
    renderComposer({ initialAgentIds: ["alpha-agent", "beta-agent"] });
    await toSimple(user);

    fireEvent.dragStart(screen.getByTestId("agent-row-alpha-agent"));
    fireEvent.drop(screen.getByTestId("agent-row-alpha-agent"));

    expect(rowIds()).toEqual(["agent-row-alpha-agent", "agent-row-beta-agent"]);
  });

  it("does not start dragging a locked core agent", async () => {
    const user = userEvent.setup();
    renderComposer(
      {
        workflowType: "user_stories",
        initialAgentIds: ["domain-analyst", "epic-architect", "story-estimator"],
      },
    );
    await toSimple(user);
    expect(screen.getByTestId("agent-row-domain-analyst")).toHaveAttribute("draggable", "false");

    fireEvent.dragStart(screen.getByTestId("agent-row-domain-analyst"));
    fireEvent.drop(screen.getByTestId("agent-row-story-estimator"));

    expect(rowIds()).toEqual([
      "agent-row-domain-analyst",
      "agent-row-epic-architect",
      "agent-row-story-estimator",
    ]);
  });

  it("forgets the drag when it ends without a drop", async () => {
    const user = userEvent.setup();
    renderComposer({ initialAgentIds: ["alpha-agent", "beta-agent"] });
    await toSimple(user);

    fireEvent.dragStart(screen.getByTestId("agent-row-alpha-agent"));
    fireEvent.dragEnd(screen.getByTestId("agent-row-alpha-agent"));
    fireEvent.drop(screen.getByTestId("agent-row-beta-agent"));

    expect(rowIds()).toEqual(["agent-row-alpha-agent", "agent-row-beta-agent"]);
  });
});

describe("ComposerPage — brief-driven suggestions", () => {
  it("suggests agents for a backlog brief and adds one when clicked", async () => {
    const user = userEvent.setup();
    renderComposer();
    await toSimple(user);
    expect(screen.queryByText("Suggested agents for your brief")).not.toBeInTheDocument();

    await typeBrief(user, "Write a backlog of user stories");

    expect(await screen.findByText("Suggested agents for your brief")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Story Estimator" }));
    expect(screen.getByTestId("agent-row-story-estimator")).toBeInTheDocument();
  });

  it("hides the suggestions after Dismiss", async () => {
    const user = userEvent.setup();
    renderComposer();
    await toSimple(user);
    await typeBrief(user, "Write a backlog of user stories");

    await user.click(await screen.findByRole("button", { name: "Dismiss" }));

    expect(screen.queryByText("Suggested agents for your brief")).not.toBeInTheDocument();
  });

  it("does not suggest anything for a brief shorter than ten characters", async () => {
    const user = userEvent.setup();
    renderComposer();
    await toSimple(user);

    await typeBrief(user, "backlog");

    expect(screen.queryByText("Suggested agents for your brief")).not.toBeInTheDocument();
  });

  it("offers to complete a partially-added companion pipeline and adds the missing agents", async () => {
    const user = userEvent.setup();
    renderComposer({ initialAgentIds: ["domain-analyst"] });
    await toSimple(user);

    expect(screen.getByText("Complete User Stories Pipeline")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Add 5 missing" }));

    expect(
      screen.getAllByTestId(/^agent-row-/).map((r) => r.getAttribute("data-testid")),
    ).toEqual([
      "agent-row-domain-analyst",
      "agent-row-epic-architect",
      "agent-row-story-estimator",
      "agent-row-nfr-specialist",
      "agent-row-backlog-reviewer",
      "agent-row-backlog-compiler",
    ]);
    expect(screen.queryByText("Complete User Stories Pipeline")).not.toBeInTheDocument();
  });
});

describe("ComposerPage — declared capabilities (workflowId)", () => {
  it("surfaces the capabilities declared by the opened workflow on the canvas", async () => {
    mockGetWorkflowDetail.mockResolvedValue({
      steps: [
        {
          name: "Plan",
          agent_id: "planner",
          strategy: "task_loop",
          gates: ["human"],
          validators: ["code_test"],
          compaction: "summary",
          task_source: { kind: "static" },
          skills: ["research"],
        },
        { name: "", agent_id: "empty", gates: [], validators: [] },
      ],
    });

    renderComposer({ workflowId: "wf-x" });

    const chips = await screen.findByTestId("canvas-declared-capabilities");
    for (const text of [
      "strategy:task_loop",
      "gate:human",
      "validator:code_test",
      "compaction:summary",
      "task_source:static",
      "skill:research",
    ]) {
      expect(within(chips).getByText(text)).toBeInTheDocument();
    }
    expect(mockGetWorkflowDetail).toHaveBeenCalledWith("test-token", "wf-x");
  });

  it("shows no declared-capability section when no step declares anything", async () => {
    mockGetWorkflowDetail.mockResolvedValue({
      steps: [{ name: "Plan", agent_id: "planner", gates: [], validators: [] }],
    });

    renderComposer({ workflowId: "wf-x" });

    await waitFor(() => expect(mockGetWorkflowDetail).toHaveBeenCalled());
    expect(screen.queryByTestId("canvas-declared-capabilities")).not.toBeInTheDocument();
  });

  it("shows no declared-capability section when the detail request fails", async () => {
    mockGetWorkflowDetail.mockRejectedValue(new Error("boom"));

    renderComposer({ workflowId: "wf-x" });

    await waitFor(() => expect(mockGetWorkflowDetail).toHaveBeenCalled());
    expect(screen.queryByTestId("canvas-declared-capabilities")).not.toBeInTheDocument();
  });

  it("does not fetch the workflow detail without a token", () => {
    mockGetToken.mockReturnValue(null);

    renderComposer({ workflowId: "wf-x" });

    expect(mockGetWorkflowDetail).not.toHaveBeenCalled();
  });

  it("does not fetch the workflow detail for a from-scratch composition", () => {
    renderComposer();

    expect(mockGetWorkflowDetail).not.toHaveBeenCalled();
  });

  it("includes validators and gates chosen on a step among the declared capabilities", async () => {
    renderComposer({
      initialAgentIds: ["alpha-agent"],
      initialSelections: { "alpha-agent": { validators: ["code_test"], gates: ["human"] } },
    });

    const chips = await screen.findByTestId("canvas-declared-capabilities");
    expect(within(chips).getByText("code_test")).toBeInTheDocument();
    expect(within(chips).getByText("human")).toBeInTheDocument();
  });
});
