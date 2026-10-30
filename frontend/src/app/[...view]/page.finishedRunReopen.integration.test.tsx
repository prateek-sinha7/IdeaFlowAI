/**
 * Finished-run reopen (`/runs/{id}` for a run that is no longer running).
 *
 * Mounts the real `DashboardPage` (real useWorkflow / useRunStateStore / useRunChat)
 * behind the same boundary doubles as `page.coldMount.test.tsx`: `@/lib/api`,
 * `next/navigation`, `@/providers/RunConnectionProvider`, `@/store/hooks`. The
 * DashboardLayout stub records every render's `pipelineState.isRunning`,
 * `isLoadingRunTrace` and agent count, and fetches the run family on
 * `contentSourceRunId` the way the real component does (through `loadRunFamily`
 * when the page hands one down, else `getRunFamily`).
 *
 * `getRunEvents` is page-aware: it pages the run's log 5,000 rows at a time,
 * calls `onPage` per page, honours the type filter, and for a gated run resolves
 * only when the test delivers its pages, so each test controls the order of the
 * event pages against the run record.
 */
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CHAT_EVENT_TYPES, STREAM_DELTA_EVENT_TYPES, type DurableFrame, type RunEventTypeFilter } from "@/lib/api";
import type { DashboardLayoutProps } from "@/components/layout/DashboardLayout";
import type { WorkflowRun } from "@/types/index";

import DashboardPage from "./page";

// --- hoisted boundary doubles

interface RenderSample {
  isRunning: boolean;
  isLoadingRunTrace: boolean | undefined;
  agentCount: number;
}

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
  const layout = { props: null as unknown as DashboardLayoutProps, renders: [] as RenderSample[] };
  return { nav, router, dispatch, api, conn, layout };
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

vi.mock("@/store/hooks", () => ({ useAppDispatch: () => h.dispatch }));

vi.mock("@/providers/RunConnectionProvider", () => ({ useRunConnection: () => h.conn }));

vi.mock("@/components/layout/DashboardLayout", async () => {
  const { useEffect } = await import("react");
  function DashboardLayoutStub(props: DashboardLayoutProps) {
    h.layout.props = props;
    const extra = props as DashboardLayoutProps & {
      loadRunFamily?: (runId: string) => Promise<unknown>;
      isLoadingRunTrace?: boolean;
    };
    h.layout.renders.push({
      isRunning: props.pipelineState?.isRunning === true,
      isLoadingRunTrace: extra.isLoadingRunTrace,
      agentCount: props.pipelineState?.agents?.length ?? 0,
    });
    const runId = props.contentSourceRunId;
    useEffect(() => {
      if (!runId) return;
      const family = extra.loadRunFamily ? extra.loadRunFamily(runId) : h.api.getRunFamily("tok", runId);
      void Promise.resolve(family).catch(() => {});
      // eslint-disable-next-line react-hooks/exhaustive-deps -- mirrors DashboardLayout's family effect, keyed on the run id only
    }, [runId]);
    return <div data-testid="dashboard-layout" />;
  }
  return { DashboardLayout: DashboardLayoutStub };
});

vi.mock("@/components/savedworkflows/WorkflowDetailView", () => ({
  WorkflowDetailView: () => null,
}));

vi.mock("@/components/workflow/LaunchWizard", () => ({
  LaunchWizard: () => null,
}));

// --- durable log doubles

