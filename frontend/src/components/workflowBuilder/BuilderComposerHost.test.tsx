import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type {
  BuilderEvent,
  BuilderModelsResponse,
  ComposerBuilderBinding,
  SessionDetail,
} from "@/types/workflowBuilder";

import { EXAMPLE_PROMPTS } from "./BuilderEmptyState";
import { resetBuilderHandoff } from "./builderHandoff";

const mocks = vi.hoisted(() => ({
  pathname: "/workflows/new",
  search: "",
  push: vi.fn(),
  composerProps: [] as Array<Record<string, unknown>>,
  composerMounts: 0,
  getBuilderModels: vi.fn(),
  listSessions: vi.fn(),
  createSession: vi.fn(),
  sendMessage: vi.fn(),
  stream: { onEvent: null as ((event: unknown) => void) | null },
}));

vi.mock("next/navigation", () => ({
  usePathname: () => mocks.pathname,
  useRouter: () => ({ push: mocks.push }),
  useSearchParams: () => new URLSearchParams(mocks.search),
}));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  getToken: () => "token",
  getUserWorkflows: vi.fn().mockResolvedValue([]),
}));

vi.mock("@/lib/workflowBuilderApi", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/workflowBuilderApi")>()),
  getBuilderModels: mocks.getBuilderModels,
  listSessions: mocks.listSessions,
  createSession: mocks.createSession,
  sendMessage: mocks.sendMessage,
}));

// The stream is the transport: the fake keeps the host's latest `onEvent` so a test
// can deliver the first snapshot exactly as the real hook would.
vi.mock("@/hooks/useBuilderSessionStream", () => ({
  useBuilderSessionStream: (config: { onEvent: (event: unknown) => void }) => {
    mocks.stream.onEvent = config.onEvent;
    return { phase: "open", reconnect: () => undefined };
  },
}));

vi.mock("@/components/workflow/composer/ComposerPage", async () => {
  const { useEffect } = await import("react");
  return {
    ComposerPage: (props: Record<string, unknown>) => {
      mocks.composerProps.push(props);
      useEffect(() => {
        mocks.composerMounts += 1;
      }, []);
      const builder = props.builder as ComposerBuilderBinding | undefined;
      return (
        <div data-testid="composer">
          {builder?.aiButtonVisible ? (
            <button type="button" onClick={builder.onAiButton}>
              AI
            </button>
          ) : null}
          {props.builderPanel as ReactNode}
        </div>
      );
    },
  };
});

import { BuilderComposerHost } from "./BuilderComposerHost";

const models: BuilderModelsResponse = {
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

const TS = "2026-01-01T00:00:00Z";

function sessionDetail(overrides: Partial<SessionDetail> = {}): SessionDetail {
  return {
    id: "s1",
    title: "Brief workflow",
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

const SNAPSHOT: BuilderEvent = {
  type: "snapshot",
  ts: TS,
  state: "idle",
  running_turn: null,
  latest_message_id: null,
  latest_revision: null,
  latest_unproposed_revision: null,
};

/** A promise the test settles by hand, to hold `createSession` open. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function lastBinding(): ComposerBuilderBinding | undefined {
  return mocks.composerProps.at(-1)?.builder as ComposerBuilderBinding | undefined;
}

function renderHost(tier: "basic" | "enterprise" | null) {
  return render(<BuilderComposerHost tier={tier} workflowType="custom" onBack={() => undefined} />);
}

const panel = () => screen.queryByRole("complementary", { name: "AI workflow builder" });
const box = () => screen.getByRole("textbox", { name: "Message to the builder" });

/** Open the empty panel from the AI button. */
async function openPanel(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "AI" }));
  expect(panel()).toBeInTheDocument();
}

