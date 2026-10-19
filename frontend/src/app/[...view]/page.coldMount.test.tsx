/**
 * Behavior tests for the `[...view]` catch-all page (`page.tsx`).
 *
 * The sibling tests in this folder read `page.tsx` as text. These MOUNT the real
 * `DashboardPage` and drive it through its system boundaries:
 *   - `next/navigation`            (router, pathname, notFound)
 *   - `@/lib/api`                  (REST wrappers; `ApiError` stays real)
 *   - `@/store/api/userWorkflows`  (saved-workflow fetch; helpers stay real)
 *   - `@/providers/RunConnectionProvider` (SSE connection: subscribe/attach/send)
 *   - `@/store/hooks`              (redux dispatch)
 *
 * `DashboardLayout`, `WorkflowDetailView` and `LaunchWizard` are replaced by thin
 * stubs: DashboardLayout is a ~3k-line shell with its own suites, and what this
 * file owns is the contract page.tsx has WITH it (the props it computes and the
 * callbacks it hands down). The stub exposes those through a captured-props
 * holder plus buttons that invoke the real callbacks the way a user click does.
 * `useWorkflow`, `useRunStateStore`, `useRunChat` and `useTabDeepLink` run for real.
 */
import { Component, type ReactNode } from "react";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";
import { signedIn, signedOut, userLoaded } from "@/store/slices/authSlice";
import type { DashboardLayoutProps } from "@/components/layout/DashboardLayout";
import type { WorkflowRun } from "@/types/index";

import DashboardPage from "./page";

// --- hoisted boundary doubles

const h = vi.hoisted(() => {
  const nav = { pathname: "/dashboard" };
  const router = { replace: vi.fn(), push: vi.fn(), back: vi.fn(), prefetch: vi.fn(), refresh: vi.fn(), forward: vi.fn() };
  const dispatch = vi.fn();
  const api = {
    getToken: vi.fn(),
    getMe: vi.fn(),
    logout: vi.fn(),
    getWorkflows: vi.fn(),
    getWorkflow: vi.fn(),
    getWorkflowDetail: vi.fn(),
    getRunEvents: vi.fn(),
    getRunFamily: vi.fn(),
    postGate: vi.fn(),
    getChat: vi.fn(),
    deleteChat: vi.fn(),
    handleSessionExpiry: vi.fn(),
  };
  const userWorkflowsGet = vi.fn();
  const conn = {
    enabled: true,
    phase: "idle" as string,
    liveRunIds: [] as string[],
    reattach: vi.fn(),
    attachRun: vi.fn(),
    detachRun: vi.fn(),
    subscribe: vi.fn(() => () => {}),
    sendCommand: vi.fn(),
    recentRuns: [] as unknown[],
    recentRunsLoaded: true,
    setRecentRuns: vi.fn(),
    loadRecentRuns: vi.fn(),
  };
  const layout = { props: null as unknown as DashboardLayoutProps };
  return { nav, router, dispatch, api, userWorkflowsGet, conn, layout };
});

vi.mock("next/navigation", () => ({
  useRouter: () => h.router,
  usePathname: () => h.nav.pathname,
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, ...h.api };
});

vi.mock("@/store/api/userWorkflows", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/store/api/userWorkflows")>();
  return { ...actual, userWorkflowsApi: { ...actual.userWorkflowsApi, get: h.userWorkflowsGet } };
});

vi.mock("@/store/hooks", () => ({ useAppDispatch: () => h.dispatch }));

vi.mock("@/providers/RunConnectionProvider", () => ({ useRunConnection: () => h.conn }));

vi.mock("@/components/layout/DashboardLayout", () => ({
  DashboardLayout: (props: DashboardLayoutProps) => {
    h.layout.props = props;
    return (
      // data-testid: this is a stub shell with no semantic landmark of its own.
      <div data-testid="dashboard-layout">
        <button onClick={() => void props.onLogout?.()}>Log out</button>
        <button onClick={() => props.onApproveReview?.("g1", "edited text")}>Approve gate</button>
        <button onClick={() => props.onRejectReview?.("g1")}>Reject gate</button>
        <button onClick={() => props.onRedoReview?.("g1", "tighten it")}>Redo gate</button>
        <button onClick={() => props.onUpdateSpecsReview?.("g1", "report")}>Update specs</button>
        <button onClick={() => props.onClearPendingOdProto?.()}>Clear proto</button>
        <button onClick={() => props.onClearPendingOdPpt?.()}>Clear ppt</button>
        <button onClick={() => void props.onSelectChat("c1")}>Select chat</button>
        <button onClick={() => void props.onDeleteChat("c1")}>Delete chat</button>
        <button onClick={() => void props.onSwitchToLiveRun?.("r2")}>Switch live</button>
        <button onClick={() => props.onRevisionLaunched?.("rev1")}>Revision launched</button>
        <button onClick={() => props.onStartPipeline?.("user_stories", "Write stories")}>Start run</button>
        <button onClick={() => props.onReconnect?.()}>Reconnect</button>
      </div>
    );
  },
}));

vi.mock("@/components/savedworkflows/WorkflowDetailView", () => ({
  WorkflowDetailView: ({ workflow }: { workflow: { name: string } }) => <h1>{workflow.name}</h1>,
}));

vi.mock("@/components/workflow/LaunchWizard", () => ({
  LaunchWizard: ({ initialMode }: { initialMode: string }) => <p>wizard:{initialMode}</p>,
}));

// --- helpers

/** Renders a visible marker when the page calls `notFound()` (which throws). */
class NotFoundBoundary extends Component<{ children: ReactNode }, { notFound: boolean }> {
  state = { notFound: false };
  static getDerivedStateFromError() {
    return { notFound: true };
  }
  render() {
    return this.state.notFound ? <p role="alert">not-found</p> : this.props.children;
  }
}

function mount(pathname: string) {
  h.nav.pathname = pathname;
  return render(
    <NotFoundBoundary>
      <DashboardPage />
    </NotFoundBoundary>,
  );
}

const props = () => h.layout.props;

/** A full run record shaped like `getWorkflow` returns it. */
function runRecord(overrides: Record<string, unknown> = {}): WorkflowRun {
  return {
    id: "r1",
    status: "completed",
    type: "user_stories",
    input: "Write stories",
    title: "Stories run",
    output: "",
    agentCount: 3,
    agentOutputs: [],
    error: undefined,
    ...overrides,
  } as unknown as WorkflowRun;
}

/** A saved user workflow shaped like `userWorkflowsApi.get` returns it. */
function savedWorkflow(overrides: Record<string, unknown> = {}) {
  return {
    id: "w1",
    name: "My Flow",
    description: "does things",
    base_pipeline_type: "custom",
    agent_ids: ["a1", "a2"],
    model_overrides: { a1: "model-x" },
    selections: {},
    manifest: null,
    ...overrides,
  };
}

async function untilDashboard() {
  return screen.findByTestId("dashboard-layout");
}

