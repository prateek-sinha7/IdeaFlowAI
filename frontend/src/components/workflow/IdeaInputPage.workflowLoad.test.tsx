/**
 * IdeaInputPage — opening a launchable/saved workflow by `workflowId`:
 * GET /api/workflows/{id} projection into the roster, declared capabilities and
 * route/gate seeds; the ISS-374/375 load-error copy; the spec-016 per-user
 * override lifecycle (toggle, save-as-my-version); and the "Open in full canvas"
 * hand-off payload.
 *
 * Boundaries: `@/lib/api` (transport). AgentsPopup and ReviewGatesSection are
 * doubles that render the props the PAGE computes and give the page's callbacks
 * back to the test. `isNotFoundError` is a stand-in for the real helper because
 * the real `ApiError` class is not exported and cannot be constructed here.
 */
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { IdeaInputPage } from "./IdeaInputPage";
import renderWithProviders from "@/test/renderWithProviders";
import type { WorkflowDetail, WorkflowStepDetail } from "@/lib/api";
import type { AgentDef, ManifestStep, WorkflowType } from "@/types/index";

const api = vi.hoisted(() => ({
  getToken: vi.fn<() => string | null>(),
  getWorkflowDetail: vi.fn(),
  createUserWorkflow: vi.fn(),
  setWorkflowOverrideEnabled: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  getToken: () => api.getToken(),
  getWorkflowDetail: (token: string, id: string) => api.getWorkflowDetail(token, id),
  createUserWorkflow: (token: string, body: unknown) => api.createUserWorkflow(token, body),
  setWorkflowOverrideEnabled: (token: string, id: string, enabled: boolean) =>
    api.setWorkflowOverrideEnabled(token, id, enabled),
  isNotFoundError: (e: unknown) => (e as { status?: number } | null)?.status === 404,
  extractFileText: vi.fn(),
  stageRunFile: vi.fn(),
}));

interface PopupHandle {
  agents: AgentDef[];
  overrideAvailable?: boolean;
  overrideActive?: boolean;
  onToggleOverride?: (next: boolean) => void;
  onOpenInCanvas?: () => void;
  isOpen: boolean;
  declaredCapabilities?: { step: string; capabilities: string[] }[];
  selections?: unknown;
  initialSelections?: unknown;
  manifestSteps?: ManifestStep[];
}

vi.mock("./AgentsPopup", () => ({
  AgentsPopup: (props: PopupHandle) => (
    <div>
      <ul aria-label="Popup roster">
        {props.agents.map((a) => (
          <li key={a.id}>{a.id}</li>
        ))}
      </ul>
      <output aria-label="Popup agents">{JSON.stringify(props.agents)}</output>
      <output aria-label="Declared capabilities">{JSON.stringify(props.declaredCapabilities ?? null)}</output>
      <output aria-label="Live selections">{JSON.stringify(props.selections ?? null)}</output>
      <output aria-label="Seed selections">{JSON.stringify(props.initialSelections ?? null)}</output>
      <output aria-label="Manifest step count">{String(props.manifestSteps?.length ?? "none")}</output>
      <output aria-label="Override state">{`${props.overrideAvailable}/${props.overrideActive}`}</output>
      <output aria-label="Popup open">{String(props.isOpen)}</output>
      {props.onToggleOverride && (
        <>
          <button type="button" onClick={() => props.onToggleOverride?.(true)}>override on</button>
          <button type="button" onClick={() => props.onToggleOverride?.(false)}>override off</button>
        </>
      )}
      {props.onOpenInCanvas && (
        <button type="button" onClick={props.onOpenInCanvas}>open in canvas</button>
      )}
    </div>
  ),
}));

interface GatesHandle {
  onChange: (ids: string[], touched: boolean) => void;
}

