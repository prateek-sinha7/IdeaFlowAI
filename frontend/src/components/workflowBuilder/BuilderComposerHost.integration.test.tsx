/**
 * Composer integration of the AI Workflow Builder (task 20.9): the real
 * `BuilderComposerHost`, builder reducer, panel, model picker and `ComposerPage`
 * (canvas, header, Save and Run once) working together in jsdom.
 *
 * Only the boundaries are replaced: Next.js navigation, the REST modules
 * (`@/lib/api`, `@/lib/workflowBuilderApi`) and the Session_Stream hook, which is
 * a controllable fake the tests push `BuilderEvent`s through. Drafts, prompts,
 * the read-only canvas, Save and the URL move are therefore the shipped code.
 *
 * Covers Req 3.8, 7.5, 7.9, 7.12, 8.6, 9.3, 10.10, 17.11, 49.9 and 49.12.
 */
import { act, cleanup, configure, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders, screen, waitFor } from "@/test/renderWithProviders";
import { consumeShallowNavTo } from "@/lib/shallowNavGuard";
import type { WorkflowManifest, WorkflowType } from "@/types/index";
import type {
  BuilderEvent,
  BuilderModelsResponse,
  DraftRevisionOut,
  SessionDetail,
  TranscriptMessage,
} from "@/types/workflowBuilder";

import { ApiError } from "@/lib/api";

import { resetBuilderHandoff, stashFirstMessage } from "./builderHandoff";

const mocks = vi.hoisted(() => ({
  pathname: "/workflows/new",
  search: "",
  push: vi.fn(),
  stream: { onEvent: null as ((event: unknown) => void) | null },
  getBuilderModels: vi.fn(),
  listSessions: vi.fn(),
  getSession: vi.fn(),
  sendMessage: vi.fn(),
  undoLastChange: vi.fn(),
  linkSession: vi.fn(),
  getUserWorkflows: vi.fn(),
  saveUserWorkflow: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => mocks.pathname,
  useRouter: () => ({ push: mocks.push }),
  useSearchParams: () => new URLSearchParams(mocks.search),
}));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  getToken: () => "token",
  getUserWorkflows: mocks.getUserWorkflows,
  saveUserWorkflow: mocks.saveUserWorkflow,
  getCapabilities: vi.fn().mockResolvedValue({ capabilities: [], model_catalog: [] }),
  getWorkflowDetail: vi.fn().mockResolvedValue({ steps: [] }),
  getAgentPrompt: vi.fn().mockResolvedValue({ prompt_body: "", override: null, has_override: false }),
  saveAgentPromptOverride: vi.fn(),
  deleteAgentPromptOverride: vi.fn(),
}));

vi.mock("@/lib/workflowBuilderApi", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/workflowBuilderApi")>()),
  getBuilderModels: mocks.getBuilderModels,
  listSessions: mocks.listSessions,
  getSession: mocks.getSession,
  sendMessage: mocks.sendMessage,
  undoLastChange: mocks.undoLastChange,
  linkSession: mocks.linkSession,
}));

// The stream is the transport: the fake keeps the host's latest `onEvent` so a test
// can deliver events exactly as the real hook would, one at a time.
vi.mock("@/hooks/useBuilderSessionStream", () => ({
  useBuilderSessionStream: (config: { onEvent: (event: unknown) => void }) => {
    mocks.stream.onEvent = config.onEvent;
    return { phase: "open", reconnect: () => undefined };
  },
}));

import { BuilderComposerHost } from "./BuilderComposerHost";

// --- Fixtures ------------------------------------------------------------------------

const TS = "2026-01-01T00:00:00Z";

const MODELS: BuilderModelsResponse = {
  models: [
    {
      id: "sonnet",
      label: "Sonnet",
      description: "",
      tier: "standard",
      cost_class: "standard",
      provider: "anthropic",
      context_window: 200000,
      user_allowed: true,
      reasoning_mode: "adaptive",
      reasoning_levels: ["low", "high"],
    },
  ],
  default_model_id: "sonnet",
  default_efforts: { sonnet: "low" },
};

function manifestOf(instanceId: string, name: string): WorkflowManifest {
  return {
    steps: [{ agent: "custom-agent", instance_id: instanceId, name, prompt: "Write it." }],
  } as unknown as WorkflowManifest;
}