let consoleError: ReturnType<typeof vi.spyOn>;
// ISS-1137: a refused launch is logged with console.warn, not console.error.
let consoleWarn: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  h.nav.pathname = "/dashboard";
  h.layout.props = null as unknown as DashboardLayoutProps;
  h.conn.phase = "idle";
  h.conn.liveRunIds = [];
  h.conn.recentRuns = [];
  h.conn.subscribe.mockImplementation(() => () => {});
  h.conn.sendCommand.mockResolvedValue(null);
  h.api.getToken.mockReturnValue("tok");
  h.api.getMe.mockResolvedValue({ id: "u1", email: "ada@example.com", tier: "basic", is_admin: false });
  h.api.logout.mockResolvedValue(undefined);
  h.api.getWorkflows.mockResolvedValue({ runs: [] });
  h.api.getRunEvents.mockResolvedValue([]);
  h.api.getRunFamily.mockResolvedValue({ members: [] });
  h.api.postGate.mockResolvedValue(undefined);
  h.api.deleteChat.mockResolvedValue(undefined);
  consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
  consoleWarn = vi.spyOn(console, "warn").mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

// --- auth guard

describe("DashboardPage auth guard", () => {
  it("redirects to login and renders nothing when no token is stored", async () => {
    h.api.getToken.mockReturnValue(null);

    const { container } = mount("/dashboard");

    await waitFor(() => expect(h.router.replace).toHaveBeenCalledTimes(1));
    expect(h.router.replace).toHaveBeenCalledWith(expect.stringMatching(/^\/login/));
    expect(container).toBeEmptyDOMElement();
    expect(h.api.getMe).not.toHaveBeenCalled();
    expect(h.dispatch).not.toHaveBeenCalled();
  });

  it("announces sign-in exactly once and stores the loaded profile when a token exists", async () => {
    const me = { id: "u1", email: "ada@example.com", tier: "pro", is_admin: true };
    h.api.getMe.mockResolvedValue(me);

    mount("/dashboard");
    await untilDashboard();

    await waitFor(() => expect(h.dispatch).toHaveBeenCalledWith(userLoaded(me as never)));
    const signedInCalls = h.dispatch.mock.calls.filter(([a]) => a.type === signedIn({ token: "tok" }).type);
    expect(signedInCalls).toEqual([[signedIn({ token: "tok" })]]);
    expect(h.api.getMe).toHaveBeenCalledWith("tok");
  });

  it("threads the profile tier, email and admin flag down to the layout", async () => {
    h.api.getMe.mockResolvedValue({ id: "u1", email: "ada@example.com", tier: "pro", is_admin: true });

    mount("/dashboard");

    await waitFor(() => expect(props().userTier).toBe("pro"));
    expect(props().userEmail).toBe("ada@example.com");
    expect(props().isAdmin).toBe(true);
  });

  it("falls back to basic tier and still renders when the profile fetch fails", async () => {
    h.api.getMe.mockRejectedValue(new Error("boom"));

    mount("/dashboard");
    await untilDashboard();

    expect(props().userTier).toBe("basic");
    expect(props().isAdmin).toBe(false);
    expect(h.dispatch.mock.calls.some(([a]) => a.type === userLoaded({} as never).type)).toBe(false);
  });
});

// --- route -> screen mapping

describe("DashboardPage route to screen mapping", () => {
  it.each([
    ["/dashboard", "home"],
    ["/create", "home"],
    ["/create/app", "input"],
    ["/create/user-stories", "input"],
    ["/create/custom_flow", "input"],
    ["/workflows/new", "composer"],
    ["/workflows", "saved-workflows"],
    ["/runs", "history"],
    ["/library", "library"],
    ["/library/agents/some-agent", "library"],
    ["/settings/profile", "settings"],
    ["/analytics", "analytics"],
  ])("opens %s on the %s main view", async (path, mainView) => {
    mount(path);
    await untilDashboard();

    expect(props().initialMainView).toBe(mainView);
  });

  it.each([
    ["/settings/profile", "profile"],
    ["/settings/ai-model", "model"],
    ["/settings/usage", "limits"],
    ["/settings/constitution", "constitution"],
    ["/settings/security", "security"],
  ])("opens %s on the %s settings section", async (path, section) => {
    mount(path);
    await untilDashboard();

    expect(props().initialSettingsSection).toBe(section);
  });

  it("carries the pipeline type of a generic /create/{type} cold load to the launch panel", async () => {
    mount("/create/custom_flow");
    await untilDashboard();

    expect(props().initialWorkflowType).toBe("custom_flow");
  });

  it("renders not-found for a path no screen owns", async () => {
    mount("/definitely/not/a/route");

    expect(await screen.findByRole("alert")).toHaveTextContent("not-found");
    expect(screen.queryByTestId("dashboard-layout")).not.toBeInTheDocument();
  });

  it.each([
    ["connecting", "connecting"],
    ["reconnecting", "reconnecting"],
    ["failed", "failed"],
    ["disconnected", "disconnected"],
    ["replaying", "connected"],
    ["live", "connected"],
    ["idle", "connected"],
  ])("maps SSE phase %s to connection status %s", async (phase, status) => {
    h.conn.phase = phase;

    mount("/dashboard");
    await untilDashboard();

    expect(props().connectionStatus).toBe(status);
  });

  it("routes the layout's reconnect action to the provider's server-derived reattach", async () => {
    const user = userEvent.setup();
    mount("/dashboard");
    await untilDashboard();

    await user.click(screen.getByRole("button", { name: "Reconnect" }));

    expect(h.conn.reattach).toHaveBeenCalledTimes(1);
  });
});

// --- standalone wizard routes

describe("DashboardPage wizard routes", () => {
  it.each([
    ["/create/ppt", "ppt"],
    ["/create/prototype", "prototype"],
    ["/create/ppt_v2", "ppt_v2"],
    ["/create/prototype_v2", "prototype_v2"],
  ])("renders the launch wizard in %s mode outside the dashboard shell", async (path, mode) => {
    mount(path);

    expect(await screen.findByText(`wizard:${mode}`)).toBeInTheDocument();
    expect(screen.queryByTestId("dashboard-layout")).not.toBeInTheDocument();
  });
});

// --- staged wizard runs