vi.mock("./ReviewGatesSection", () => ({
  ReviewGatesSection: (props: GatesHandle) => (
    <div>
      <button type="button" onClick={() => props.onChange(["gate-a"], true)}>check gate</button>
      <button type="button" onClick={() => props.onChange([], false)}>untouch gates</button>
    </div>
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

const WF = "ex_A1_loop";
const WF_TYPE = WF as WorkflowType;

function step(agentId: string, over: Partial<WorkflowStepDetail> = {}): WorkflowStepDetail {
  return {
    agent_id: agentId,
    name: "",
    role: "",
    order: 1,
    strategy: "",
    gates: [],
    validators: [],
    ...over,
  };
}

function detail(over: Partial<WorkflowDetail> = {}): WorkflowDetail {
  return {
    id: WF,
    name: "Loop",
    description: "",
    planner: "run",
    clarify_mode: "auto",
    clarify_defaults: [],
    context_providers: [],
    deliverable: {},
    steps: [],
    ...over,
  };
}

const MANIFEST_STEPS: ManifestStep[] = [
  {
    agent: "custom-agent",
    instance_id: "ask",
    name: "Ask",
    gates: ["conditional"],
    route: {
      condition_agent: "ask",
      outcomes: {
        yes: { trigger: "step", target: "done" },
        elsewhere: { trigger: "workflow", target: "other_wf" },
      },
      default_next: "done",
    },
  },
  { agent: "custom-agent", instance_id: "done", name: "Done" },
  { agent: "summary-agent", name: "Summary", skills: ["skill-1"] },
];

const OVERRIDE_STEPS: ManifestStep[] = [
  { agent: "custom-agent", instance_id: "mine-a", name: "Mine A", gates: ["human"] },
  { agent: "custom-agent", instance_id: "mine-b", name: "Mine B" },
];

function manifestDetail(over: Partial<WorkflowDetail> = {}): WorkflowDetail {
  return detail({
    steps: [step("custom-agent:ask", { name: "Ask", role: "Decides", order: 5, declared_gate: "Human_Gate" })],
    manifest_steps: MANIFEST_STEPS,
    ...over,
  });
}

function overrideDetail(over: Partial<WorkflowDetail> = {}): WorkflowDetail {
  return detail({
    manifest_steps: OVERRIDE_STEPS,
    has_override: true,
    override_id: "ov-1",
    is_overridden: true,
    ...over,
  });
}

type PageProps = React.ComponentProps<typeof IdeaInputPage>;

function pageElement(onRun: PageProps["onRun"], extra: Partial<PageProps>) {
  return (
    <IdeaInputPage workflowType={WF_TYPE} workflowId={WF} onBack={vi.fn()} onRun={onRun} {...extra} />
  );
}

function renderPage(extra: Partial<PageProps> = {}, agents: AgentDef[] = []) {
  const onRun = vi.fn();
  const result = renderWithProviders(pageElement(onRun, extra), {
    preloadedState: {
      agents: { agents, totalCount: agents.length, pipelines: {}, status: "succeeded", error: null },
    },
  });
  return {
    onRun,
    unmount: result.unmount,
    rerenderPage: (next: Partial<PageProps>) => result.rerender(pageElement(onRun, next)),
  };
}

const rosterIds = () =>
  within(screen.getByRole("list", { name: "Popup roster" }))
    .queryAllByRole("listitem")
    .map((li) => li.textContent);
const readJson = (name: string) => JSON.parse(screen.getByRole("status", { name }).textContent ?? "null");
const brief = () => screen.getByRole("textbox", { name: "Brief description" });
const overrideState = () => screen.getByRole("status", { name: "Override state" });

/** Resolves once the first fetch has produced a roster. */
const waitForRoster = (ids: string[]) => waitFor(() => expect(rosterIds()).toEqual(ids));

beforeEach(() => {
  vi.spyOn(console, "log").mockImplementation(() => undefined);
  api.getToken.mockReturnValue("test-token");
  api.getWorkflowDetail.mockResolvedValue(manifestDetail());
  api.createUserWorkflow.mockResolvedValue({ id: "saved-1" });
  api.setWorkflowOverrideEnabled.mockResolvedValue({ id: "ov-1" });
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.clearAllMocks();
});

describe("IdeaInputPage workflow fetch", () => {
  it("builds the roster from the raw manifest steps, normalising route targets to node ids", async () => {
    renderPage();

    await waitForRoster(["custom-agent:ask", "custom-agent:done", "summary-agent"]);
    const [ask, done, summary] = readJson("Popup agents");
    expect(api.getWorkflowDetail).toHaveBeenCalledWith("test-token", WF);
    expect(ask).toMatchObject({
      id: "custom-agent:ask",
      name: "Ask",
      role: "Decides",
      order: 5,
      gate: "Human_Gate",
      isCustom: true,
      instance_id: "ask",
      pipeline_type: WF,
    });
    expect(ask.route).toEqual({
      condition_agent: "custom-agent:ask",
      outcomes: {
        yes: { trigger: "step", target: "custom-agent:done" },
        elsewhere: { trigger: "workflow", target: "other_wf" },
      },
      default_next: "custom-agent:done",
    });
    expect(done).toMatchObject({ id: "custom-agent:done", role: "Workflow step", order: 2, gate: null });
    expect(summary).toMatchObject({ id: "summary-agent", name: "Summary", has_skill: true, isCustom: false });
  });

  it("seeds the live and initial selections with the gates the manifest declares", async () => {
    renderPage();

    await waitForRoster(["custom-agent:ask", "custom-agent:done", "summary-agent"]);
    const declared = { "custom-agent:ask": { gates: ["conditional"] } };
    await waitFor(() => expect(readJson("Live selections")).toEqual(declared));
    expect(readJson("Seed selections")).toEqual(declared);
    expect(screen.getByRole("status", { name: "Manifest step count" })).toHaveTextContent("3");
  });

  it("lets a saved lever for the same step win over the manifest-declared gates", async () => {
    renderPage({ initialSelections: { "custom-agent:ask": { gates: ["human"] } } });

    await waitForRoster(["custom-agent:ask", "custom-agent:done", "summary-agent"]);

    expect(readJson("Seed selections")).toEqual({ "custom-agent:ask": { gates: ["human"] } });
  });

  it("omits agent ids from the launch payload while the roster is the manifest's own, unchanged", async () => {
    const user = userEvent.setup();
    const { onRun } = renderPage();
    await waitForRoster(["custom-agent:ask", "custom-agent:done", "summary-agent"]);
    await user.type(brief(), "Run the loop");

    await user.click(screen.getByRole("button", { name: "Run workflow" }));

    expect(onRun).toHaveBeenCalledWith("Run the loop", [], WF, { gate_agent_ids: [] });
  });

  it("falls back to the compiled steps when the API supplies no manifest steps", async () => {
    api.getWorkflowDetail.mockResolvedValue(
      detail({
        manifest_steps: null,
        steps: [
          step("compiled-a", { name: "Compiled A", role: "Does A", order: 3, skills: ["s1"], declared_gate: "Human_Gate" }),
          step("compiled-b"),
        ],
      }),
    );
    renderPage();

    await waitForRoster(["compiled-a", "compiled-b"]);
    const [a, b] = readJson("Popup agents");
    expect(a).toMatchObject({ name: "Compiled A", role: "Does A", order: 3, has_skill: true, gate: "Human_Gate", pipeline_type: WF });
    expect(b).toMatchObject({ name: "compiled-b", role: "Workflow step", has_skill: false, gate: null });
    expect(screen.getByRole("status", { name: "Manifest step count" })).toHaveTextContent("none");
  });

  it("maps every declared capability kind per step and leaves capability-free steps out", async () => {
    api.getWorkflowDetail.mockResolvedValue(
      detail({
        manifest_steps: null,
        steps: [
          step("s1-agent", {
            name: "S1",
            strategy: "per_task",
            gates: ["human"],
            validators: ["v1", "v2"],
            compaction: "summarize",
            task_source: { kind: "tasks_md" },
          }),
          step("quiet-agent", { name: "Quiet" }),
          step("s3-agent", { name: "", strategy: "single_shot" }),
        ],
      }),
    );
    renderPage();

    await waitFor(() =>
      expect(readJson("Declared capabilities")).toEqual([
        {
          step: "S1",
          capabilities: [
            "strategy:per_task",
            "gate:human",
            "validator:v1",
            "validator:v2",
            "compaction:summarize",
            "task_source:tasks_md",
          ],
        },
        { step: "s3-agent", capabilities: ["strategy:single_shot"] },
      ]),
    );
  });

  it("reports no declared capabilities when no step declares any", async () => {
    api.getWorkflowDetail.mockResolvedValue(detail({ manifest_steps: null, steps: [step("quiet-agent")] }));
    renderPage();

    await waitForRoster(["quiet-agent"]);

    expect(readJson("Declared capabilities")).toBeNull();
  });

  it("does not fetch, and shows no error, when there is no workflow id", () => {
    renderPage({ workflowId: undefined });

    expect(api.getWorkflowDetail).not.toHaveBeenCalled();
    expect(screen.queryByText(/not found|failed to load/i)).not.toBeInTheDocument();
  });

  it("does not fetch, and shows no error, when the user has no token", () => {
    api.getToken.mockReturnValue(null);

    renderPage();

    expect(api.getWorkflowDetail).not.toHaveBeenCalled();
    expect(screen.queryByText(/not found|failed to load/i)).not.toBeInTheDocument();
  });

  it("clears the projected roster and capabilities when the workflow id is removed", async () => {
    const { rerenderPage } = renderPage();
    await waitForRoster(["custom-agent:ask", "custom-agent:done", "summary-agent"]);

    rerenderPage({ workflowId: undefined });

    await waitForRoster([]);
    expect(readJson("Declared capabilities")).toBeNull();
    expect(screen.getByRole("status", { name: "Manifest step count" })).toHaveTextContent("none");
  });

  it("ignores a response that arrives after the page unmounted", async () => {
    let resolveDetail!: (d: WorkflowDetail) => void;
    api.getWorkflowDetail.mockReturnValue(new Promise<WorkflowDetail>((r) => (resolveDetail = r)));
    const { unmount } = renderPage();
    unmount();

    await act(async () => resolveDetail(manifestDetail()));

    expect(console.log).not.toHaveBeenCalledWith("[wf] 1. fetched", WF, expect.anything());
  });
});

describe("IdeaInputPage workflow load errors", () => {
  it("tells the user the workflow was not found when the fetch returns 404 and nothing can run", async () => {
    api.getWorkflowDetail.mockRejectedValue({ status: 404 });
    renderPage();

    expect(
      await screen.findByText(`Workflow "${WF}" not found — go back and pick one from the dashboard.`),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add agents first" })).toBeDisabled();
  });

  it("tells the user to reload when the fetch fails for any other reason", async () => {
    api.getWorkflowDetail.mockRejectedValue(new Error("network down"));
    renderPage();

    expect(await screen.findByText("Failed to load this workflow. Reload the page to retry.")).toBeInTheDocument();
  });

  it("stays quiet about a failed fetch when the roster still has agents to run", async () => {
    api.getWorkflowDetail.mockRejectedValue({ status: 404 });
    renderPage({ initialAgentIds: ["seed-agent"] }, [
      {
        id: "seed-agent",
        name: "Seed",
        role: "r",
        description: "d",
        pipeline_type: "other",
        order: 1,
        icon: "x",
        estimated_duration: 0,
        has_skill: false,
      },
    ]);

    await waitFor(() => expect(api.getWorkflowDetail).toHaveBeenCalled());
    await act(async () => undefined);

    expect(rosterIds()).toEqual(["seed-agent"]);
    expect(screen.queryByText(/not found|failed to load/i)).not.toBeInTheDocument();
  });

  it("does not show a load error for the migration meta-type, which has no workflow of its own", async () => {
    api.getWorkflowDetail.mockRejectedValue({ status: 404 });
    renderWithProviders(
      <IdeaInputPage workflowType="migration" workflowId="migration" onBack={vi.fn()} onRun={vi.fn()} />,
    );

    await waitFor(() => expect(api.getWorkflowDetail).toHaveBeenCalledWith("test-token", "migration"));
    await act(async () => undefined);

    expect(screen.queryByText(/not found|failed to load/i)).not.toBeInTheDocument();
  });
});

describe("IdeaInputPage per-user override", () => {
  it("offers no override toggle when the user has no saved override", async () => {
    renderPage();
    await waitForRoster(["custom-agent:ask", "custom-agent:done", "summary-agent"]);

    expect(overrideState()).toHaveTextContent("false/false");
    expect(screen.queryByRole("button", { name: "override on" })).not.toBeInTheDocument();
  });

  it("shows the override's steps and re-sends its selections when the override is on at load", async () => {
    const user = userEvent.setup();
    api.getWorkflowDetail.mockResolvedValue(overrideDetail());
    const { onRun } = renderPage();

    await waitForRoster(["custom-agent:mine-a", "custom-agent:mine-b"]);
    expect(overrideState()).toHaveTextContent("true/true");
    await user.type(brief(), "Use mine");
    await user.click(screen.getByRole("button", { name: "Run workflow" }));

    expect(onRun.mock.calls[0][3]).toEqual({
      gate_agent_ids: [],
      selections: { "custom-agent:mine-a": { gates: ["human"] } },
    });
  });

  it("keeps the system roster and an inactive flag when the saved override is switched off at load", async () => {
    api.getWorkflowDetail.mockResolvedValue(
      overrideDetail({ is_overridden: false, manifest_steps: MANIFEST_STEPS }),
    );
    renderPage();

    await waitForRoster(["custom-agent:ask", "custom-agent:done", "summary-agent"]);

    expect(overrideState()).toHaveTextContent("true/false");
  });

  it("persists the off state, clears launch selections and keeps the roster when the override is toggled off", async () => {
    const user = userEvent.setup();
    api.getWorkflowDetail.mockResolvedValue(overrideDetail());
    const { onRun } = renderPage();
    await waitForRoster(["custom-agent:mine-a", "custom-agent:mine-b"]);

    await user.click(screen.getByRole("button", { name: "override off" }));

    await waitFor(() => expect(overrideState()).toHaveTextContent("true/false"));
    expect(api.setWorkflowOverrideEnabled).toHaveBeenCalledWith("test-token", "ov-1", false);
    await user.type(brief(), "Use system");
    await user.click(screen.getByRole("button", { name: "Run workflow" }));
    expect(onRun.mock.calls[0][3]).toEqual({ gate_agent_ids: [] });
  });

  it("restores the override's selections and persists the on state when toggled back on", async () => {
    const user = userEvent.setup();
    api.getWorkflowDetail.mockResolvedValue(overrideDetail());
    const { onRun } = renderPage();
    await waitForRoster(["custom-agent:mine-a", "custom-agent:mine-b"]);
    await user.click(screen.getByRole("button", { name: "override off" }));
    await waitFor(() => expect(overrideState()).toHaveTextContent("true/false"));

    await user.click(screen.getByRole("button", { name: "override on" }));

    await waitFor(() => expect(overrideState()).toHaveTextContent("true/true"));
    expect(api.setWorkflowOverrideEnabled).toHaveBeenLastCalledWith("test-token", "ov-1", true);
    await user.type(brief(), "Use mine again");
    await user.click(screen.getByRole("button", { name: "Run workflow" }));
    expect(onRun.mock.calls[0][3]).toEqual({
      gate_agent_ids: [],
      selections: { "custom-agent:mine-a": { gates: ["human"] } },
    });
  });

  it("keeps the toggled state on screen when persisting it fails", async () => {
    const user = userEvent.setup();
    api.getWorkflowDetail.mockResolvedValue(overrideDetail());
    api.setWorkflowOverrideEnabled.mockRejectedValue(new Error("offline"));
    renderPage();
    await waitForRoster(["custom-agent:mine-a", "custom-agent:mine-b"]);

    await user.click(screen.getByRole("button", { name: "override off" }));

    await waitFor(() => expect(api.setWorkflowOverrideEnabled).toHaveBeenCalled());
    expect(overrideState()).toHaveTextContent("true/false");
  });

  it("enables a saved-but-off override, reads back its rows and activates it", async () => {
    const user = userEvent.setup();
    api.getWorkflowDetail
      .mockResolvedValueOnce(overrideDetail({ is_overridden: false, manifest_steps: MANIFEST_STEPS }))
      .mockResolvedValueOnce(overrideDetail());
    renderPage();
    await waitForRoster(["custom-agent:ask", "custom-agent:done", "summary-agent"]);

    await user.click(screen.getByRole("button", { name: "override on" }));

    await waitForRoster(["custom-agent:mine-a", "custom-agent:mine-b"]);
    expect(api.setWorkflowOverrideEnabled).toHaveBeenCalledWith("test-token", "ov-1", true);
    expect(api.getWorkflowDetail).toHaveBeenCalledTimes(2);
    expect(overrideState()).toHaveTextContent("true/true");
  });

  it("turns the override back off when enabling a saved-but-off override fails", async () => {
    const user = userEvent.setup();
    api.getWorkflowDetail.mockResolvedValue(
      overrideDetail({ is_overridden: false, manifest_steps: MANIFEST_STEPS }),
    );
    api.setWorkflowOverrideEnabled.mockRejectedValue(new Error("denied"));
    renderPage();
    await waitForRoster(["custom-agent:ask", "custom-agent:done", "summary-agent"]);

    await user.click(screen.getByRole("button", { name: "override on" }));

    await waitFor(() => expect(api.setWorkflowOverrideEnabled).toHaveBeenCalled());
    expect(overrideState()).toHaveTextContent("true/false");
    expect(rosterIds()).toEqual(["custom-agent:ask", "custom-agent:done", "summary-agent"]);
  });

  it("does nothing when the override is toggled without a token", async () => {
    const user = userEvent.setup();
    api.getWorkflowDetail.mockResolvedValue(overrideDetail());
    renderPage();
    await waitForRoster(["custom-agent:mine-a", "custom-agent:mine-b"]);
    api.getToken.mockReturnValue(null);

    await user.click(screen.getByRole("button", { name: "override off" }));

    expect(api.setWorkflowOverrideEnabled).not.toHaveBeenCalled();
    expect(overrideState()).toHaveTextContent("true/true");
  });
});

describe("IdeaInputPage save as my version", () => {
  async function openLoadedPage(extra: Partial<PageProps> = {}) {
    const user = userEvent.setup();
    const view = renderPage(extra);
    await waitForRoster(["custom-agent:ask", "custom-agent:done", "summary-agent"]);
    return { user, ...view };
  }

  it("saves the lineup as an override of the built-in, with the brief as its description", async () => {
    const { user } = await openLoadedPage();
    await user.type(brief(), "  My brief  ");

    await user.click(screen.getByRole("button", { name: /save as my version/i }));

    await screen.findByText("Saved");
    expect(api.createUserWorkflow).toHaveBeenCalledTimes(1);
    const [token, body] = api.createUserWorkflow.mock.calls[0];
    expect(token).toBe("test-token");
    expect(body).toMatchObject({
      name: `My ${WF}`,
      description: "My brief",
      base_pipeline_type: WF,
      agent_ids: ["custom-agent:ask", "custom-agent:done", "summary-agent"],
      overrides_pipeline_type: WF,
    });
    const steps = body.manifest.steps as { gates?: string[] }[];
    expect(steps).toHaveLength(3);
    // ISS-225/254: the gate the manifest declares travels with the saved step.
    expect(steps[0].gates).toEqual(["conditional"]);
    expect(overrideState()).toHaveTextContent("true/true");
  });

  it("uses a generic description when the brief is empty", async () => {
    const { user } = await openLoadedPage();

    await user.click(screen.getByRole("button", { name: /save as my version/i }));

    await screen.findByText("Saved");
    expect(api.createUserWorkflow.mock.calls[0][1].description).toBe("Your saved version of this workflow.");
  });

  it("hides the save buttons while Saved is shown and brings them back after 2.5 seconds", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderPage();
    await waitForRoster(["custom-agent:ask", "custom-agent:done", "summary-agent"]);

    await user.click(screen.getByRole("button", { name: /save as my version/i }));
    await screen.findByText("Saved");
    expect(screen.queryByRole("button", { name: /save as my version/i })).not.toBeInTheDocument();

    await act(async () => {
      vi.advanceTimersByTime(2500);
    });

    expect(screen.queryByText("Saved")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /save as my version/i })).toBeInTheDocument();
  });

  it("shows the server's message when saving fails", async () => {
    api.createUserWorkflow.mockRejectedValue(new Error("name already taken"));
    const { user } = await openLoadedPage();

    await user.click(screen.getByRole("button", { name: /save as my version/i }));

    expect(await screen.findByText("name already taken")).toBeInTheDocument();
    expect(screen.queryByText("Saved")).not.toBeInTheDocument();
  });

  it("shows a generic message when saving fails without an error message", async () => {
    api.createUserWorkflow.mockRejectedValue(undefined);
    const { user } = await openLoadedPage();

    await user.click(screen.getByRole("button", { name: /save as my version/i }));

    expect(await screen.findByText("Failed to save your version.")).toBeInTheDocument();
  });

  it("asks the user to sign in when there is no token at save time", async () => {
    const { user } = await openLoadedPage();
    api.getToken.mockReturnValue(null);

    await user.click(screen.getByRole("button", { name: /save as my version/i }));

    expect(screen.getByText("Not authenticated.")).toBeInTheDocument();
    expect(api.createUserWorkflow).not.toHaveBeenCalled();
  });

  it("is disabled while the roster is empty", async () => {
    api.getWorkflowDetail.mockRejectedValue({ status: 404 });
    renderPage();
    await screen.findByText(/not found/);

    expect(screen.getByRole("button", { name: /save as my version/i })).toBeDisabled();
  });

  it("is not offered for a custom composition, which has no built-in to override", () => {
    renderWithProviders(
      <IdeaInputPage workflowType="custom" workflowId={WF} onBack={vi.fn()} onRun={vi.fn()} />,
    );

    expect(screen.queryByRole("button", { name: /save as my version/i })).not.toBeInTheDocument();
  });
});

describe("IdeaInputPage open in full canvas", () => {
  it("is not offered when the parent gave no canvas handler", async () => {
    renderPage();
    await waitForRoster(["custom-agent:ask", "custom-agent:done", "summary-agent"]);

    expect(screen.queryByRole("button", { name: "open in canvas" })).not.toBeInTheDocument();
  });

  it("closes the popup and hands over the live composition, using saved gate ids while gates are untouched", async () => {
    const user = userEvent.setup();
    const onOpenInCanvas = vi.fn();
    renderPage({
      onOpenInCanvas,
      initialModelOverrides: { "summary-agent": "model-x" },
      initialGateIds: ["saved-gate"],
    });
    await waitForRoster(["custom-agent:ask", "custom-agent:done", "summary-agent"]);
    await user.type(brief(), "  Canvas brief  ");
    await user.click(screen.getByRole("button", { name: /^advanced/i }));
    expect(screen.getByRole("status", { name: "Popup open" })).toHaveTextContent("true");
    await user.click(screen.getByRole("button", { name: "untouch gates" }));

    await user.click(screen.getByRole("button", { name: "open in canvas" }));

    expect(screen.getByRole("status", { name: "Popup open" })).toHaveTextContent("false");
    expect(onOpenInCanvas).toHaveBeenCalledWith({
      agentIds: ["custom-agent:ask", "custom-agent:done", "summary-agent"],
      manifestSteps: MANIFEST_STEPS,
      modelOverrides: { "summary-agent": "model-x" },
      selections: {},
      brief: "Canvas brief",
      gateAgentIds: ["saved-gate"],
    });
  });

  it("hands over the gate ids the user checked and omits an empty brief", async () => {
    const user = userEvent.setup();
    const onOpenInCanvas = vi.fn();
    renderPage({ onOpenInCanvas });
    await waitForRoster(["custom-agent:ask", "custom-agent:done", "summary-agent"]);
    await user.click(screen.getByRole("button", { name: "check gate" }));

    await user.click(screen.getByRole("button", { name: "open in canvas" }));

    const handed = onOpenInCanvas.mock.calls[0][0];
    expect(handed.gateAgentIds).toEqual(["gate-a"]);
    expect(handed.brief).toBeUndefined();
  });
});

describe("IdeaInputPage manifest projection edge cases", () => {
  const EDGE_STEPS = [
    { instance_id: "bare" },
    { instance_id: "plain" },
    {
      agent: "custom-agent",
      instance_id: "routed",
      name: "Routed",
      route: {
        outcomes: {
          go: { trigger: "step", target: "custom-agent:bare" },
          away: { trigger: "step", target: "unknown-step" },
        },
      },
    },
    {
      instance_id: "ext",
      name: "Ext",
      route: { condition_agent: "external-step", outcomes: {}, default_next: "nowhere" },
    },
    { instance_id: "noout", name: "NoOut", route: { condition_agent: "x" } },
  ] as unknown as ManifestStep[];

  it("defaults a step with no agent to a custom-agent node and names it from the compiled step, else its id", async () => {
    api.getWorkflowDetail.mockResolvedValue(
      detail({
        manifest_steps: EDGE_STEPS,
        steps: [step("custom-agent:bare", { name: "Compiled Bare" })],
      }),
    );
    renderPage();

    await waitForRoster([
      "custom-agent:bare",
      "custom-agent:plain",
      "custom-agent:routed",
      "custom-agent:ext",
      "custom-agent:noout",
    ]);
    const agents = readJson("Popup agents");
    expect(agents[0]).toMatchObject({ name: "Compiled Bare", isCustom: true, instance_id: "bare" });
    expect(agents[1]).toMatchObject({ name: "custom-agent:plain" });
  });

  it("leaves unknown route targets and external decision sources as authored", async () => {
    api.getWorkflowDetail.mockResolvedValue(detail({ manifest_steps: EDGE_STEPS }));
    renderPage();

    await waitForRoster([
      "custom-agent:bare",
      "custom-agent:plain",
      "custom-agent:routed",
      "custom-agent:ext",
      "custom-agent:noout",
    ]);
    const [, , routed, ext, noOutcomes] = readJson("Popup agents");
    expect(routed.route.outcomes).toEqual({
      go: { trigger: "step", target: "custom-agent:bare" },
      away: { trigger: "step", target: "unknown-step" },
    });
    expect(routed.route.condition_agent).toBeUndefined();
    expect(ext.route).toEqual({ condition_agent: "external-step", outcomes: {}, default_next: "nowhere" });
    expect(noOutcomes.route).toEqual({ condition_agent: "x" });
  });

  it("seeds no selections when no manifest step declares a gate", async () => {
    api.getWorkflowDetail.mockResolvedValue(detail({ manifest_steps: EDGE_STEPS }));
    renderPage();

    await waitForRoster([
      "custom-agent:bare",
      "custom-agent:plain",
      "custom-agent:routed",
      "custom-agent:ext",
      "custom-agent:noout",
    ]);

    expect(readJson("Live selections")).toEqual({});
    expect(readJson("Seed selections")).toBeNull();
  });

  it("numbers compiled steps by position when the API gives them no order", async () => {
    api.getWorkflowDetail.mockResolvedValue(
      detail({
        manifest_steps: null,
        steps: [step("first", { order: undefined as never }), step("second", { order: undefined as never })],
      }),
    );
    renderPage();

    await waitForRoster(["first", "second"]);

    expect(readJson("Popup agents").map((a: AgentDef) => a.order)).toEqual([1, 2]);
  });

  it("ignores a failure from a previous workflow id after the page moved to another workflow", async () => {
    let rejectFirst!: (e: unknown) => void;
    api.getWorkflowDetail.mockReturnValueOnce(new Promise((_, reject) => (rejectFirst = reject)));
    api.getWorkflowDetail.mockResolvedValueOnce(manifestDetail());
    const { rerenderPage } = renderPage();

    rerenderPage({ workflowId: "other_wf" });
    await waitForRoster(["custom-agent:ask", "custom-agent:done", "summary-agent"]);
    await act(async () => rejectFirst({ status: 404 }));

    expect(screen.queryByText(/not found/)).not.toBeInTheDocument();
    expect(rosterIds()).toEqual(["custom-agent:ask", "custom-agent:done", "summary-agent"]);
  });

  it("hands over no manifest steps when the workflow was projected from compiled steps only", async () => {
    const user = userEvent.setup();
    const onOpenInCanvas = vi.fn();
    api.getWorkflowDetail.mockResolvedValue(detail({ manifest_steps: null, steps: [step("compiled-a")] }));
    renderPage({ onOpenInCanvas });
    await waitForRoster(["compiled-a"]);

    await user.click(screen.getByRole("button", { name: "open in canvas" }));

    expect(onOpenInCanvas.mock.calls[0][0].manifestSteps).toBeUndefined();
    expect(onOpenInCanvas.mock.calls[0][0].agentIds).toEqual(["compiled-a"]);
  });

  it("saves as my version with the manifest steps alone when the manifest declares no gates", async () => {
    const user = userEvent.setup();
    api.getWorkflowDetail.mockResolvedValue(detail({ manifest_steps: null, steps: [step("compiled-a")] }));
    renderPage();
    await waitForRoster(["compiled-a"]);

    await user.click(screen.getByRole("button", { name: /save as my version/i }));

    await screen.findByText("Saved");
    const steps = api.createUserWorkflow.mock.calls[0][1].manifest.steps as { gates?: string[] }[];
    expect(steps).toHaveLength(1);
    expect(steps[0].gates ?? []).toEqual([]);
  });
});

describe("IdeaInputPage override edge cases", () => {
  const NO_GATE_OVERRIDE = [
    { agent: "custom-agent", instance_id: "plain-a", name: "Plain A" },
    { agent: "custom-agent", instance_id: "plain-b", name: "Plain B" },
  ] as ManifestStep[];

  it("launches without selections when the active override declares no gates", async () => {
    const user = userEvent.setup();
    api.getWorkflowDetail.mockResolvedValue(overrideDetail({ manifest_steps: NO_GATE_OVERRIDE }));
    const { onRun } = renderPage();
    await waitForRoster(["custom-agent:plain-a", "custom-agent:plain-b"]);
    await user.type(brief(), "Go");

    await user.click(screen.getByRole("button", { name: "Run workflow" }));

    expect(onRun.mock.calls[0][3]).toEqual({ gate_agent_ids: [] });
  });

  it("launches without selections after toggling a gate-free override off and back on", async () => {
    const user = userEvent.setup();
    api.getWorkflowDetail.mockResolvedValue(overrideDetail({ manifest_steps: NO_GATE_OVERRIDE }));
    const { onRun } = renderPage();
    await waitForRoster(["custom-agent:plain-a", "custom-agent:plain-b"]);
    await user.click(screen.getByRole("button", { name: "override off" }));
    await waitFor(() => expect(overrideState()).toHaveTextContent("true/false"));

    await user.click(screen.getByRole("button", { name: "override on" }));
    await waitFor(() => expect(overrideState()).toHaveTextContent("true/true"));
    await user.type(brief(), "Go");
    await user.click(screen.getByRole("button", { name: "Run workflow" }));

    expect(onRun.mock.calls[0][3]).toEqual({ gate_agent_ids: [] });
  });

  it("launches without selections after enabling a saved-but-off override that declares no gates", async () => {
    const user = userEvent.setup();
    api.getWorkflowDetail
      .mockResolvedValueOnce(overrideDetail({ is_overridden: false, manifest_steps: MANIFEST_STEPS }))
      .mockResolvedValueOnce(overrideDetail({ manifest_steps: NO_GATE_OVERRIDE }));
    const { onRun } = renderPage();
    await waitForRoster(["custom-agent:ask", "custom-agent:done", "summary-agent"]);

    await user.click(screen.getByRole("button", { name: "override on" }));
    await waitForRoster(["custom-agent:plain-a", "custom-agent:plain-b"]);
    await user.type(brief(), "Go");
    await user.click(screen.getByRole("button", { name: "Run workflow" }));

    expect(onRun.mock.calls[0][3]).toEqual({ gate_agent_ids: [] });
  });

  it("makes no request when the override is toggled after the workflow id was removed", async () => {
    const user = userEvent.setup();
    api.getWorkflowDetail.mockResolvedValue(overrideDetail());
    const { rerenderPage } = renderPage();
    await waitForRoster(["custom-agent:mine-a", "custom-agent:mine-b"]);
    rerenderPage({ workflowId: undefined });

    await user.click(screen.getByRole("button", { name: "override off" }));

    expect(api.setWorkflowOverrideEnabled).not.toHaveBeenCalled();
  });
});