const MANIFEST_A = manifestOf("draft-a", "Draft A");
const MANIFEST_B = manifestOf("draft-b", "Draft B");

function revision(
  n: number,
  manifest: WorkflowManifest,
  overrides: Partial<DraftRevisionOut> = {},
): DraftRevisionOut {
  return {
    revision: n,
    kind: "accepted",
    manifest: manifest as unknown as Record<string, unknown>,
    target_trust: "user",
    change_summary: null,
    launch_needs: [],
    source_turn_id: "t1",
    created_at: TS,
    ...overrides,
  };
}

function message(overrides: Partial<TranscriptMessage>): TranscriptMessage {
  return {
    id: "m1",
    seq: 1,
    role: "user",
    turn_id: "t1",
    reply_to_message_id: null,
    status: "accepted",
    outcome: null,
    stop_reason: null,
    content: "Make a blog workflow",
    thinking: null,
    steps: null,
    model_id: "sonnet",
    effort: "low",
    skill_hash: null,
    skill_updated: false,
    error: null,
    revision: null,
    activity: [],
    activity_summary: null,
    created_at: TS,
    ended_at: null,
    ...overrides,
  };
}

/** A finished turn whose reply carries accepted revision `n`. */
function draftTurn(n: number): TranscriptMessage[] {
  return [
    message({ id: "m1", seq: 1, content: "Make a blog workflow" }),
    message({
      id: "a1",
      seq: 2,
      role: "assistant",
      reply_to_message_id: "m1",
      status: "completed",
      outcome: "draft",
      content: "I built the workflow.",
      revision: n,
    }),
  ];
}

function sessionDetail(overrides: Partial<SessionDetail> = {}): SessionDetail {
  return {
    id: "s1",
    title: "Blog workflow",
    mode: "create",
    workflow_id: null,
    model_id: "sonnet",
    effort: "low",
    running: false,
    created_at: TS,
    updated_at: TS,
    target_trust: "user",
    skill_hash: "hash",
    messages: [],
    latest_draft: null,
    latest_unproposed: null,
    running_turn: null,
    linked_row_changed: false,
    ...overrides,
  };
}

/** What `GET /sessions/s1` answers; tests change it to model the server moving on. */
let server: SessionDetail;

// --- Stream helpers ------------------------------------------------------------------

function emit(event: BuilderEvent) {
  act(() => {
    mocks.stream.onEvent?.(event);
  });
}

function turnStarted(turnId: string): BuilderEvent {
  return {
    type: "turn_started",
    ts: TS,
    turn_id: turnId,
    seq: 1,
    message_id: "m-live",
    model_id: "sonnet",
    effort: "low",
    skill_hash: "hash",
  };
}

function draftApplied(turnId: string, n: number, manifest: WorkflowManifest): BuilderEvent {
  return {
    type: "draft_applied",
    ts: TS,
    turn_id: turnId,
    seq: 2,
    revision: n,
    target_trust: "user",
    change_summary: {
      added: [],
      removed: [],
      reordered: false,
      gates_changed: [],
      validators_changed: [],
      models_changed: [],
      prompts_changed: 0,
    },
    launch_needs: [],
    manifest: manifest as unknown as Record<string, unknown>,
  };
}

function turnCompleted(turnId: string, n: number | null): BuilderEvent {
  return {
    type: "turn_completed",
    ts: TS,
    turn_id: turnId,
    seq: 3,
    status: "completed",
    outcome: n === null ? "reply" : "draft",
    stop_reason: null,
    message_id: "a-live",
    revision: n,
    usage: { input: 0, output: 0, cache_read: 0, cache_write: 0, summary: null },
  };
}

// --- Rendering -----------------------------------------------------------------------

function setLocation(pathname: string, search: string) {
  mocks.pathname = pathname;
  mocks.search = search;
  window.history.replaceState(null, "", `${pathname}${search ? `?${search}` : ""}`);
}

function renderHost(extra: Record<string, unknown> = {}) {
  const onUnsavedChange = vi.fn();
  const utils = renderWithProviders(
    <BuilderComposerHost
      tier="enterprise"
      workflowType={"custom" as WorkflowType}
      onBack={() => undefined}
      onRun={vi.fn()}
      initialName="My flow"
      onUnsavedChange={onUnsavedChange}
      {...extra}
    />,
  );
  return { ...utils, onUnsavedChange };
}

const UPDATING = "The builder is updating this workflow.";
const DB_NOTE = /An unsaved canvas runs at user trust/;