describe("DashboardPage staged wizard runs", () => {
  it("opens the execution view directly when a wizard run is pending on the home route", async () => {
    sessionStorage.setItem("ppt.pending", "1");

    mount("/dashboard");
    await untilDashboard();

    expect(props().initialMainView).toBe("execution");
  });

  it("hands a staged prototype draft to the layout once connected and consumes the storage keys", async () => {
    sessionStorage.setItem("prototype.pending", "1");
    sessionStorage.setItem(
      "prototype.draft",
      JSON.stringify({ designSystemId: "ds1", templateId: "t1", brief: "Build a shop", agentIds: ["a1"], pipelineType: "prototype_v2" }),
    );

    mount("/dashboard");

    await waitFor(() => expect(props().pendingOdProtoParams).not.toBeNull());
    expect(props().pendingOdProtoParams).toEqual({
      brief: "Build a shop",
      templateId: "t1",
      designSystemId: "ds1",
      discovery: null,
      agentIds: ["a1"],
      pipelineType: "prototype_v2",
    });
    expect(sessionStorage.getItem("prototype.pending")).toBeNull();
    expect(sessionStorage.getItem("prototype.draft")).toBeNull();
  });

  it("lets the layout clear the staged prototype params after consuming them", async () => {
    const user = userEvent.setup();
    sessionStorage.setItem("prototype.pending", "1");
    sessionStorage.setItem("prototype.draft", JSON.stringify({ designSystemId: "ds1" }));
    mount("/dashboard");
    await waitFor(() => expect(props().pendingOdProtoParams).not.toBeNull());

    await user.click(screen.getByRole("button", { name: "Clear proto" }));

    expect(props().pendingOdProtoParams).toBeNull();
  });

  it("ignores a staged prototype draft that names no design system", async () => {
    sessionStorage.setItem("prototype.pending", "1");
    sessionStorage.setItem("prototype.draft", JSON.stringify({ brief: "no ds" }));

    mount("/dashboard");
    await untilDashboard();

    expect(props().pendingOdProtoParams).toBeNull();
    expect(sessionStorage.getItem("prototype.pending")).toBe("1");
  });

  it("ignores a staged prototype draft that is not valid JSON", async () => {
    sessionStorage.setItem("prototype.pending", "1");
    sessionStorage.setItem("prototype.draft", "{not json");

    mount("/dashboard");
    await untilDashboard();

    expect(props().pendingOdProtoParams).toBeNull();
  });

  it("hands a staged deck draft to the layout once connected and consumes the storage keys", async () => {
    sessionStorage.setItem("ppt.pending", "1");
    sessionStorage.setItem("ppt.draft", JSON.stringify({ templateId: "t9", brief: "Q3 deck", pipelineType: "ppt_v2" }));

    mount("/dashboard");

    await waitFor(() => expect(props().pendingOdPptParams).not.toBeNull());
    expect(props().pendingOdPptParams).toEqual({
      brief: "Q3 deck",
      templateId: "t9",
      designSystemId: null,
      discovery: null,
      pipelineType: "ppt_v2",
    });
    expect(sessionStorage.getItem("ppt.pending")).toBeNull();
    expect(sessionStorage.getItem("ppt.draft")).toBeNull();
  });

  it("lets the layout clear the staged deck params after consuming them", async () => {
    const user = userEvent.setup();
    sessionStorage.setItem("ppt.pending", "1");
    sessionStorage.setItem("ppt.draft", JSON.stringify({ templateId: "t9" }));
    mount("/dashboard");
    await waitFor(() => expect(props().pendingOdPptParams).not.toBeNull());

    await user.click(screen.getByRole("button", { name: "Clear ppt" }));

    expect(props().pendingOdPptParams).toBeNull();
  });

  it("ignores a staged deck draft that names no template", async () => {
    sessionStorage.setItem("ppt.pending", "1");
    sessionStorage.setItem("ppt.draft", JSON.stringify({ brief: "no template" }));

    mount("/dashboard");
    await untilDashboard();

    expect(props().pendingOdPptParams).toBeNull();
    expect(sessionStorage.getItem("ppt.pending")).toBe("1");
  });

  it("keeps a staged prototype run staged while the connection is not ready", async () => {
    h.conn.phase = "failed";
    sessionStorage.setItem("prototype.pending", "1");
    sessionStorage.setItem("prototype.draft", JSON.stringify({ designSystemId: "ds1" }));

    mount("/dashboard");
    await untilDashboard();

    expect(props().pendingOdProtoParams).toBeNull();
    expect(sessionStorage.getItem("prototype.pending")).toBe("1");
  });
});

// --- /workflows/{id} read view