type Frame = DurableFrame;

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (err: unknown) => void;
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (err: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const PAGE_SIZE = 5000;

interface EventsCall {
  runId: string;
  afterSeq: number;
  onPage?: (frames: Frame[]) => void;
  filter?: RunEventTypeFilter;
  pages: Frame[][];
  delivered: number;
  done: Deferred<Frame[]>;
  frames: Frame[];
}

const ev = {
  logs: new Map<string, Frame[]>(),
  gated: new Set<string>(),
  calls: [] as EventsCall[],
};

function applyFilter(frames: Frame[], afterSeq: number, filter?: RunEventTypeFilter): Frame[] {
  return frames.filter((f) => {
    if (((f.data.seq as number) ?? 0) <= afterSeq) return false;
    if (filter?.types && filter.types.length > 0) return filter.types.includes(f.type);
    if (filter?.excludeTypes && filter.excludeTypes.length > 0) return !filter.excludeTypes.includes(f.type);
    return true;
  });
}

function paginate(frames: Frame[]): Frame[][] {
  const pages: Frame[][] = [];
  for (let i = 0; i < frames.length; i += PAGE_SIZE) pages.push(frames.slice(i, i + PAGE_SIZE));
  return pages.length > 0 ? pages : [[]];
}

/** Hand the caller its next page (via onPage); resolves the walk after the last page. */
function deliverPage(call: EventsCall): void {
  if (call.delivered >= call.pages.length) return;
  call.onPage?.(call.pages[call.delivered]);
  call.delivered += 1;
  if (call.delivered === call.pages.length) call.done.resolve(call.frames);
}

function deliverAll(call: EventsCall): void {
  while (call.delivered < call.pages.length) deliverPage(call);
}

function eventsImpl(_tok: string, runId: string, afterSeq = 0, onPage?: (f: Frame[]) => void, filter?: RunEventTypeFilter) {
  const frames = applyFilter(ev.logs.get(runId) ?? [], afterSeq, filter);
  const call: EventsCall = { runId, afterSeq, onPage, filter, pages: paginate(frames), delivered: 0, done: deferred<Frame[]>(), frames };
  ev.calls.push(call);
  if (!ev.gated.has(runId)) deliverAll(call);
  return call.done.promise;
}

const callsFor = (runId: string) => ev.calls.filter((c) => c.runId === runId);

// --- run fixtures

const ROSTER = [
  { id: "p0", name: "Planner", role: "plan", icon: "P", order: 0 },
  { id: "a1", name: "Writer", role: "write", icon: "W", order: 1 },
  { id: "a2", name: "Reviewer", role: "review", icon: "R", order: 2 },
];

interface FinishedLog {
  frames: Frame[];
  agentOutputs: Array<{ agent_id: string; task_id: null; output: string; thinking_text: string }>;
  expected: Record<string, { output: string; thinkingText: string }>;
}

/**
 * A finished user-stories run of exactly 6,200 rows: a planner step streams 5,040
 * chunks first, so both real steps start after seq 5,000 (on the second page of an
 * unfiltered walk). `openLastPass` leaves a2's last pass without agent_complete.
 */
function finishedLog(runId = "r1", { openLastPass = false } = {}): FinishedLog {
  const frames: Frame[] = [];
  let seq = 0;
  const f = (type: string, data: Record<string, unknown> = {}) => {
    seq += 1;
    frames.push({ type, data: { event_id: `${runId}-e${seq}`, seq, ...data } });
  };
  const text = { p0: "", a1: "", a2: "" };
  let a1Thinking = "";
  f("chat_message", { text: "Write stories" });
  f("pipeline_start", { pipeline_run_id: runId, pipeline_type: "user_stories", agents: ROSTER });
  f("agent_start", { agent_id: "p0" });
  for (let i = 0; i < 5040; i++) {
    f("agent_chunk", { agent_id: "p0", chunk: "x" });
    text.p0 += "x";
  }
  f("agent_complete", { agent_id: "p0" });
  f("agent_start", { agent_id: "a1" });
  for (let i = 0; i < 50; i++) {
    f("agent_thinking", { agent_id: "a1", thinking: `t${i};` });
    a1Thinking += `t${i};`;
  }
  for (let i = 0; i < 500; i++) {
    f("agent_chunk", { agent_id: "a1", chunk: `a1-${i};` });
    text.a1 += `a1-${i};`;
  }
  f("agent_complete", { agent_id: "a1" });
  f("agent_start", { agent_id: "a2" });
  for (let i = 0; i < 600; i++) {
    f("agent_chunk", { agent_id: "a2", chunk: `a2-${i};` });
    text.a2 += `a2-${i};`;
  }
  if (!openLastPass) f("agent_complete", { agent_id: "a2" });
  f("pipeline_complete", { pipeline_run_id: runId, pipeline_type: "user_stories", final_output: "# Stories" });
  f("chat_reply", { text: "Delivered" });
  if (!openLastPass) expect(frames).toHaveLength(6200);
  const agentOutputs = [
    { agent_id: "p0", task_id: null, output: text.p0, thinking_text: "" },
    { agent_id: "a1", task_id: null, output: text.a1, thinking_text: a1Thinking },
    ...(openLastPass ? [] : [{ agent_id: "a2", task_id: null, output: text.a2, thinking_text: "" }]),
  ];
  return {
    frames,
    agentOutputs,
    expected: {
      p0: { output: text.p0, thinkingText: "" },
      a1: { output: text.a1, thinkingText: a1Thinking },
      a2: { output: text.a2, thinkingText: "" },
    },
  };
}

function runRecord(overrides: Record<string, unknown> = {}): WorkflowRun {
  return {
    id: "r1",
    status: "completed",
    type: "user_stories",
    input: "Write stories",
    title: "Stories run",
    output: "# Stories",
    agentCount: 3,
    agentOutputs: undefined,
    error: undefined,
    ...overrides,
  } as unknown as WorkflowRun;
}

/** Slim record (`includeHeavy=false`) via a deferred; heavy record resolves at once. */
function serveRecords(slim: Promise<WorkflowRun>, heavy: WorkflowRun) {
  h.api.getWorkflow.mockImplementation((_tok: string, _id: string, includeHeavy?: boolean) =>
    includeHeavy === false ? slim : Promise.resolve(heavy),
  );
}

function mount(pathname: string) {
  h.nav.pathname = pathname;
  return render(<DashboardPage />);
}

const props = () => h.layout.props;
const agent = (id: string) => props()?.pipelineState?.agents.find((a) => a.id === id);

async function untilPrimaryEventsCall(): Promise<EventsCall> {
  await waitFor(() => expect(callsFor("r1").length).toBeGreaterThan(0));
  return callsFor("r1")[0];
}

/** All three steps of the reopened run show their final, done state. */
async function untilStepsSettled() {
  await waitFor(
    () => {
      expect(agent("a1")?.status).toBe("done");
      expect(agent("a2")?.status).toBe("done");
    },
    { timeout: 20000 },
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  ev.logs.clear();
  ev.gated.clear();
  ev.calls = [];
  h.layout.props = null as unknown as DashboardLayoutProps;
  h.layout.renders = [];
  h.conn.phase = "idle";
  h.conn.liveRunIds = [];
  h.conn.recentRuns = [];
  h.conn.subscribe.mockImplementation(() => () => {});
  h.conn.sendCommand.mockResolvedValue(null);
  h.api.getToken.mockReturnValue("tok");
  h.api.getMe.mockResolvedValue({ id: "u1", email: "ada@example.com", tier: "basic", is_admin: false });
  h.api.getWorkflows.mockResolvedValue({ runs: [] });
  h.api.getRunEvents.mockImplementation(eventsImpl);
  h.api.getRunFamily.mockResolvedValue({ root_id: "r1", members: [] });
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.spyOn(console, "warn").mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("DashboardPage finished-run reopen", () => {
  it("never commits isRunning true when a finished run's first event page lands before its record", async () => {
    const log = finishedLog();
    ev.logs.set("r1", log.frames);
    ev.gated.add("r1");
    const slim = deferred<WorkflowRun>();
    serveRecords(slim.promise, runRecord({ agentOutputs: log.agentOutputs }));

    mount("/runs/r1");
    const call = await untilPrimaryEventsCall();
    await act(async () => deliverPage(call));
    await act(async () => slim.resolve(runRecord()));
    await act(async () => deliverAll(call));

    await untilStepsSettled();
    expect(h.layout.renders.some((r) => r.isRunning)).toBe(false);
    // A page that landed before the record must still be applied once the run is
    // registered: the step that only appears on the second page keeps its output.
    expect(agent("a2")?.output).toBe(log.expected.a2.output);
  }, 30000);

  it("never commits isRunning true when a finished run's record lands before its events", async () => {
    const log = finishedLog();
    ev.logs.set("r1", log.frames);
    ev.gated.add("r1");
    serveRecords(Promise.resolve(runRecord()), runRecord({ agentOutputs: log.agentOutputs }));

    mount("/runs/r1");
    const call = await untilPrimaryEventsCall();
    await waitFor(() => expect(props()?.userStoryContent).toBe("# Stories"));
    await act(async () => deliverPage(call));
    await act(async () => deliverPage(call));

    await untilStepsSettled();
    expect(h.layout.renders.some((r) => r.isRunning)).toBe(false);
  }, 30000);

  it("shows full per-agent output for a finished run whose steps start after seq 5000", async () => {
    const log = finishedLog();
    ev.logs.set("r1", log.frames);
    ev.gated.add("r1");
    const slim = deferred<WorkflowRun>();
    serveRecords(slim.promise, runRecord({ agentOutputs: log.agentOutputs }));

    mount("/runs/r1");
    const call = await untilPrimaryEventsCall();
    await act(async () => deliverPage(call));
    await act(async () => slim.resolve(runRecord()));
    await act(async () => deliverAll(call));

    await untilStepsSettled();
    for (const id of ["p0", "a1", "a2"]) {
      expect(agent(id)?.output).toBe(log.expected[id].output);
      expect(agent(id)?.thinkingText ?? "").toBe(log.expected[id].thinkingText);
    }
  }, 30000);

  it("falls back to the full log in one batch when agent_outputs cannot cover the run", async () => {
    const log = finishedLog("r1", { openLastPass: true });
    ev.logs.set("r1", log.frames);
    serveRecords(Promise.resolve(runRecord()), runRecord({ agentOutputs: log.agentOutputs }));

    mount("/runs/r1");

    await untilStepsSettled();
    const primary = callsFor("r1");
    expect(primary).toHaveLength(2);
    expect(primary[0].filter).toEqual({ excludeTypes: STREAM_DELTA_EVENT_TYPES });
    expect(primary[0].onPage).toBeUndefined();
    expect(primary[1].filter).toBeUndefined();
    expect(primary[1].onPage).toBeUndefined();
    expect(agent("a2")?.output).toBe(log.expected.a2.output);
    expect(agent("a1")?.output).toBe(log.expected.a1.output);
    expect(h.layout.renders.some((r) => r.isRunning)).toBe(false);
  }, 30000);

  it("requests the finished run without delta events and family members chat-only", async () => {
    const log = finishedLog();
    ev.logs.set("r1", log.frames);
    ev.logs.set("r0", finishedLog("r0").frames);
    ev.logs.set("r2", finishedLog("r2").frames);
    h.api.getRunFamily.mockResolvedValue({ root_id: "r0", members: [{ id: "r0" }, { id: "r1" }, { id: "r2" }] });
    serveRecords(Promise.resolve(runRecord()), runRecord({ agentOutputs: log.agentOutputs }));

    mount("/runs/r1");

    await untilStepsSettled();
    await waitFor(() => expect(h.api.getRunEvents).toHaveBeenCalledTimes(3));
    expect(h.api.getRunEvents).toHaveBeenCalledWith("tok", "r1", 0, undefined, { excludeTypes: STREAM_DELTA_EVENT_TYPES });
    expect(h.api.getRunEvents).toHaveBeenCalledWith("tok", "r0", 0, undefined, { types: CHAT_EVENT_TYPES });
    expect(h.api.getRunEvents).toHaveBeenCalledWith("tok", "r2", 0, undefined, { types: CHAT_EVENT_TYPES });
  }, 30000);

  it("fetches the run family once", async () => {
    const log = finishedLog();
    ev.logs.set("r1", log.frames);
    h.api.getRunFamily.mockResolvedValue({ root_id: "r1", members: [{ id: "r1" }] });
    serveRecords(Promise.resolve(runRecord()), runRecord({ agentOutputs: log.agentOutputs }));

    mount("/runs/r1");

    await untilStepsSettled();
    await waitFor(() => expect(h.api.getRunFamily).toHaveBeenCalled());
    expect(h.api.getRunFamily).toHaveBeenCalledTimes(1);
  }, 30000);

  it("does not run the completion catch-up for a replayed pipeline_complete", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    const log = finishedLog();
    ev.logs.set("r1", log.frames);
    serveRecords(Promise.resolve(runRecord()), runRecord({ agentOutputs: log.agentOutputs }));

    mount("/runs/r1");
    for (let i = 0; i < 10; i++) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
    }
    expect(agent("a2")?.status).toBe("done");
    const before = h.api.getRunEvents.mock.calls.length;

    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(h.api.getRunEvents.mock.calls.length).toBe(before);
  }, 30000);

  it("keeps live runs progressive", async () => {
    // Its own run id: a live run's store entry outlives the unmount (ISS-679),
    // so reusing r1 would leak this run's roster into the next test.
    const frames: Frame[] = [
      { type: "pipeline_start", data: { event_id: "l1", seq: 1, pipeline_run_id: "rl", pipeline_type: "user_stories", agents: ROSTER } },
      { type: "agent_start", data: { event_id: "l2", seq: 2, agent_id: "p0" } },
      { type: "agent_chunk", data: { event_id: "l3", seq: 3, agent_id: "p0", chunk: "live" } },
    ];
    ev.logs.set("rl", frames);
    serveRecords(
      Promise.resolve(runRecord({ id: "rl", status: "running", output: "" })),
      runRecord({ id: "rl", status: "running" }),
    );

    mount("/runs/rl");

    await waitFor(() => expect(h.conn.attachRun).toHaveBeenCalledWith("rl"));
    await waitFor(() => expect(agent("p0")?.output).toBe("live"));
    const liveWalk = callsFor("rl").find((c) => typeof c.onPage === "function");
    expect(liveWalk).toBeDefined();
    expect(liveWalk?.filter).toBeUndefined();
    expect(h.api.getRunEvents).toHaveBeenCalledWith("tok", "rl", 0, expect.any(Function));
    expect(h.api.getWorkflow).not.toHaveBeenCalledWith("tok", "rl", true);
    expect(props().isLoadingRunTrace).toBeFalsy();
    expect(props().pipelineState?.isRunning).toBe(true);
  }, 30000);

  it("shows the Steps loading state until the finished trace lands", async () => {
    const log = finishedLog();
    ev.logs.set("r1", log.frames);
    ev.gated.add("r1");
    serveRecords(Promise.resolve(runRecord()), runRecord({ agentOutputs: log.agentOutputs }));

    mount("/runs/r1");
    const call = await untilPrimaryEventsCall();
    await waitFor(() => expect(props()?.userStoryContent).toBe("# Stories"));
    expect(props().isLoadingRunTrace).toBe(true);
    expect(props().pipelineState?.agents).toHaveLength(0);

    await act(async () => deliverAll(call));

    await untilStepsSettled();
    expect(props().isLoadingRunTrace).toBe(false);
    expect(h.layout.renders.some((r) => r.agentCount > 0 && r.isLoadingRunTrace === true)).toBe(false);
    expect(screen.getByTestId("dashboard-layout")).toBeInTheDocument();
  }, 30000);
});