/** Open the host on a session that already holds `latest_draft`, and wait for the canvas to show it. */
async function openWithDraft(manifest: WorkflowManifest, nodeId: string, extra = {}) {
  server = sessionDetail({
    messages: draftTurn(1),
    latest_draft: revision(1, manifest),
  });
  setLocation("/workflows/new", "ai=s1");
  const utils = renderHost(extra);
  await screen.findByTestId(`canvas-node-${nodeId}`);
  return utils;
}

// The first render of the full Composer is slow on a loaded runner; the default 1 s
// `findBy*` wait failed the first tests of a parallel run. A condition that holds is
// still found at once, so the longer bound only matters when something is wrong.
configure({ asyncUtilTimeout: 10_000 });

afterEach(() => {
  // Unmount first: a late re-render of the panel after a test reads `matchMedia`,
  // which must still be stubbed then.
  cleanup();
  vi.unstubAllGlobals();
});

beforeEach(() => {
  // jsdom has no `matchMedia`; the panel reads it for its dock query. A wide viewport docks it.
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: true,
    media: query,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  }));
  resetBuilderHandoff();
  vi.clearAllMocks();
  mocks.stream.onEvent = null;
  server = sessionDetail();
  setLocation("/workflows/new", "");
  mocks.getBuilderModels.mockResolvedValue(MODELS);
  mocks.listSessions.mockResolvedValue({ items: [], next_cursor: null });
  mocks.getSession.mockImplementation(async () => server);
  mocks.getUserWorkflows.mockResolvedValue([]);
  mocks.linkSession.mockResolvedValue({});
  mocks.sendMessage.mockResolvedValue({ turn_id: "t-own", message_id: "m-own", replayed: false });
  mocks.saveUserWorkflow.mockResolvedValue({ id: "wf-new" });
});

// --- Tests ---------------------------------------------------------------------------

