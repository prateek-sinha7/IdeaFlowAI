/**
 * Coverage-gap behavior tests for the `[...view]` catch-all page (`page.tsx`).
 *
 * `page.coldMount.test.tsx` owns cold-mount routing and `page.frameRouting.test.tsx`
 * owns SSE frame routing. This file closes the gaps a folder-scoped V8 run measured
 * after those suites: shallow run-tab navigation on an already-open run, the brief a
 * launch displays, revision-vs-fresh launch content, the launch-window pipeline_start
 * registration, gate decisions against an OPEN gate, the legacy stream/complete
 * frames, a strategy-less canvas seed, and a token-less chat delete.
 *
 * The page's route helpers (`reopenTabFor`, `pinnedVersionFor`, `deepLinkAgentIdFor`,
 * ...) are module-private, so they are exercised through the props the page hands
 * to `DashboardLayout` (a props-capturing stub). Boundaries mocked: `next/navigation`,
 * `@/lib/api` (`ApiError` stays real), `@/store/hooks`, and the SSE connection
 * provider. `useWorkflow`, `useRunStateStore`, `useRunChat`, `useTabDeepLink`,
 * `parseViewPath` and `parseRunInput` run for real.
 *
 * The harness is repeated rather than shared: `vi.mock` factories are hoisted per
 * file and cannot be imported.
 */
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { DashboardLayoutProps } from "@/components/layout/DashboardLayout";
import type { WorkflowRun } from "@/types/index";

import DashboardPage from "./page";

// --- hoisted boundary doubles

const h = vi.hoisted(() => {
  const nav = { pathname: "/dashboard" };
  const router = { replace: vi.fn(), push: vi.fn(), back: vi.fn(), prefetch: vi.fn(), refresh: vi.fn(), forward: vi.fn() };
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
  const subscribers = new Set<(m: unknown) => void>();
  const conn = {
    enabled: true,
    phase: "idle" as string,
    liveRunIds: [] as string[],
    reattach: vi.fn(),
    attachRun: vi.fn(),
    detachRun: vi.fn(),
    subscribe: vi.fn(),
    sendCommand: vi.fn(),
    recentRuns: [] as unknown[],
    recentRunsLoaded: true,
    setRecentRuns: vi.fn(),
    loadRecentRuns: vi.fn(),
  };
  const layout = { props: null as unknown as DashboardLayoutProps };
  return { nav, router, api, conn, subscribers, layout };
});

vi.mock("next/navigation", () => ({
  useRouter: () => h.router,
  usePathname: () => h.nav.pathname,
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
}));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), ...h.api }));
vi.mock("@/store/hooks", () => ({ useAppDispatch: () => vi.fn() }));
vi.mock("@/providers/RunConnectionProvider", () => ({ useRunConnection: () => h.conn }));
vi.mock("@/components/layout/DashboardLayout", () => ({
  DashboardLayout: (props: DashboardLayoutProps) => {
    h.layout.props = props;
    // data-testid: stub shell with no semantic landmark of its own.
    return <div data-testid="dashboard-layout" />;
  },
}));

// --- helpers

const props = () => h.layout.props as Required<DashboardLayoutProps>;

interface Frame {
  type: string;
  data?: Record<string, unknown>;
  /** Run the frame arrived on, as stamped by the SSE transport. */
  from?: string;
}

/** Push frames through every fan-out subscriber, the way the SSE provider does. */
async function emit(...frames: Frame[]) {
  for (const f of frames) {
    await act(async () => {
      for (const fn of [...h.subscribers]) fn({ type: f.type, data: f.data, _sourceRunId: f.from });
    });
  }
}

function mount(pathname: string) {
  h.nav.pathname = pathname;
  return render(<DashboardPage />);
}

/** Move the mounted page to a new path without remounting (a shallow pushState). */
function navigateShallow(view: ReturnType<typeof mount>, pathname: string) {
  h.nav.pathname = pathname;
  view.rerender(<DashboardPage />);
}

/** Mount the live-stream route for `r1` as the tab that launched it and already tracks it. */
async function mountTrackingR1() {
  sessionStorage.setItem("tab_launched_run_ids", JSON.stringify(["r1"]));
  h.conn.liveRunIds = ["r1"];
  mount("/runs/r1/stream");
  await screen.findByTestId("dashboard-layout");
  await waitFor(() => expect(props().contentSourceRunId).toBe("r1"));
  await waitFor(() => expect(h.subscribers.size).toBeGreaterThan(0));
}

/** Invoke the launch callback the page hands the layout, as the launch panel does. */
async function launch(type: string, message: string, extraParams?: Record<string, unknown>) {
  await act(async () => {
    props().onStartPipeline(type, message, undefined, undefined, extraParams);
  });
}