describe("BuilderComposerHost", () => {
  beforeEach(() => {
    resetBuilderHandoff();
    // jsdom has no `matchMedia`; the panel reads it for its dock query. A wide viewport docks it.
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: true,
      media: query,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }));
    mocks.pathname = "/workflows/new";
    mocks.search = "";
    mocks.push.mockReset();
    mocks.composerProps.length = 0;
    mocks.composerMounts = 0;
    mocks.stream.onEvent = null;
    mocks.getBuilderModels.mockReset().mockResolvedValue(models);
    mocks.listSessions.mockReset().mockResolvedValue({ items: [], next_cursor: null });
    mocks.createSession.mockReset().mockResolvedValue(sessionDetail());
    mocks.sendMessage
      .mockReset()
      .mockResolvedValue({ turn_id: "t1", message_id: "m1", replayed: false });
  });

  afterEach(() => {
    // Unmount first: a late re-render of the panel reads `matchMedia`, which must still be stubbed.
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders_composerWithoutBinding_whenTierLacksCustomEntitlement", async () => {
    renderHost("basic");

    expect(screen.getByTestId("composer")).toBeInTheDocument();
    expect(mocks.getBuilderModels).not.toHaveBeenCalled();
    expect(lastBinding()).toBeUndefined();
  });

  it("renders_composerWithoutBinding_whenModelsRequestFails", async () => {
    mocks.getBuilderModels.mockRejectedValue(new Error("404"));
    renderHost("enterprise");

    await waitFor(() => expect(mocks.getBuilderModels).toHaveBeenCalledTimes(1));
    expect(lastBinding()).toBeUndefined();
    expect(screen.queryByRole("button", { name: "AI" })).not.toBeInTheDocument();
  });

  it("passesBindingAndKeepsComposerMounted_whenModelsArriveAfterFirstRender", async () => {
    renderHost("enterprise");
    expect(lastBinding()).toBeUndefined();

    await waitFor(() => expect(lastBinding()?.aiButtonVisible).toBe(true));
    expect(mocks.composerMounts).toBe(1);
    expect(lastBinding()?.turnRunning).toBe(false);
  });

  it("usesTheGivenBaseWithoutARowLookup_whenLinkedBasePipelineTypeIsPassed", async () => {
    const api = await import("@/lib/api");
    const lookup = vi.mocked(api.getUserWorkflows);
    lookup.mockClear();
    mocks.pathname = "/workflows/wf-1/edit";
    render(
      <BuilderComposerHost
        tier="enterprise"
        linkedBasePipelineType="prototype"
        workflowType="custom"
        onBack={() => undefined}
      />,
    );

    await waitFor(() => expect(lastBinding()).toBeDefined());
    expect(lastBinding()?.linkedBaseIsCustom).toBe(false);
    expect(lookup).not.toHaveBeenCalled();
  });

  it("hidesAiButton_whenRouteIsNotNewOrEdit", async () => {
    mocks.pathname = "/workflows/pptx/canvas";
    renderHost("enterprise");

    await waitFor(() => expect(mocks.getBuilderModels).toHaveBeenCalled());
    await waitFor(() => expect(lastBinding()).toBeDefined());
    expect(lastBinding()?.aiButtonVisible).toBe(false);
  });

  it("opensTheEmptyPanelWithTheCursorInTheBox_whenTheAiButtonIsClickedWithoutAnAiParam", async () => {
    const user = userEvent.setup();
    renderHost("enterprise");

    await openPanel(user);

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(box()).toHaveFocus();
    expect(screen.getByRole("heading", { name: "What should this workflow do?" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: EXAMPLE_PROMPTS[0] })).toBeInTheDocument();
    expect(lastBinding()?.panelOpen).toBe(true);
    await waitFor(() => expect(mocks.listSessions).toHaveBeenCalled());
  });

  it("collapsesThePanel_whenTheAiButtonIsClickedWhileThePanelIsOpen", async () => {
    const user = userEvent.setup();
    renderHost("enterprise");
    await openPanel(user);

    await user.click(screen.getByRole("button", { name: "AI" }));

    expect(panel()).toBeNull();
    expect(lastBinding()?.panelOpen).toBe(false);
  });

  it("fillsTheBoxAndSendsNothing_whenAnExamplePromptIsPicked", async () => {
    const user = userEvent.setup();
    renderHost("enterprise");
    await openPanel(user);

    await user.click(screen.getByRole("button", { name: EXAMPLE_PROMPTS[1] }));

    expect(box()).toHaveValue(EXAMPLE_PROMPTS[1]);
    expect(box()).toHaveFocus();
    expect(mocks.createSession).not.toHaveBeenCalled();
    expect(mocks.sendMessage).not.toHaveBeenCalled();
  });

  it("showsTheMessageAtOnceAndCreatesOneSession_whenTheUserSendsAgainWhileItIsCreated", async () => {
    const user = userEvent.setup();
    const create = deferred<SessionDetail>();
    mocks.createSession.mockReturnValue(create.promise);
    renderHost("enterprise");
    await openPanel(user);

    await user.type(box(), "Make a brief{Enter}");

    // The text moved from the box into the transcript before the server answered.
    expect(box()).toHaveValue("");
    expect(screen.getByRole("article", { name: "Your message" })).toHaveTextContent("Make a brief");
    expect(screen.getByText("Sending")).toBeInTheDocument();

    // A second message cannot start a second session while the first is created.
    await user.type(box(), "And another{Enter}");
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "New conversation" })).toBeDisabled();
    expect(mocks.createSession).toHaveBeenCalledTimes(1);

    await act(async () => {
      create.resolve(sessionDetail());
    });
    expect(screen.getByRole("article", { name: "Your message" })).toHaveTextContent("Make a brief");

    // The first snapshot sends the first message once, with the picker's choice.
    act(() => {
      mocks.stream.onEvent?.(SNAPSHOT);
    });
    await waitFor(() => expect(mocks.sendMessage).toHaveBeenCalledTimes(1));
    expect(mocks.sendMessage.mock.calls[0][2]).toMatchObject({
      content: "Make a brief",
      model_id: "sonnet",
      effort: "low",
    });
    expect(mocks.createSession).toHaveBeenCalledTimes(1);
  });

  it("putsTheTextBackAndExplains_whenTheSessionCannotBeCreated", async () => {
    const user = userEvent.setup();
    mocks.createSession.mockRejectedValue(new Error("boom"));
    renderHost("enterprise");
    await openPanel(user);

    await user.type(box(), "Make a brief{Enter}");

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not start the conversation");
    expect(box()).toHaveValue("Make a brief");
    expect(screen.queryByRole("article", { name: "Your message" })).toBeNull();
    expect(screen.getByRole("button", { name: "Send" })).toBeEnabled();
  });

  it("startsAnEditSessionOnTheOpenWorkflowWithoutANewCanvas_whenTheFirstMessageIsSentOnAnEditRoute", async () => {
    const user = userEvent.setup();
    mocks.pathname = "/workflows/wf-1/edit";
    mocks.createSession.mockResolvedValue(sessionDetail({ mode: "edit", workflow_id: "wf-1" }));
    renderHost("enterprise");
    await openPanel(user);

    await user.type(box(), "Add a review gate{Enter}");

    await waitFor(() => expect(mocks.createSession).toHaveBeenCalledTimes(1));
    expect(mocks.createSession).toHaveBeenCalledWith("token", {
      mode: "edit",
      workflow_id: "wf-1",
      model_id: "sonnet",
      effort: "low",
    });
    // The open workflow stays on the canvas: no navigation, no remount.
    expect(mocks.push).not.toHaveBeenCalled();
    expect(mocks.composerMounts).toBe(1);
    await waitFor(() => expect(window.location.search).toBe("?ai=s1"));
    expect(window.location.pathname).toBe("/workflows/wf-1/edit");
  });

  it("registersACanvasApiGetter_whenComposerCallsRegister", async () => {
    renderHost("enterprise");
    await waitFor(() => expect(lastBinding()).toBeDefined());

    const getManifest = vi.fn(() => ({ steps: [] }));
    act(() => {
      lastBinding()?.registerCanvasApi({ getManifest, isDirty: () => false });
    });

    expect(getManifest).not.toHaveBeenCalled();
  });
});