describe("BuilderComposerHost with the real Composer — apply-draft path", () => {
  it("putsTheLatestDraftOnTheCanvasAndReportsUnsavedWork_whenASessionOpensFromTheUrl", async () => {
    const { onUnsavedChange } = await openWithDraft(MANIFEST_A, "draft-a");

    expect(screen.getByTestId("canvas-node-draft-a")).toBeInTheDocument();
    await waitFor(() => expect(onUnsavedChange).toHaveBeenLastCalledWith(true));
    expect(screen.getByRole("button", { name: /Save workflow/i })).toBeEnabled();
  });

  it("replacesTheCanvasWithoutAPrompt_whenThisTabSentTheMessageAndTheDraftArrives", async () => {
    const user = userEvent.setup();
    await openWithDraft(MANIFEST_A, "draft-a");

    await user.type(screen.getByLabelText("Message to the builder"), "Rename the step");
    await user.click(screen.getByRole("button", { name: "Send" }));

    // The canvas the builder gets is the one on screen, edits included (Req 9.2).
    await waitFor(() => expect(mocks.sendMessage).toHaveBeenCalledTimes(1));
    const [, sessionId, body] = mocks.sendMessage.mock.calls[0];
    expect(sessionId).toBe("s1");
    expect(body.canvas_state.steps[0]).toMatchObject({ instance_id: "draft-a" });

    server = sessionDetail({
      messages: draftTurn(2),
      latest_draft: revision(2, MANIFEST_B, { source_turn_id: "t-own" }),
    });
    emit(turnStarted("t-own"));
    emit(draftApplied("t-own", 2, MANIFEST_B));

    expect(await screen.findByTestId("canvas-node-draft-b")).toBeInTheDocument();
    expect(screen.queryByTestId("canvas-node-draft-a")).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    emit(turnCompleted("t-own", 2));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("BuilderComposerHost with the real Composer — first message", () => {
  const snapshotEvent: BuilderEvent = {
    type: "snapshot",
    ts: TS,
    state: "idle",
    running_turn: null,
    latest_message_id: null,
    latest_revision: null,
    latest_unproposed_revision: null,
  };

  it("putsTheFirstMessageBackInTheInput_whenItsSendIsRefused", async () => {
    mocks.sendMessage.mockRejectedValue(new ApiError(503, { detail: "busy" }));
    stashFirstMessage("s1", { text: "Make a brief", modelId: "sonnet", effort: "low" });
    setLocation("/workflows/new", "ai=s1");
    renderHost();
    const input = await screen.findByLabelText("Message to the builder");
    await waitFor(() => expect(mocks.getSession).toHaveBeenCalled());

    emit(snapshotEvent);

    await waitFor(() => expect(mocks.sendMessage).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(input).toHaveValue("Make a brief"));
  });

  it("leavesTheInputEmpty_whenTheFirstMessageIsAccepted", async () => {
    stashFirstMessage("s1", { text: "Make a brief", modelId: "sonnet", effort: "low" });
    setLocation("/workflows/new", "ai=s1");
    renderHost();
    const input = await screen.findByLabelText("Message to the builder");
    await waitFor(() => expect(mocks.getSession).toHaveBeenCalled());

    emit(snapshotEvent);

    await waitFor(() => expect(mocks.sendMessage).toHaveBeenCalledTimes(1));
    expect(input).toHaveValue("");
  });
});

describe("BuilderComposerHost with the real Composer — a turn in another tab", () => {
  it("holdsTheDraftAndAsksFirst_whenTheCanvasHasUnsavedWork", async () => {
    await openWithDraft(MANIFEST_A, "draft-a");
    server = sessionDetail({
      messages: draftTurn(2),
      latest_draft: revision(2, MANIFEST_B, { source_turn_id: "t-other" }),
    });

    emit(turnStarted("t-other"));
    emit(draftApplied("t-other", 2, MANIFEST_B));

    // Held while the turn runs: the canvas keeps the user's work and nothing asks yet.
    expect(screen.getByTestId("canvas-node-draft-a")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    emit(turnCompleted("t-other", 2));

    const dialog = await screen.findByRole("dialog", { name: "Load the builder's update?" });
    expect(screen.getByTestId("canvas-node-draft-a")).toBeInTheDocument();
    expect(screen.queryByTestId("canvas-node-draft-b")).not.toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Load update" }));

    expect(await screen.findByTestId("canvas-node-draft-b")).toBeInTheDocument();
    expect(screen.queryByTestId("canvas-node-draft-a")).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("keepsTheCanvasAndDoesNotAskAgain_whenTheUserDeclinesTheUpdate", async () => {
    await openWithDraft(MANIFEST_A, "draft-a");
    server = sessionDetail({
      messages: draftTurn(2),
      latest_draft: revision(2, MANIFEST_B, { source_turn_id: "t-other" }),
    });
    emit(turnStarted("t-other"));
    emit(draftApplied("t-other", 2, MANIFEST_B));
    emit(turnCompleted("t-other", 2));

    const dialog = await screen.findByRole("dialog", { name: "Load the builder's update?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Keep my changes" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    // The reload that follows the turn must not bring the prompt back for the same revision.
    await waitFor(() => expect(mocks.getSession.mock.calls.length).toBeGreaterThan(1));
    expect(screen.getByTestId("canvas-node-draft-a")).toBeInTheDocument();
    expect(screen.queryByTestId("canvas-node-draft-b")).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("loadsTheDraftWithoutAPrompt_whenTheCanvasHasNoUnsavedWork", async () => {
    server = sessionDetail();
    setLocation("/workflows/new", "ai=s1");
    renderHost();
    await screen.findByRole("button", { name: "Send" });
    await waitFor(() => expect(mocks.stream.onEvent).not.toBeNull());
    server = sessionDetail({
      messages: draftTurn(1),
      latest_draft: revision(1, MANIFEST_B, { source_turn_id: "t-other" }),
    });

    emit(turnStarted("t-other"));
    emit(draftApplied("t-other", 1, MANIFEST_B));
    emit(turnCompleted("t-other", 1));

    expect(await screen.findByTestId("canvas-node-draft-b")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("BuilderComposerHost with the real Composer — read-only canvas", () => {
  it("makesTheCanvasInertAndBlocksSave_whileATurnRunsInAnyTab", async () => {
    await openWithDraft(MANIFEST_A, "draft-a");
    expect(screen.getByTestId("canvas-view").closest("[inert]")).toBeNull();

    emit(turnStarted("t-other"));

    await waitFor(() => expect(screen.getByTestId("canvas-view").closest("[inert]")).not.toBeNull());
    expect(screen.getByText(UPDATING)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Save workflow/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Run once/i })).toBeDisabled();
    // The panel sits outside the inert body, so the turn can still be stopped (Req 5.5).
    const panel = screen.getByRole("complementary", { name: "AI workflow builder" });
    expect(panel.closest("[inert]")).toBeNull();
    expect(within(panel).getByRole("button", { name: "Stop" })).toBeEnabled();
  });

  it("makesTheCanvasEditableAgain_whenTheTurnEnds", async () => {
    await openWithDraft(MANIFEST_A, "draft-a");
    emit(turnStarted("t-other"));
    await waitFor(() => expect(screen.getByText(UPDATING)).toBeInTheDocument());

    emit(turnCompleted("t-other", null));

    await waitFor(() => expect(screen.queryByText(UPDATING)).not.toBeInTheDocument());
    expect(screen.getByTestId("canvas-view").closest("[inert]")).toBeNull();
    expect(screen.getByRole("button", { name: /Save workflow/i })).toBeEnabled();
  });
});

describe("BuilderComposerHost with the real Composer — Undo", () => {
  it("undoesAtOnce_whenTheCanvasIsStillTheDraft", async () => {
    mocks.undoLastChange.mockResolvedValue(revision(2, MANIFEST_A, { kind: "undo" }));
    await openWithDraft(MANIFEST_A, "draft-a");

    await userEvent.click(await screen.findByRole("button", { name: "Undo" }));

    await waitFor(() => expect(mocks.undoLastChange).toHaveBeenCalledTimes(1));
    expect(mocks.undoLastChange).toHaveBeenCalledWith("token", "s1", { expected_revision: 1 });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("asksBeforeDiscardingEdits_andOnlyUndoesAfterConfirmation", async () => {
    mocks.undoLastChange.mockResolvedValue(revision(2, MANIFEST_A, { kind: "undo" }));
    await openWithDraft(MANIFEST_A, "draft-a");
    await userEvent.click(screen.getByRole("button", { name: "Remove Draft A" }));
    await waitFor(() => expect(screen.queryByTestId("canvas-node-draft-a")).not.toBeInTheDocument());

    await userEvent.click(await screen.findByRole("button", { name: "Undo" }));
    const dialog = await screen.findByRole("dialog", { name: "Discard your edits?" });
    expect(mocks.undoLastChange).not.toHaveBeenCalled();

    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(mocks.undoLastChange).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "Undo" }));
    const again = await screen.findByRole("dialog", { name: "Discard your edits?" });
    await userEvent.click(within(again).getByRole("button", { name: "Undo and discard" }));

    await waitFor(() => expect(mocks.undoLastChange).toHaveBeenCalledTimes(1));
    expect(mocks.undoLastChange).toHaveBeenCalledWith("token", "s1", { expected_revision: 1 });
  });
});

describe("BuilderComposerHost with the real Composer — Save as new on a non-custom row", () => {
  const ROW = { id: "wf-proto", name: "Proto", base_pipeline_type: "prototype" };

  async function openOnPrototypeRow() {
    mocks.getUserWorkflows.mockResolvedValue([ROW]);
    server = sessionDetail({ mode: "edit", workflow_id: "wf-proto" });
    setLocation("/workflows/wf-proto/edit", "ai=s1");
    renderHost({ initialUserWorkflowId: "wf-proto", initialName: "Proto" });
    await screen.findByRole("button", { name: "Save as new" });
  }

  it("offersOnlySaveAsNew_whenTheLinkedRowIsNotCustom", async () => {
    await openOnPrototypeRow();

    await waitFor(() =>
      expect(screen.queryByRole("button", { name: /Save workflow/i })).not.toBeInTheDocument(),
    );
    expect(screen.getAllByRole("button", { name: "Save as new" })).toHaveLength(1);
  });

  it("createsANewRowLinksTheSessionAndMovesTheUrl_whenSaveAsNewSucceeds", async () => {
    mocks.saveUserWorkflow.mockResolvedValue({ id: "wf-copy" });
    await openOnPrototypeRow();
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: /Save workflow/i })).not.toBeInTheDocument(),
    );

    await userEvent.click(screen.getByRole("button", { name: "Save as new" }));

    await waitFor(() => expect(mocks.saveUserWorkflow).toHaveBeenCalledTimes(1));
    expect(mocks.saveUserWorkflow.mock.calls[0][1]).toBeUndefined();
    expect(mocks.saveUserWorkflow.mock.calls[0][2]).toMatchObject({ base_pipeline_type: "custom" });
    await waitFor(() =>
      expect(mocks.linkSession).toHaveBeenCalledWith("token", "s1", { workflow_id: "wf-copy" }),
    );
    await waitFor(() => expect(window.location.pathname).toBe("/workflows/wf-copy/edit"));
    expect(window.location.search).toBe("?ai=s1");
  });

  it("prefillsTheNameWithTheAiCopyName_whenTheRowIsNotCustom", async () => {
    await openOnPrototypeRow();

    expect(await screen.findByDisplayValue("Proto (AI)")).toBeInTheDocument();
  });
});

describe("BuilderComposerHost with the real Composer — Run once at db trust", () => {
  async function openWithDbDraft() {
    server = sessionDetail({
      messages: draftTurn(1),
      latest_draft: revision(1, MANIFEST_A, { target_trust: "db" }),
      target_trust: "db",
    });
    setLocation("/workflows/new", "ai=s1");
    renderHost();
    await screen.findByTestId("canvas-node-draft-a");
  }

  async function typeBrief(user: ReturnType<typeof userEvent.setup>) {
    await user.click(screen.getByRole("button", { name: /^Simple$/ }));
    await user.type(await screen.findByPlaceholderText(/Describe what you want/i), "Build a thing");
  }

  it("disablesRunOnceWithTheNote_whileTheDbDraftIsUnsaved", async () => {
    const user = userEvent.setup();
    await openWithDbDraft();
    await typeBrief(user);

    expect(screen.getByRole("button", { name: /Run once/i })).toBeDisabled();
    expect(screen.getByText(DB_NOTE)).toBeInTheDocument();
  });

  it("enablesRunOnceAndDropsTheNote_afterTheDraftIsSaved", async () => {
    const user = userEvent.setup();
    await openWithDbDraft();
    await user.click(screen.getByRole("button", { name: /Save workflow/i }));
    await waitFor(() => expect(mocks.saveUserWorkflow).toHaveBeenCalledTimes(1));
    await typeBrief(user);

    await waitFor(() => expect(screen.getByRole("button", { name: /Run once/i })).toBeEnabled());
    expect(screen.queryByText(DB_NOTE)).not.toBeInTheDocument();
  });
});

describe("BuilderComposerHost with the real Composer — first save", () => {
  it("linksTheSessionAndMovesTheUrlWithoutRemountingTheComposer_afterTheFirstSave", async () => {
    mocks.saveUserWorkflow.mockResolvedValue({ id: "wf-9" });
    await openWithDraft(MANIFEST_A, "draft-a");
    const nodeBefore = screen.getByTestId("canvas-node-draft-a");
    const canvasBefore = screen.getByTestId("canvas-view");

    await userEvent.click(screen.getByRole("button", { name: /Save workflow/i }));

    await waitFor(() =>
      expect(mocks.linkSession).toHaveBeenCalledWith("token", "s1", { workflow_id: "wf-9" }),
    );
    await waitFor(() => expect(window.location.pathname).toBe("/workflows/wf-9/edit"));
    expect(window.location.search).toBe("?ai=s1");
    // The page's cold-mount fetch is skipped by this one-shot, path-keyed mark (Req 3.8).
    expect(consumeShallowNavTo("/workflows/wf-9/edit")).toBe(true);
    expect(consumeShallowNavTo("/workflows/wf-9/edit")).toBe(false);
    // Same DOM nodes: the Composer was updated in place, so the draft is still on the canvas.
    expect(screen.getByTestId("canvas-view")).toBe(canvasBefore);
    expect(screen.getByTestId("canvas-node-draft-a")).toBe(nodeBefore);
    expect(nodeBefore.isConnected).toBe(true);
  });

  it("changesNeitherTheLinkNorTheUrl_whenTheSaveFails", async () => {
    mocks.saveUserWorkflow.mockRejectedValue(
      Object.assign(new Error("The manifest does not compile."), { status: 422 }),
    );
    await openWithDraft(MANIFEST_A, "draft-a");

    await userEvent.click(screen.getByRole("button", { name: /Save workflow/i }));

    expect(await screen.findByText("The manifest does not compile.")).toBeInTheDocument();
    expect(mocks.linkSession).not.toHaveBeenCalled();
    expect(window.location.pathname).toBe("/workflows/new");
    expect(screen.getByTestId("canvas-node-draft-a")).toBeInTheDocument();
  });
});