/** A full run record shaped like `getWorkflow` returns it. */
function runRecord(overrides: Record<string, unknown> = {}): WorkflowRun {
  return {
    id: "r1",
    status: "completed",
    type: "user_stories",
    input: "Write stories",
    title: "Stories run",
    output: "# Stories",
    agentCount: 1,
    agentOutputs: [],
    error: undefined,
    ...overrides,
  } as unknown as WorkflowRun;
}

/** A structurally valid JWT whose `sub` is unique per test, so the module-scope run store (keyed by account) starts empty. */
function makeJwt(sub: string): string {
  const b64 = (o: object) => btoa(JSON.stringify(o)).replace(/=+$/, "").replace(/\+/g, "-").replace(/\//g, "_");
  return `${b64({ alg: "none" })}.${b64({ sub })}.sig`;
}

const launchedIds = () => JSON.parse(sessionStorage.getItem("tab_launched_run_ids") ?? "null") as string[] | null;

let token = "";
let testCounter = 0;
let consoleError: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  vi.clearAllMocks();
  token = makeJwt(`page-gap-user-${++testCounter}`);
  sessionStorage.clear();
  h.subscribers.clear();
  h.nav.pathname = "/dashboard";
  h.layout.props = null as unknown as DashboardLayoutProps;
  h.conn.phase = "idle";
  h.conn.liveRunIds = [];
  h.conn.recentRuns = [];
  h.conn.subscribe.mockImplementation((fn: (m: unknown) => void) => {
    h.subscribers.add(fn);
    return () => {
      h.subscribers.delete(fn);
    };
  });
  h.conn.sendCommand.mockResolvedValue(null);
  h.api.getToken.mockReturnValue(token);
  h.api.getMe.mockResolvedValue({ id: "u1", email: "ada@example.com", tier: "basic", is_admin: false });
  h.api.logout.mockResolvedValue(undefined);
  h.api.getWorkflows.mockResolvedValue({ runs: [] });
  h.api.getWorkflow.mockResolvedValue(runRecord());
  h.api.getRunEvents.mockResolvedValue([]);
  h.api.getRunFamily.mockResolvedValue({ members: [] });
  h.api.postGate.mockResolvedValue(undefined);
  h.api.deleteChat.mockResolvedValue(undefined);
  consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// --- shallow tab navigation on an already-open run

describe("DashboardPage shallow run-tab navigation", () => {
  it.each([
    ["/runs/r1/audit", "audit", undefined],
    ["/runs/r1/files", "files", undefined],
    ["/runs/r1/workspace", "workspace", undefined],
    ["/runs/r1/steps", "thinking", undefined],
    ["/runs/r1/steps/agent-7", "thinking", "agent-7"],
    ["/runs/r1/preview/full", "preview", undefined],
  ])("requests the tab for %s without refetching the open run", async (path, tab, agentId) => {
    const view = mount("/runs/r1");
    await waitFor(() => expect(props()?.contentSourceRunId).toBe("r1"));
    expect(props().deepLinkTarget).toBeNull();

    navigateShallow(view, path);

    await waitFor(() => expect(props().deepLinkTarget).toEqual(expect.objectContaining({ tab, agentId })));
    expect(h.api.getWorkflow).toHaveBeenCalledTimes(1);
  });

  it("requests the preview tab when the path returns to the bare run route", async () => {
    const view = mount("/runs/r1/files");
    await waitFor(() => expect(props()?.deepLinkTarget).toEqual(expect.objectContaining({ tab: "files" })));

    navigateShallow(view, "/runs/r1");

    await waitFor(() => expect(props().deepLinkTarget).toEqual(expect.objectContaining({ tab: "preview" })));
    expect(h.api.getWorkflow).toHaveBeenCalledTimes(1);
  });

  it("requests no tab when the path moves to a pinned version of the open run", async () => {
    const view = mount("/runs/r1");
    await waitFor(() => expect(props()?.contentSourceRunId).toBe("r1"));

    navigateShallow(view, "/runs/r1/versions/2");

    await waitFor(() => expect(props().pinnedVersion).toBe("2"));
    expect(props().deepLinkTarget).toBeNull();
    expect(h.api.getWorkflow).toHaveBeenCalledTimes(1);
  });
});

// --- the brief a launch displays

describe("DashboardPage launch brief", () => {
  it("shows the launcher's display title as the brief when one is supplied", async () => {
    mount("/dashboard");
    await screen.findByTestId("dashboard-layout");

    await launch("user_stories", "=== REVISION REQUEST ===\nIgnored\n=== END REQUEST ===", { _display_title: "  Clean title  " });

    await waitFor(() => expect(props().submittedBrief).toBe("Clean title"));
  });

  it("shows the revision instruction as the brief when the message carries one", async () => {
    mount("/dashboard");
    await screen.findByTestId("dashboard-layout");

    await launch("user_stories", "=== REVISION REQUEST ===\nMake it blue\n=== END REQUEST ===", { _display_title: "   " });

    await waitFor(() => expect(props().submittedBrief).toBe("Make it blue"));
  });

  it("shows the original brief from a chain-context-only message", async () => {
    mount("/dashboard");
    await screen.findByTestId("dashboard-layout");

    await launch(
      "ppt",
      "=== CONTEXT FROM PREVIOUS PIPELINE (user_stories) ===\nOriginal Brief: Launch deck\nStories: ...\n=== END PREVIOUS CONTEXT ===",
    );

    await waitFor(() => expect(props().submittedBrief).toBe("Launch deck"));
  });

  it("leaves the brief blank when a chain-context-only message names no original brief", async () => {
    mount("/dashboard");
    await screen.findByTestId("dashboard-layout");
    await launch("user_stories", "Seed brief");
    await waitFor(() => expect(props().submittedBrief).toBe("Seed brief"));

    await launch("ppt", "=== CONTEXT FROM PREVIOUS PIPELINE (user_stories) ===\nStories only\n=== END PREVIOUS CONTEXT ===");

    await waitFor(() => expect(props().submittedBrief).toBe(""));
  });

  it("leaves the brief blank when the message is empty", async () => {
    mount("/dashboard");
    await screen.findByTestId("dashboard-layout");
    await launch("user_stories", "Seed brief");
    await waitFor(() => expect(props().submittedBrief).toBe("Seed brief"));

    await launch("user_stories", "");

    await waitFor(() => expect(props().submittedBrief).toBe(""));
  });
});

// --- revision vs fresh launch on an open run

describe("DashboardPage launch over an open run", () => {
  async function mountOpenRun() {
    mount("/runs/r1");
    await waitFor(() => expect(props()?.userStoryContent).toBe("# Stories"));
    expect(props().contentSourceRunId).toBe("r1");
  }

  it("keeps the open run's output and content source when a revision launches", async () => {
    await mountOpenRun();

    await launch("user_stories_revision", "=== REVISION REQUEST ===\nShorter\n=== END REQUEST ===");

    await waitFor(() => expect(props().submittedBrief).toBe("Shorter"));
    expect(h.conn.sendCommand).toHaveBeenCalledWith(null, expect.objectContaining({ pipeline_type: "user_stories_revision" }));
    expect(props().userStoryContent).toBe("# Stories");
    expect(props().contentSourceRunId).toBe("r1");
  });

  it("clears the open run's output and content source when a fresh run launches", async () => {
    await mountOpenRun();

    await launch("user_stories", "A new idea");

    await waitFor(() => expect(props().submittedBrief).toBe("A new idea"));
    expect(props().userStoryContent).toBe("");
    expect(props().contentSourceRunId).toBeNull();
  });
});

// --- pipeline_start while a launch POST is still in flight

describe("DashboardPage launch window", () => {
  async function mountWithPendingLaunch() {
    sessionStorage.setItem("tab_launched_run_ids", JSON.stringify(["old"]));
    h.conn.sendCommand.mockReturnValue(new Promise(() => {}));
    mount("/dashboard");
    await screen.findByTestId("dashboard-layout");
    await waitFor(() => expect(h.subscribers.size).toBeGreaterThan(0));
    await launch("user_stories", "Write stories");
  }

  it("registers a run announced during the launch window before its POST resolves", async () => {
    await mountWithPendingLaunch();

    await emit({ type: "pipeline_start", from: "r5", data: { pipeline_run_id: "r5", pipeline_type: "user_stories", agents: [] } });

    expect(launchedIds()).toEqual(["old", "r5"]);
    expect(props().backgroundStartedRunId).toBeNull();
  });

  it("treats a previously launched run's pipeline_start as background during the launch window", async () => {
    await mountWithPendingLaunch();

    await emit({ type: "pipeline_start", from: "old", data: { pipeline_run_id: "old", pipeline_type: "user_stories", agents: [] } });

    await waitFor(() => expect(props().backgroundStartedRunId).toBe("old"));
    expect(launchedIds()).toEqual(["old"]);
  });
});

// --- gate decisions on an OPEN gate

describe("DashboardPage decisions on an open review gate", () => {
  const GATE = { pipeline_run_id: "r1", gate_key: "g1", agent_id: "a1", agent_name: "Alpha", output: "Draft output" };

  async function mountWithOpenGate() {
    await mountTrackingR1();
    await emit({ type: "review_gate_ready", from: "r1", data: GATE });
    await waitFor(() => expect(props().reviewGateData).not.toBeNull());
  }

  it("posts an approval against the open gate's run and closes the gate", async () => {
    await mountWithOpenGate();

    await act(async () => props().onApproveReview("g1"));

    expect(h.api.postGate).toHaveBeenCalledWith(token, "r1", {
      gate_key: "g1",
      action: "approve",
      approved: true,
      edited_content: null,
    });
    await waitFor(() => expect(props().reviewGateData).toBeNull());
  });

  it.each([
    ["reject", (p: Required<DashboardLayoutProps>) => p.onRejectReview("g1"), { gate_key: "g1", action: "reject", approved: false }],
    ["redo", (p: Required<DashboardLayoutProps>) => p.onRedoReview("g1", "tighten it"), { gate_key: "g1", action: "redo", instructions: "tighten it" }],
    [
      "update_specs",
      (p: Required<DashboardLayoutProps>) => p.onUpdateSpecsReview("g1", "report"),
      { gate_key: "g1", action: "update_specs", analysis_report: "report" },
    ],
  ])("posts the %s decision against the open gate's run and closes the gate", async (_label, decide, body) => {
    await mountWithOpenGate();

    await act(async () => decide(props()));

    expect(h.api.postGate).toHaveBeenCalledWith(token, "r1", body);
    await waitFor(() => expect(props().reviewGateData).toBeNull());
  });

  it.each([
    ["reject", (p: Required<DashboardLayoutProps>) => p.onRejectReview("g1")],
    ["redo", (p: Required<DashboardLayoutProps>) => p.onRedoReview("g1", "again")],
    ["update_specs", (p: Required<DashboardLayoutProps>) => p.onUpdateSpecsReview("g1", "report")],
  ])("logs, without throwing, when a %s decision fails to post", async (action, decide) => {
    const failure = new Error("gate down");
    h.api.postGate.mockRejectedValue(failure);
    await mountWithOpenGate();

    await act(async () => decide(props()));

    await waitFor(() => expect(consoleError).toHaveBeenCalledWith(`postGate ${action} failed`, failure));
    expect(screen.getByTestId("dashboard-layout")).toBeInTheDocument();
  });

  it("applies the approved edit to the gated agent once the server confirms the approval", async () => {
    await mountTrackingR1();
    await emit({
      type: "pipeline_start",
      from: "r1",
      data: {
        pipeline_run_id: "r1",
        pipeline_type: "user_stories",
        agents: [{ id: "a1", name: "Alpha", role: "analyst", icon: "A", order: 0 }],
      },
    });
    await waitFor(() => expect(props().pipelineState.agents).toHaveLength(1));
    await emit({ type: "review_gate_ready", from: "r1", data: GATE });
    await waitFor(() => expect(props().reviewGateData).not.toBeNull());
    await act(async () => props().onApproveReview("g1", "Edited draft"));

    await emit({ type: "review_gate_approved", from: "r1", data: {} });

    await waitFor(() => expect(props().pipelineState.agents[0].output).toBe("Edited draft"));
  });
});

// --- legacy chat stream frames

describe("DashboardPage legacy stream frames", () => {
  it("flags the chat as streaming on a stream frame and stops on complete without adding a message", async () => {
    await mountTrackingR1();
    expect(props().isStreaming).toBe(false);

    await emit({ type: "stream", from: "r1", data: {} });
    await waitFor(() => expect(props().isStreaming).toBe(true));

    await emit({ type: "complete", from: "r1", data: {} });

    await waitFor(() => expect(props().isStreaming).toBe(false));
    expect(props().messages).toEqual([]);
    expect(props().streamingContent).toBe("");
  });
});

// --- built-in canvas without a declared deliverable

describe("DashboardPage built-in canvas seed", () => {
  it("omits the deliverable from the run config when the manifest declares no strategy", async () => {
    h.api.getWorkflowDetail.mockResolvedValue({
      name: "Bare",
      description: "No deliverable",
      steps: [{ agent_id: "a1" }],
      planner: "run",
      clarify_mode: "skip",
    });

    mount("/workflows/bare/canvas");

    await waitFor(() => expect(props()?.initialSavedComposition).toBeTruthy());
    expect(props().initialSavedComposition?.runConfig).toEqual({
      planner: "run",
      clarify: { mode: "skip", defaults: [] },
    });
  });
});

// --- chat delete without a session

describe("DashboardPage chat delete", () => {
  it("sends no delete request when the session token is gone", async () => {
    mount("/dashboard");
    await screen.findByTestId("dashboard-layout");
    h.api.getToken.mockReturnValue(null);

    await act(async () => {
      await props().onDeleteChat("c1");
    });

    expect(h.api.deleteChat).not.toHaveBeenCalled();
  });
});