describe("DashboardPage saved-workflow read view", () => {
  it("renders nothing while the workflow is loading, then its detail view", async () => {
    let resolve!: (w: unknown) => void;
    h.userWorkflowsGet.mockReturnValue(new Promise((r) => (resolve = r)));

    const { container } = mount("/workflows/w1");
    await waitFor(() => expect(h.userWorkflowsGet).toHaveBeenCalledWith("w1"));
    expect(container).toBeEmptyDOMElement();

    await act(async () => resolve(savedWorkflow()));

    expect(await screen.findByRole("heading", { name: "My Flow" })).toBeInTheDocument();
    expect(screen.queryByTestId("dashboard-layout")).not.toBeInTheDocument();
  });

  it.each([403, 404])("renders not-found when the workflow fetch fails with %i", async (status) => {
    h.userWorkflowsGet.mockRejectedValue(new ApiError(status, "nope"));

    mount("/workflows/w1");

    expect(await screen.findByRole("alert")).toHaveTextContent("not-found");
  });

  it("stays blank, without not-found, on a transient server error", async () => {
    h.userWorkflowsGet.mockRejectedValue(new ApiError(500, "down"));

    const { container } = mount("/workflows/w1");

    await waitFor(() => expect(consoleError).toHaveBeenCalled());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(container).toBeEmptyDOMElement();
  });

  it("hands an expired session to the shared session-expiry handler", async () => {
    h.userWorkflowsGet.mockRejectedValue(new ApiError(401, "expired"));

    mount("/workflows/w1");

    await waitFor(() => expect(h.api.handleSessionExpiry).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

// --- /workflows/{id}/edit

describe("DashboardPage saved-workflow edit route", () => {
  it("seeds the composer with the fetched workflow", async () => {
    h.userWorkflowsGet.mockResolvedValue(savedWorkflow());

    mount("/workflows/w1/edit");

    await waitFor(() => expect(props()?.initialSavedComposition).toBeTruthy());
    expect(h.userWorkflowsGet).toHaveBeenCalledWith("w1");
    expect(props().initialMainView).toBe("composer");
    expect(props().initialSavedComposition).toEqual(
      expect.objectContaining({
        id: "w1",
        name: "My Flow",
        description: "does things",
        agentIds: ["a1", "a2"],
        modelOverrides: { a1: "model-x" },
        selections: {},
      }),
    );
  });

  it.each([403, 404])("renders not-found when the edit fetch fails with %i", async (status) => {
    h.userWorkflowsGet.mockRejectedValue(new ApiError(status, "nope"));

    mount("/workflows/w1/edit");

    expect(await screen.findByRole("alert")).toHaveTextContent("not-found");
  });

  it("keeps the empty composer, without not-found, on a transient server error", async () => {
    h.userWorkflowsGet.mockRejectedValue(new ApiError(500, "down"));

    mount("/workflows/w1/edit");
    await untilDashboard();

    await waitFor(() => expect(consoleError).toHaveBeenCalled());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(props().initialSavedComposition).toBeNull();
  });

  it("hands an expired session to the shared session-expiry handler", async () => {
    h.userWorkflowsGet.mockRejectedValue(new ApiError(401, "expired"));

    mount("/workflows/w1/edit");

    await waitFor(() => expect(h.api.handleSessionExpiry).toHaveBeenCalledTimes(1));
  });
});

// --- /workflows/{id}/run

describe("DashboardPage saved-workflow run route", () => {
  it("renders nothing while the base pipeline type is being resolved", async () => {
    h.userWorkflowsGet.mockReturnValue(new Promise(() => {}));

    const { container } = mount("/workflows/w1/run");

    await waitFor(() => expect(h.userWorkflowsGet).toHaveBeenCalledWith("w1"));
    expect(container).toBeEmptyDOMElement();
  });

  it("opens the composer for a custom workflow with its brief and gates prefilled", async () => {
    h.userWorkflowsGet.mockResolvedValue(
      savedWorkflow({ selections: { _wizard: { brief: "Prefilled brief", gateAgentIds: ["g1"] } } }),
    );

    mount("/workflows/w1/run");
    await untilDashboard();

    expect(props().initialMainView).toBe("composer");
    expect(props().initialSavedComposition).toEqual(
      expect.objectContaining({ id: "w1", brief: "Prefilled brief", gateAgentIds: ["g1"], agentIds: ["a1", "a2"] }),
    );
  });

  it("opens the plain launch panel for any other catalog base type", async () => {
    h.userWorkflowsGet.mockResolvedValue(savedWorkflow({ base_pipeline_type: "user_stories" }));

    mount("/workflows/w1/run");
    await untilDashboard();

    expect(props().initialMainView).toBe("input");
  });

  it.each([
    ["ppt", "ppt.draft"],
    ["ppt_v2", "ppt.draft"],
    ["prototype", "prototype.draft"],
    ["prototype_v2", "prototype.draft"],
  ])("renders the %s wizard and stages its draft under %s", async (base, draftKey) => {
    h.userWorkflowsGet.mockResolvedValue(
      savedWorkflow({
        base_pipeline_type: base,
        selections: { _wizard: { templateId: "t1", designSystemId: "ds1", brief: "B" }, extra: { k: 1 } },
      }),
    );

    mount("/workflows/w1/run");

    expect(await screen.findByText(`wizard:${base}`)).toBeInTheDocument();
    expect(JSON.parse(sessionStorage.getItem(draftKey) ?? "null")).toEqual({
      templateId: "t1",
      designSystemId: "ds1",
      brief: "B",
      modelOverrides: { a1: "model-x" },
      selections: { extra: { k: 1 } },
      agentIds: ["a1", "a2"],
      id: "w1",
      name: "My Flow",
      description: "does things",
    });
  });

  it.each([403, 404])("renders not-found when the run-route fetch fails with %i", async (status) => {
    h.userWorkflowsGet.mockRejectedValue(new ApiError(status, "nope"));

    mount("/workflows/w1/run");

    expect(await screen.findByRole("alert")).toHaveTextContent("not-found");
    expect(screen.queryByTestId("dashboard-layout")).not.toBeInTheDocument();
  });

  it("hands an expired session to the shared session-expiry handler", async () => {
    h.userWorkflowsGet.mockRejectedValue(new ApiError(401, "expired"));

    mount("/workflows/w1/run");

    await waitFor(() => expect(h.api.handleSessionExpiry).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

// --- /workflows/{type}/canvas

describe("DashboardPage built-in canvas route", () => {
  it("seeds a copy-only composer from the built-in workflow detail", async () => {
    h.api.getWorkflowDetail.mockResolvedValue({
      name: "Deck",
      description: "Builds decks",
      steps: [{ agent_id: "a1" }, { agent_id: "a2" }],
      manifest_steps: null,
      deliverable: { strategy: "ppt" },
      planner: "run",
      clarify_mode: "auto",
      clarify_defaults: ["d1"],
    });

    mount("/workflows/ppt/canvas");

    await waitFor(() => expect(props()?.initialSavedComposition).toBeTruthy());
    expect(h.api.getWorkflowDetail).toHaveBeenCalledWith("tok", "ppt");
    expect(props().builtinCanvasType).toBe("ppt");
    expect(props().initialWorkflowType).toBe("ppt");
    expect(props().initialMainView).toBe("composer");
    const seed = props().initialSavedComposition!;
    expect(seed).not.toHaveProperty("id");
    expect(seed).toEqual(
      expect.objectContaining({
        agentIds: ["a1", "a2"],
        name: "Deck",
        description: "Builds decks",
        modelOverrides: {},
        selections: {},
        runConfig: {
          deliverable: { strategy: "ppt", name: "output.md" },
          planner: "run",
          clarify: { mode: "auto", defaults: ["d1"] },
        },
      }),
    );
  });

  it("defaults the run config to skip planner and clarify when the manifest declares neither", async () => {
    h.api.getWorkflowDetail.mockResolvedValue({
      name: "Plain",
      description: "",
      steps: [],
      deliverable: { strategy: "single_file", name: "page.html" },
      planner: "other",
      clarify_mode: "other",
    });

    mount("/workflows/plain/canvas");

    await waitFor(() => expect(props()?.initialSavedComposition).toBeTruthy());
    expect(props().initialSavedComposition?.runConfig).toEqual({
      deliverable: { strategy: "single_file", name: "page.html" },
      planner: "skip",
      clarify: { mode: "skip", defaults: [] },
    });
  });

  it.each([403, 404])("renders not-found when the canvas seed fetch fails with %i", async (status) => {
    h.api.getWorkflowDetail.mockRejectedValue(new ApiError(status, "nope"));

    mount("/workflows/ghost/canvas");

    expect(await screen.findByRole("alert")).toHaveTextContent("not-found");
  });

  it("keeps the blank composer, without not-found, on a transient server error", async () => {
    h.api.getWorkflowDetail.mockRejectedValue(new ApiError(500, "down"));

    mount("/workflows/ppt/canvas");
    await untilDashboard();

    await waitFor(() => expect(h.api.getWorkflowDetail).toHaveBeenCalled());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(props().initialSavedComposition).toBeNull();
  });
});

// --- cold-mount run reopen (/runs/{id}*)

describe("DashboardPage run reopen", () => {
  it("fetches the run and its durable events, exposing it as the content source", async () => {
    h.api.getWorkflow.mockResolvedValue(runRecord({ output: "# Stories" }));

    mount("/runs/r1");

    await waitFor(() => expect(props()?.userStoryContent).toBe("# Stories"));
    expect(h.api.getWorkflow).toHaveBeenCalledWith("tok", "r1", false);
    expect(h.api.getRunEvents).toHaveBeenCalledWith("tok", "r1", 0, expect.any(Function));
    expect(props().contentSourceRunId).toBe("r1");
    expect(props().contentSourceRunType).toBe("user_stories");
    expect(props().reopenedRunStatus).toBeUndefined();
    await waitFor(() => expect(props().isLoadingRunData).toBe(false));
  });

  it("marks the run as loading while its record is in flight", async () => {
    h.api.getWorkflow.mockReturnValue(new Promise(() => {}));

    mount("/runs/r1");

    await waitFor(() => expect(props()?.isLoadingRunData).toBe(true));
  });

  it("does not attach a live stream to a terminal run", async () => {
    h.api.getWorkflow.mockResolvedValue(runRecord({ status: "completed" }));

    mount("/runs/r1");
    await waitFor(() => expect(props()?.contentSourceRunId).toBe("r1"));

    expect(h.conn.attachRun).not.toHaveBeenCalled();
  });

  it("attaches the live stream of a run that is still in progress", async () => {
    h.api.getWorkflow.mockResolvedValue(runRecord({ status: "running" }));

    mount("/runs/r1");

    await waitFor(() => expect(h.conn.attachRun).toHaveBeenCalledWith("r1"));
  });

  it("routes a deck run's output to the deck slot", async () => {
    h.api.getWorkflow.mockResolvedValue(runRecord({ type: "ppt_v2", output: "<deck/>" }));

    mount("/runs/r1");

    await waitFor(() => expect(props()?.pptContent).toBe("<deck/>"));
    expect(props().userStoryContent).toBe("");
  });

  it("routes a prototype run's output to the prototype slot", async () => {
    h.api.getWorkflow.mockResolvedValue(runRecord({ type: "prototype_feature_revision", output: "<app/>" }));

    mount("/runs/r1");

    await waitFor(() => expect(props()?.prototypeContent).toBe("<app/>"));
  });

  it("routes an unrecognised run type to the generic deliverable using its persisted mimetype", async () => {
    h.api.getWorkflow.mockResolvedValue(
      runRecord({
        type: "some_custom_flow",
        output: "BASE64ZIP",
        deliverableMimetype: "application/zip",
        deliverableFilename: "bundle.zip",
      }),
    );

    mount("/runs/r1");

    await waitFor(() => expect(props()?.genericDeliverable).toBeDefined());
    expect(props().genericDeliverable).toEqual({
      mimetype: "application/zip",
      filename: "bundle.zip",
      content: "BASE64ZIP",
    });
  });

  it("does not render output for a run that did not complete", async () => {
    h.api.getWorkflow.mockResolvedValue(runRecord({ status: "failed", output: "partial" }));

    mount("/runs/r1");
    await waitFor(() => expect(props()?.reopenedRunStatus).toBe("failed"));

    expect(props().userStoryContent).toBe("");
    expect(props().genericDeliverable).toBeUndefined();
  });

  it("surfaces a failed run's status, failed agent ids and agent names", async () => {
    h.api.getWorkflow.mockResolvedValue(
      runRecord({
        status: "failed",
        error: "2 agent(s) failed: a1, a2",
        agentOutputs: [{ agent_id: "a1", name: "Alpha" }],
      }),
    );

    mount("/runs/r1");

    await waitFor(() => expect(props()?.reopenedRunStatus).toBe("failed"));
    expect(props().reopenedFailedAgents).toEqual(["a1", "a2"]);
    expect(props().reopenedAgentNameById).toEqual({ a1: "Alpha" });
  });

  it("keeps a degraded run's partial deliverable and still flags the degraded status", async () => {
    h.api.getWorkflow.mockResolvedValue(runRecord({ status: "degraded", output: "# Partial" }));

    mount("/runs/r1");

    await waitFor(() => expect(props()?.userStoryContent).toBe("# Partial"));
    expect(props().reopenedRunStatus).toBe("degraded");
  });

  it("seeds the submitted brief from the reopened run's input", async () => {
    h.api.getWorkflow.mockResolvedValue(runRecord({ input: "Build a login page", title: "T" }));

    mount("/runs/r1");

    await waitFor(() => expect(props()?.submittedBrief).toBe("Build a login page"));
  });

  it("falls back to the run title when its input carries no brief", async () => {
    h.api.getWorkflow.mockResolvedValue(runRecord({ input: "", title: "Titled run" }));

    mount("/runs/r1");

    await waitFor(() => expect(props()?.submittedBrief).toBe("Titled run"));
  });

  it("fetches the run record exactly once for a tab route", async () => {
    // A tab route reopens via a `{ id }` stub, so getWorkflow is called once.
    h.api.getWorkflow.mockResolvedValue(runRecord());

    mount("/runs/r1/files");
    await waitFor(() => expect(props()?.contentSourceRunId).toBe("r1"));

    expect(h.api.getWorkflow).toHaveBeenCalledTimes(1);
  });

  it("still opens the run when the durable event replay fails", async () => {
    h.api.getWorkflow.mockResolvedValue(runRecord({ output: "# Stories" }));
    h.api.getRunEvents.mockRejectedValue(new Error("events down"));

    mount("/runs/r1");

    await waitFor(() => expect(props()?.userStoryContent).toBe("# Stories"));
    expect(consoleError).toHaveBeenCalledWith("Failed to seed run trace on open:", expect.any(Error));
  });

  it("does not fetch the run when the token has gone missing", async () => {
    // Auth effect reads the token once, then it disappears before the reopen fetch.
    h.api.getToken.mockReturnValueOnce("tok").mockReturnValue(null);

    mount("/runs/r1");
    await untilDashboard();

    expect(h.api.getWorkflow).not.toHaveBeenCalled();
  });

  it.each([
    ["/runs/r1/audit", "audit", undefined],
    ["/runs/r1/files", "files", undefined],
    ["/runs/r1/workspace", "workspace", undefined],
    ["/runs/r1/steps", "thinking", undefined],
    ["/runs/r1/steps/agent-7", "thinking", "agent-7"],
    ["/runs/r1/preview/full", "preview", undefined],
  ])("deep-links %s to the %s tab once the run has loaded", async (path, tab, agentId) => {
    h.api.getWorkflow.mockResolvedValue(runRecord());

    mount(path);

    await waitFor(() => expect(props()?.deepLinkTarget).toEqual(expect.objectContaining({ tab, agentId })));
    expect(props().initialMainView).toBe("execution");
  });

  it("requests no tab for the bare run-detail route", async () => {
    h.api.getWorkflow.mockResolvedValue(runRecord());

    mount("/runs/r1");
    await waitFor(() => expect(props()?.contentSourceRunId).toBe("r1"));

    expect(props().deepLinkTarget).toBeNull();
  });

  it("threads a pinned version from the path down to the layout", async () => {
    h.api.getWorkflow.mockResolvedValue(runRecord());

    mount("/runs/r1/versions/3/files");
    await untilDashboard();

    expect(props().pinnedVersion).toBe("3");
  });

  it("carries a live run's recents entry type when the run is already attached", async () => {
    h.conn.liveRunIds = ["r1"];
    h.conn.recentRuns = [{ id: "r1", type: "ppt", status: "running" }];
    h.api.getWorkflow.mockResolvedValue(runRecord({ type: "ppt", status: "running" }));

    mount("/runs/r1");

    await waitFor(() => expect(props()?.activePipelineRunId).toBe("r1"));
    expect(props().contentSourceRunType).toBe("ppt");
    expect(h.api.getWorkflow).toHaveBeenCalledWith("tok", "r1", false);
  });
});

// --- run access failure + bounded retry

describe("DashboardPage run access failures", () => {
  /** Settle microtasks and the page's one fake-timer retry (setTimeout only is faked). */
  async function settleThroughRetry() {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1200);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
  }

  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  });

  it("retries once after a 404 and recovers when the second read succeeds", async () => {
    h.api.getWorkflow
      .mockRejectedValueOnce(new ApiError(404, "lag"))
      .mockResolvedValueOnce(runRecord({ output: "# Recovered" }));

    mount("/runs/r1");
    await settleThroughRetry();

    expect(h.api.getWorkflow).toHaveBeenCalledTimes(2);
    expect(props().userStoryContent).toBe("# Recovered");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("does not retry before the retry delay has elapsed", async () => {
    h.api.getWorkflow.mockRejectedValue(new ApiError(404, "lag"));

    mount("/runs/r1");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1199);
    });

    expect(h.api.getWorkflow).toHaveBeenCalledTimes(1);
  });

  it.each([403, 404])("renders not-found when the retry also fails with %i and the run is not live", async (status) => {
    h.api.getWorkflow.mockRejectedValue(new ApiError(status, "denied"));

    mount("/runs/r1");
    await settleThroughRetry();

    expect(h.api.getWorkflow).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("alert")).toHaveTextContent("not-found");
  });

  it("keeps the shell instead of not-found when the failing run is corroborated as live", async () => {
    h.conn.liveRunIds = ["r1"];
    h.api.getWorkflow.mockRejectedValue(new ApiError(404, "lag"));

    mount("/runs/r1");
    await settleThroughRetry();

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByTestId("dashboard-layout")).toBeInTheDocument();
  });

  it("does not retry or deny access on a server error", async () => {
    h.api.getWorkflow.mockRejectedValue(new ApiError(500, "down"));

    mount("/runs/r1");
    await settleThroughRetry();

    expect(h.api.getWorkflow).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(consoleError).toHaveBeenCalledWith("Failed to load workflow output:", expect.any(ApiError));
    expect(props().isLoadingRunData).toBe(false);
  });
});

// --- cold-mount live stream (/runs/{id}/stream)

describe("DashboardPage live stream cold mount", () => {
  it("re-attaches via the record fetch when the run is not already live", async () => {
    h.api.getWorkflow.mockResolvedValue(runRecord({ status: "running" }));

    mount("/runs/r1/stream");

    await waitFor(() => expect(h.conn.attachRun).toHaveBeenCalledWith("r1"));
    expect(h.api.getWorkflow).toHaveBeenCalledWith("tok", "r1", false);
    expect(props().initialMainView).toBe("execution");
  });

  it("restores a live run from the persisted launch state without refetching the record", async () => {
    h.conn.liveRunIds = ["r1"];
    h.conn.recentRuns = [{ id: "r1", type: "ppt", status: "running" }];
    sessionStorage.setItem("run_brief:r1", "Launch brief");

    mount("/runs/r1/stream");

    await waitFor(() => expect(props()?.submittedBrief).toBe("Launch brief"));
    expect(h.api.getWorkflow).not.toHaveBeenCalled();
    expect(h.api.getRunEvents).toHaveBeenCalledWith("tok", "r1");
    expect(props().contentSourceRunId).toBe("r1");
    expect(props().activePipelineRunId).toBe("r1");
    expect(props().contentSourceRunType).toBe("ppt");
  });

  it("prefers the run type persisted at launch over the recents entry", async () => {
    h.conn.liveRunIds = ["r1"];
    h.conn.recentRuns = [{ id: "r1", type: "ppt", status: "running" }];
    sessionStorage.setItem("run_type:r1", "prototype");

    mount("/runs/r1/stream");

    await waitFor(() => expect(props()?.contentSourceRunType).toBe("prototype"));
  });

  it("keeps the shell and logs when the replay after remount fails", async () => {
    h.conn.liveRunIds = ["r1"];
    h.api.getRunEvents.mockRejectedValue(new Error("replay down"));

    mount("/runs/r1/stream");

    await waitFor(() =>
      expect(consoleError).toHaveBeenCalledWith("durable replay after remount failed:", "r1", expect.any(Error)),
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("seeds the brief from a live run's revision instruction when the family has members", async () => {
    h.conn.liveRunIds = ["r1"];
    h.conn.recentRuns = [{ id: "r1", type: "ppt", status: "running", input: "Make it shorter" }];
    h.api.getRunFamily.mockResolvedValue({ members: [{ id: "r1" }] });

    mount("/runs/r1/stream");

    await waitFor(() => expect(props()?.submittedBrief).toBe("Make it shorter"));
  });
});

// --- callbacks handed to the layout

describe("DashboardPage layout callbacks", () => {
  it("revokes the token, signs out and returns to login on logout", async () => {
    const user = userEvent.setup();
    mount("/dashboard");
    await untilDashboard();

    await user.click(screen.getByRole("button", { name: "Log out" }));

    await waitFor(() => expect(h.router.replace).toHaveBeenCalledWith("/login"));
    expect(h.api.logout).toHaveBeenCalledWith("tok");
    expect(h.dispatch).toHaveBeenCalledWith(signedOut());
  });

  it.each([
    [
      "Approve gate",
      { gate_key: "g1", action: "approve", approved: true, edited_content: "edited text" },
    ],
    ["Reject gate", { gate_key: "g1", action: "reject", approved: false }],
    ["Redo gate", { gate_key: "g1", action: "redo", instructions: "tighten it" }],
    ["Update specs", { gate_key: "g1", action: "update_specs", analysis_report: "report" }],
  ])("posts the %s decision to the gate endpoint", async (label, body) => {
    const user = userEvent.setup();
    mount("/dashboard");
    await untilDashboard();

    await user.click(screen.getByRole("button", { name: label }));

    expect(h.api.postGate).toHaveBeenCalledWith("tok", "", body);
  });

  it("logs, without throwing, when a gate decision fails to post", async () => {
    const user = userEvent.setup();
    h.api.postGate.mockRejectedValue(new Error("gate down"));
    mount("/dashboard");
    await untilDashboard();

    await user.click(screen.getByRole("button", { name: "Approve gate" }));

    await waitFor(() => expect(consoleError).toHaveBeenCalledWith("postGate approve failed", expect.any(Error)));
    expect(screen.getByTestId("dashboard-layout")).toBeInTheDocument();
  });

  it("loads a chat session's messages, stripping the embedded steps comment", async () => {
    const user = userEvent.setup();
    h.api.getChat.mockResolvedValue({
      messages: [
        { id: "m1", chat_session_id: "c1", role: "user", content: "Hello", created_at: "2025-01-01T00:00:00Z" },
        {
          id: "m2",
          chat_session_id: "c1",
          role: "assistant",
          content: '<!--steps:[{"id":"s1"}]-->Answer',
          created_at: "2025-01-01T00:00:01Z",
        },
      ],
      final_output: null,
    });
    mount("/dashboard");
    await untilDashboard();

    await user.click(screen.getByRole("button", { name: "Select chat" }));

    await waitFor(() => expect(props().messages).toHaveLength(2));
    expect(h.api.getChat).toHaveBeenCalledWith("tok", "c1");
    expect(props().activeChatId).toBe("c1");
    expect(props().messages[0]).toEqual(expect.objectContaining({ id: "m1", role: "user", content: "Hello" }));
    expect(props().messages[1]).toEqual(
      expect.objectContaining({ id: "m2", content: "Answer", steps: [{ id: "s1" }] }),
    );
  });

  it("restores a chat's saved final output into the matching content slots", async () => {
    const user = userEvent.setup();
    h.api.getChat.mockResolvedValue({ messages: [], final_output: JSON.stringify({ ppt: "deck", prototype: "app" }) });
    mount("/dashboard");
    await untilDashboard();

    await user.click(screen.getByRole("button", { name: "Select chat" }));

    await waitFor(() => expect(props().pptContent).toBe('"deck"'));
    expect(props().prototypeContent).toBe('"app"');
    expect(props().userStoryContent).toBe("");
  });

  it("logs, and keeps the shell, when a chat session cannot be loaded", async () => {
    const user = userEvent.setup();
    h.api.getChat.mockRejectedValue(new Error("chat down"));
    mount("/dashboard");
    await untilDashboard();

    await user.click(screen.getByRole("button", { name: "Select chat" }));

    await waitFor(() => expect(consoleError).toHaveBeenCalledWith("Failed to load chat:", expect.any(Error)));
    expect(screen.getByTestId("dashboard-layout")).toBeInTheDocument();
  });

  it("deletes the active chat and clears the conversation it was showing", async () => {
    const user = userEvent.setup();
    h.api.getChat.mockResolvedValue({ messages: [{ id: "m1", chat_session_id: "c1", role: "user", content: "Hi", created_at: "t" }], final_output: null });
    mount("/dashboard");
    await untilDashboard();
    await user.click(screen.getByRole("button", { name: "Select chat" }));
    await waitFor(() => expect(props().messages).toHaveLength(1));

    await user.click(screen.getByRole("button", { name: "Delete chat" }));

    await waitFor(() => expect(props().activeChatId).toBeNull());
    expect(h.api.deleteChat).toHaveBeenCalledWith("tok", "c1");
    expect(props().messages).toEqual([]);
  });

  it("logs a failed chat deletion but still clears the active conversation", async () => {
    const user = userEvent.setup();
    h.api.deleteChat.mockRejectedValue(new Error("delete down"));
    h.api.getChat.mockResolvedValue({ messages: [], final_output: null });
    mount("/dashboard");
    await untilDashboard();
    await user.click(screen.getByRole("button", { name: "Select chat" }));
    await waitFor(() => expect(props().activeChatId).toBe("c1"));

    await user.click(screen.getByRole("button", { name: "Delete chat" }));

    await waitFor(() => expect(consoleError).toHaveBeenCalledWith("Failed to delete chat:", expect.any(Error)));
    await waitFor(() => expect(props().activeChatId).toBeNull());
  });

  it("keeps the active chat when a different chat is deleted", async () => {
    const user = userEvent.setup();
    h.api.getChat.mockResolvedValue({ messages: [], final_output: null });
    mount("/dashboard");
    await untilDashboard();
    await act(async () => {
      await props().onDeleteChat("other-chat");
    });

    expect(h.api.deleteChat).toHaveBeenCalledWith("tok", "other-chat");
    expect(props().activeChatId).toBeNull();
    // selecting then deleting a DIFFERENT chat must not clear the selected one
    await user.click(screen.getByRole("button", { name: "Select chat" }));
    await waitFor(() => expect(props().activeChatId).toBe("c1"));
    await act(async () => {
      await props().onDeleteChat("other-chat");
    });
    expect(props().activeChatId).toBe("c1");
  });

  it("switches the viewport to a live run from recents: attach, brief, type and replay", async () => {
    const user = userEvent.setup();
    h.conn.recentRuns = [
      { id: "r2", type: "ppt", status: "running", input: "Q3 board deck", title: "Deck", agentCount: 4 },
    ];
    mount("/dashboard");
    await untilDashboard();

    await user.click(screen.getByRole("button", { name: "Switch live" }));

    await waitFor(() => expect(props().contentSourceRunId).toBe("r2"));
    expect(h.conn.attachRun).toHaveBeenCalledWith("r2");
    expect(h.api.getRunEvents).toHaveBeenCalledWith("tok", "r2");
    expect(props().contentSourceRunType).toBe("ppt");
    expect(props().activePipelineRunId).toBe("r2");
    expect(props().submittedBrief).toBe("Q3 board deck");
    expect(JSON.parse(sessionStorage.getItem("tab_launched_run_ids") ?? "[]")).toContain("r2");
  });

  it("falls back to the run title for the brief when the recents entry has no input", async () => {
    const user = userEvent.setup();
    h.conn.recentRuns = [{ id: "r2", type: "ppt", status: "running", title: "Only a title" }];
    mount("/dashboard");
    await untilDashboard();

    await user.click(screen.getByRole("button", { name: "Switch live" }));

    await waitFor(() => expect(props().submittedBrief).toBe("Only a title"));
  });

  it("still switches to a live run that is not in recents, tolerating a failed replay", async () => {
    const user = userEvent.setup();
    h.api.getRunEvents.mockRejectedValue(new Error("replay down"));
    mount("/dashboard");
    await untilDashboard();

    await user.click(screen.getByRole("button", { name: "Switch live" }));

    await waitFor(() => expect(props().contentSourceRunId).toBe("r2"));
    expect(h.conn.attachRun).toHaveBeenCalledWith("r2");
    expect(props().contentSourceRunType).toBeNull();
  });

  it("tracks a launched revision, attaches its stream and navigates to its stream URL", async () => {
    const user = userEvent.setup();
    mount("/dashboard");
    await untilDashboard();

    await user.click(screen.getByRole("button", { name: "Revision launched" }));

    expect(h.conn.attachRun).toHaveBeenCalledWith("rev1");
    expect(h.router.push).toHaveBeenCalledWith("/runs/rev1/stream");
    expect(JSON.parse(sessionStorage.getItem("tab_launched_run_ids") ?? "[]")).toContain("rev1");
  });

  it("restores the launched-run allow-list persisted by an earlier mount of the same tab", async () => {
    const user = userEvent.setup();
    sessionStorage.setItem("tab_launched_run_ids", JSON.stringify(["old-run"]));
    mount("/dashboard");
    await untilDashboard();

    await user.click(screen.getByRole("button", { name: "Revision launched" }));

    expect(JSON.parse(sessionStorage.getItem("tab_launched_run_ids") ?? "[]")).toEqual(["old-run", "rev1"]);
  });
});

// --- launching a pipeline

describe("DashboardPage pipeline launch", () => {
  it("posts the run, attaches its stream, persists brief and type, and refreshes recents", async () => {
    const user = userEvent.setup();
    const freshRuns = [{ id: "new-run", status: "running" }];
    h.conn.sendCommand.mockResolvedValue("new-run");
    h.api.getWorkflows.mockResolvedValue({ runs: freshRuns });
    mount("/dashboard");
    await untilDashboard();

    await user.click(screen.getByRole("button", { name: "Start run" }));

    await waitFor(() => expect(h.conn.attachRun).toHaveBeenCalledWith("new-run"));
    expect(h.conn.sendCommand).toHaveBeenCalledWith(null, {
      type: "run_pipeline",
      pipeline_type: "user_stories",
      message: "Write stories",
    });
    expect(sessionStorage.getItem("run_brief:new-run")).toBe("Write stories");
    expect(sessionStorage.getItem("run_type:new-run")).toBe("user_stories");
    expect(JSON.parse(sessionStorage.getItem("tab_launched_run_ids") ?? "[]")).toContain("new-run");
    await waitFor(() => expect(h.conn.setRecentRuns).toHaveBeenCalledWith(freshRuns));
    expect(h.api.getWorkflows).toHaveBeenCalledWith("tok", { limit: 50 });
    expect(props().submittedBrief).toBe("Write stories");
  });

  it("does not attach or persist anything when the launch resolves without a run id", async () => {
    const user = userEvent.setup();
    h.conn.sendCommand.mockResolvedValue(null);
    mount("/dashboard");
    await untilDashboard();

    await user.click(screen.getByRole("button", { name: "Start run" }));

    await waitFor(() => expect(h.conn.sendCommand).toHaveBeenCalled());
    expect(h.conn.attachRun).not.toHaveBeenCalled();
    expect(sessionStorage.getItem("tab_launched_run_ids")).toBeNull();
  });

  it("logs and recovers the local state when the launch request is rejected", async () => {
    const user = userEvent.setup();
    h.conn.sendCommand.mockRejectedValue(new ApiError(503, "busy"));
    mount("/dashboard");
    await untilDashboard();

    await user.click(screen.getByRole("button", { name: "Start run" }));

    await waitFor(() => expect(consoleWarn).toHaveBeenCalledWith("Pipeline launch failed:", expect.any(ApiError)));
    expect(h.conn.attachRun).not.toHaveBeenCalled();
  });
});

// --- subscriptions + cleanup

describe("DashboardPage SSE subscriptions", () => {
  it("subscribes to the run fan-out and releases every subscription on unmount", async () => {
    const unsubscribe = vi.fn();
    h.conn.subscribe.mockImplementation(() => unsubscribe);
    const { unmount } = mount("/dashboard");
    await untilDashboard();
    expect(h.conn.subscribe).toHaveBeenCalled();
    expect(unsubscribe).not.toHaveBeenCalled();

    unmount();

    expect(unsubscribe).toHaveBeenCalled();
  });
});

// --- transcript seeding from the revision family -----------------------------

describe("DashboardPage run transcript seeding", () => {
  const chat = (id: string, text: string, type = "chat_reply") => ({
    type,
    data: { event_id: `e-${id}`, message_id: `m-${id}`, text },
  });

  /** getRunEvents keyed by run id; any other id resolves empty. */
  function eventsByRun(byRun: Record<string, unknown[] | Error>) {
    h.api.getRunEvents.mockImplementation(async (_tok: string, runId: string) => {
      const v = byRun[runId];
      if (v instanceof Error) throw v;
      return v ?? [];
    });
  }

  const texts = () => props().runChatMessages?.map((m) => m.content);

  it("seeds a reopened run's transcript in family order: earlier runs, itself, then later runs", async () => {
    h.api.getWorkflow.mockResolvedValue(runRecord({ id: "r1" }));
    h.api.getRunFamily.mockResolvedValue({ members: [{ id: "r0" }, { id: "r1" }, { id: "r2" }] });
    eventsByRun({
      r0: [chat("0", "First"), { type: "agent_chunk", data: { event_id: "noise" } }],
      r1: [chat("1", "Mine")],
      r2: [chat("2", "Later")],
    });

    mount("/runs/r1");

    await waitFor(() => expect(texts()).toEqual(["First", "Mine", "Later"]));
  });

  it("still seeds the opened run's own transcript when a sibling's events fail to load", async () => {
    h.api.getWorkflow.mockResolvedValue(runRecord({ id: "r1" }));
    h.api.getRunFamily.mockResolvedValue({ members: [{ id: "r0" }, { id: "r1" }] });
    eventsByRun({ r0: new Error("sibling down"), r1: [chat("1", "Mine")] });

    mount("/runs/r1");

    await waitFor(() => expect(texts()).toEqual(["Mine"]));
  });

  it("falls back to the opened run's own transcript when the family cannot be fetched", async () => {
    h.api.getWorkflow.mockResolvedValue(runRecord({ id: "r1" }));
    h.api.getRunFamily.mockRejectedValue(new Error("family down"));
    eventsByRun({ r1: [chat("1", "Mine")] });

    mount("/runs/r1");

    await waitFor(() => expect(texts()).toEqual(["Mine"]));
  });

  it("seeds a live remounted run from the chat frames of every family member", async () => {
    h.conn.liveRunIds = ["r1"];
    h.api.getRunFamily.mockResolvedValue({ members: [{ id: "r0" }, { id: "r1" }] });
    eventsByRun({ r0: [chat("0", "Parent")], r1: [chat("1", "Revision started")] });

    mount("/runs/r1/stream");

    await waitFor(() => expect(texts()).toEqual(["Parent", "Revision started"]));
  });

  it("seeds a live remounted run from its own chat frames when it has no family", async () => {
    h.conn.liveRunIds = ["r1"];
    h.api.getRunFamily.mockResolvedValue({ members: [] });
    eventsByRun({ r1: [chat("1", "Only me"), { type: "agent_chunk", data: { event_id: "noise" } }] });

    mount("/runs/r1/stream");

    await waitFor(() => expect(texts()).toEqual(["Only me"]));
  });

  it("seeds a live remounted run from its own chat frames when the family fetch fails", async () => {
    h.conn.liveRunIds = ["r1"];
    h.api.getRunFamily.mockRejectedValue(new Error("family down"));
    eventsByRun({ r1: [chat("1", "Only me")] });

    mount("/runs/r1/stream");

    await waitFor(() => expect(texts()).toEqual(["Only me"]));
  });
});