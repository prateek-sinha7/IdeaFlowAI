/**
 * Behavior tests for how `page.tsx` routes SSE frames from the run fan-out.
 *
 * `DashboardPage` subscribes one handler to `useRunConnection().subscribe(...)`.
 * These tests mount the real page, capture that subscriber, push frames through
 * it exactly as the SSE transport does (`{ type, data, _sourceRunId }`) and
 * assert on the props the page then hands to `DashboardLayout` (a thin stub, as
 * in `page.coldMount.test.tsx`, which owns the cold-mount/route coverage).
 *
 * The harness block below is intentionally repeated rather than shared:
 * `vi.mock` factories are hoisted per file and cannot be imported.
 */
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { DashboardLayoutProps } from "@/components/layout/DashboardLayout";
import type { WorkflowRun } from "@/types/index";

import DashboardPage from "./page";

// ─── hoisted boundary doubles ───────────────────────────────────────────────

const h = vi.hoisted(() => {
  const nav = { pathname: "/runs/r1/stream" };
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
    subscribe: vi.fn((fn: (m: unknown) => void) => {
      subscribers.add(fn);
      return () => {
        subscribers.delete(fn);
      };
    }),
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

// ─── helpers ────────────────────────────────────────────────────────────────

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

/**
 * Mount the live-stream route for `r1` as a page that launched `launched` runs in
 * this tab and already tracks `r1` (the post-launch remount path).
 */
async function mountTrackingR1(launched: string[] = ["r1"]) {
  sessionStorage.setItem("tab_launched_run_ids", JSON.stringify(launched));
  h.conn.liveRunIds = ["r1"];
  h.nav.pathname = "/runs/r1/stream";
  render(<DashboardPage />);
  await screen.findByTestId("dashboard-layout");
  await waitFor(() => expect(props().contentSourceRunId).toBe("r1"));
  await waitFor(() => expect(h.subscribers.size).toBeGreaterThan(0));
}

const START_R1: Frame = {
  type: "pipeline_start",
  from: "r1",
  data: {
    pipeline_run_id: "r1",
    pipeline_type: "user_stories",
    agents: [{ id: "a1", name: "Alpha", role: "analyst", icon: "A", order: 0 }],
  },
};

/** Apply the updater a `setRecentRuns(prev => ...)` call was given to a list. */
function lastRecentsUpdater(): (prev: WorkflowRun[]) => WorkflowRun[] {
  const call = [...h.conn.setRecentRuns.mock.calls].reverse().find(([arg]) => typeof arg === "function");
  if (!call) throw new Error("setRecentRuns was never called with an updater");
  return call[0] as (prev: WorkflowRun[]) => WorkflowRun[];
}

const row = (id: string, status: string) => ({ id, status, title: id }) as unknown as WorkflowRun;

/** A structurally valid JWT whose `sub` is unique per test, so the module-scope run store (keyed by account) starts empty. */
function makeJwt(sub: string): string {
  const b64 = (o: object) => btoa(JSON.stringify(o)).replace(/=+$/, "").replace(/\+/g, "-").replace(/\//g, "_");
  return `${b64({ alg: "none" })}.${b64({ sub })}.sig`;
}

let token = "";
let testCounter = 0;

beforeEach(() => {
  vi.clearAllMocks();
  token = makeJwt(`user-${++testCounter}`);
  sessionStorage.clear();
  h.subscribers.clear();
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
  h.api.getMe.mockResolvedValue({ id: "u1", email: "a@b.c", tier: "basic", is_admin: false });
  h.api.getWorkflows.mockResolvedValue({ runs: [] });
  h.api.getRunEvents.mockResolvedValue([]);
  h.api.getRunFamily.mockResolvedValue({ members: [] });
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

// ─── dedup + scoping ────────────────────────────────────────────────────────

describe("DashboardPage frame de-duplication and run scoping", () => {
  it("applies a frame carrying an already-seen event id only once", async () => {
    await mountTrackingR1();

    await emit(
      { type: "error", data: { error: "boom", event_id: "ev-1" } },
      { type: "error", data: { error: "boom", event_id: "ev-1" } },
    );

    expect(props().messages).toHaveLength(1);
  });

  it("applies frames that carry no event id every time", async () => {
    await mountTrackingR1();

    await emit({ type: "error", data: { error: "one" } }, { type: "error", data: { error: "two" } });

    expect(props().messages).toHaveLength(2);
  });

  it("drops a foreign run's per-agent frame before it can claim the event id", async () => {
    await mountTrackingR1();
    await emit(START_R1);
    await waitFor(() => expect(props().pipelineState.agents).toHaveLength(1));

    await emit({ type: "agent_start", from: "r9", data: { agent_id: "a1", event_id: "shared-id" } });
    expect(props().pipelineState.agents[0].status).toBe("idle");

    await emit({ type: "agent_start", from: "r1", data: { agent_id: "a1", event_id: "shared-id" } });
    await waitFor(() => expect(props().pipelineState.agents[0].status).toBe("running"));
  });

  it("ignores chat frames in the pipeline router", async () => {
    await mountTrackingR1();

    await emit({ type: "chat_reply", from: "r1", data: { text: "hi" } }, { type: "stream_attached", from: "r1" });

    expect(props().messages).toEqual([]);
    expect(props().pipelineState.isRunning).toBe(false);
  });
});

// ─── pipeline lifecycle ─────────────────────────────────────────────────────

describe("DashboardPage pipeline lifecycle frames", () => {
  it("shows the tracked run as running with its roster on pipeline_start", async () => {
    await mountTrackingR1();

    await emit(START_R1);

    await waitFor(() => expect(props().pipelineState.isRunning).toBe(true));
    expect(props().pipelineState.pipelineRunId).toBe("r1");
    expect(props().pipelineState.agents.map((a) => a.id)).toEqual(["a1"]);
  });

  it("records a foreign run's pipeline_start as background-started without touching the viewed run", async () => {
    await mountTrackingR1();

    await emit({
      type: "pipeline_start",
      from: "r9",
      data: { pipeline_run_id: "r9", agents: [{ id: "x1", name: "X", role: "r", icon: "x", order: 0 }] },
    });

    await waitFor(() => expect(props().backgroundStartedRunId).toBe("r9"));
    expect(props().pipelineState.agents).toEqual([]);
  });

  it("clears a stale questionnaire and gate when the tracked run starts", async () => {
    await mountTrackingR1();
    await emit({
      type: "questionnaire_ready",
      from: "r1",
      data: { pipeline_run_id: "r1", questions: [{ question_id: "q1", question_text: "Why?" }] },
    });
    await waitFor(() => expect(props().activePipelineRunId).toBe("r1"));

    await emit(START_R1);

    await waitFor(() => expect(props().pipelineState.isRunning).toBe(true));
    // The lane reads questionnaireData from the per-run store; the tracked run's
    // own (build) pipeline_start must clear it there too (BUG-005 same-run reset,
    // the positive control TS-Y-02 asserts end-to-end).
    await waitFor(() => expect(props().questionnaireData).toBeNull());
  });

  describe("pipeline_complete", () => {
    it.each([
      ["user_stories", "userStoryContent"],
      ["app_builder_revision", "userStoryContent"],
      ["ppt_v2", "pptContent"],
      ["prototype_large_revision", "prototypeContent"],
    ] as const)("routes a %s deliverable to %s", async (pipelineType, slot) => {
      await mountTrackingR1();

      await emit({
        type: "pipeline_complete",
        from: "r1",
        data: { pipeline_run_id: "r1", pipeline_type: pipelineType, final_output: "OUTPUT" },
      });

      await waitFor(() => expect(props()[slot]).toBe("OUTPUT"));
    });

    it("routes an unrecognised type to the generic deliverable using the declared mimetype and filename", async () => {
      await mountTrackingR1();

      await emit({
        type: "pipeline_complete",
        from: "r1",
        data: {
          pipeline_run_id: "r1",
          pipeline_type: "some_custom_flow",
          final_output: "ZIPDATA",
          deliverable_mimetype: "application/zip",
          deliverable_filename: "bundle.zip",
        },
      });

      await waitFor(() => expect(props().genericDeliverable).toBeDefined());
      expect(props().genericDeliverable).toEqual({
        mimetype: "application/zip",
        filename: "bundle.zip",
        content: "ZIPDATA",
      });
    });

    it("derives the mimetype from the output when the event declares none", async () => {
      await mountTrackingR1();

      await emit({
        type: "pipeline_complete",
        from: "r1",
        data: { pipeline_run_id: "r1", pipeline_type: "some_custom_flow", final_output: "<!DOCTYPE html><p>x</p>" },
      });

      await waitFor(() => expect(props().genericDeliverable?.mimetype).toBe("text/html"));
      expect(props().genericDeliverable?.filename).toBeUndefined();
    });

    it("makes the completing tracked run the content source and releases its stream", async () => {
      await mountTrackingR1();

      await emit({
        type: "pipeline_complete",
        from: "r1",
        data: { pipeline_run_id: "r1", pipeline_type: "user_stories", final_output: "# Done" },
      });

      expect(h.conn.detachRun).toHaveBeenCalledWith("r1");
      expect(props().contentSourceRunId).toBe("r1");
    });

    it("marks the run completed in the recents list, leaving other rows and unchanged rows alone", async () => {
      await mountTrackingR1();

      await emit({ type: "pipeline_complete", from: "r1", data: { pipeline_run_id: "r1", pipeline_type: "x" } });

      const update = lastRecentsUpdater();
      const list = [row("r1", "running"), row("r2", "running")];
      expect(update(list).map((r) => [r.id, r.status])).toEqual([
        ["r1", "completed"],
        ["r2", "running"],
      ]);
      const settled = [row("r1", "completed")];
      expect(update(settled)).toBe(settled);
      const unrelated = [row("r2", "running")];
      expect(update(unrelated)).toBe(unrelated);
    });

    it("uses the reported status for the recents patch", async () => {
      await mountTrackingR1();

      await emit({
        type: "pipeline_complete",
        from: "r1",
        data: { pipeline_run_id: "r1", pipeline_type: "x", status: "degraded", agents_failed: [] },
      });

      expect(lastRecentsUpdater()([row("r1", "running")])[0].status).toBe("degraded");
    });

    it("appends a degraded warning naming the failed agents", async () => {
      await mountTrackingR1();

      await emit({
        type: "pipeline_complete",
        from: "r1",
        data: { pipeline_run_id: "r1", pipeline_type: "x", status: "degraded", agents_failed: ["a1", "a2"] },
      });

      await waitFor(() => expect(props().messages).toHaveLength(1));
      expect(props().messages[0].content).toBe(
        "Warning: run completed degraded — the deliverable was produced, but these agents failed: a1, a2. [code:pipeline_degraded] [recoverable:false]",
      );
    });

    it("words the degraded warning generically when no agents are named", async () => {
      await mountTrackingR1();

      await emit({
        type: "pipeline_complete",
        from: "r1",
        data: { pipeline_run_id: "r1", pipeline_type: "x", status: "degraded" },
      });

      await waitFor(() => expect(props().messages).toHaveLength(1));
      expect(props().messages[0].content).toContain("but some agents failed.");
    });

    it("signals a foreign run's completion as background-completed without re-pointing the content source", async () => {
      await mountTrackingR1();

      await emit({
        type: "pipeline_complete",
        from: "r9",
        data: { pipeline_run_id: "r9", pipeline_type: "user_stories", final_output: "# Other" },
      });

      await waitFor(() => expect(props().backgroundCompletedRunId).toBe("r9"));
      expect(props().contentSourceRunId).toBe("r1");
      expect(h.conn.detachRun).not.toHaveBeenCalled();
    });

    it("advances the content source to a revision run completing from the tracked run", async () => {
      await mountTrackingR1();

      await emit({
        type: "pipeline_complete",
        from: "rev9",
        data: { pipeline_run_id: "rev9", pipeline_type: "user_stories_revision", final_output: "# v2" },
      });

      await waitFor(() => expect(props().contentSourceRunId).toBe("rev9"));
      expect(props().backgroundCompletedRunId).toBeNull();
      expect(h.conn.detachRun).toHaveBeenCalledWith("rev9");
    });

    it("recovers the narrator card the detach raced by folding in chat frames fetched after completion", async () => {
      await mountTrackingR1();
      vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
      h.api.getRunEvents.mockClear();
      h.api.getRunEvents.mockResolvedValue([
        { type: "agent_chunk", data: { event_id: "n0" } },
        { type: "chat_reply", data: { event_id: "n1", text: "Delivered" } },
      ]);

      await emit({
        type: "pipeline_complete",
        from: "r1",
        data: { pipeline_run_id: "r1", pipeline_type: "user_stories", final_output: "# Done" },
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(400);
      });

      expect(h.api.getRunEvents).toHaveBeenCalledWith(token, "r1", 0);
    });
  });

  describe("pipeline_failed", () => {
    it("tells the user which agents failed and why, for the tracked run", async () => {
      await mountTrackingR1();

      await emit({
        type: "pipeline_failed",
        from: "r1",
        data: { pipeline_run_id: "r1", error: "Out of budget", agents_failed: ["a1"] },
      });

      await waitFor(() => expect(props().messages).toHaveLength(1));
      expect(props().messages[0]).toEqual(
        expect.objectContaining({
          role: "assistant",
          content: "Error: Out of budget (agents failed: a1) [code:pipeline_failed] [recoverable:false]",
        }),
      );
      expect(lastRecentsUpdater()([row("r1", "running")])[0].status).toBe("failed");
    });

    it("uses a generic message when the failure carries no reason or agents", async () => {
      await mountTrackingR1();

      await emit({ type: "pipeline_failed", from: "r1", data: { pipeline_run_id: "r1" } });

      await waitFor(() => expect(props().messages).toHaveLength(1));
      expect(props().messages[0].content).toBe("Error: Pipeline failed [code:pipeline_failed] [recoverable:false]");
    });

    it("keeps a run this tab never launched out of the chat", async () => {
      await mountTrackingR1();

      await emit({ type: "pipeline_failed", from: "r9", data: { pipeline_run_id: "r9", error: "nope" } });

      expect(props().messages).toEqual([]);
      expect(props().backgroundRunTransition).toBeNull();
    });

    it("flags a launched background run as failed without adding a chat message", async () => {
      await mountTrackingR1(["r1", "r9"]);

      await emit({ type: "pipeline_failed", from: "r9", data: { pipeline_run_id: "r9", error: "bg" } });

      await waitFor(() => expect(props().backgroundRunTransition).toEqual({ runId: "r9", to: "failed" }));
    });
  });

  describe("pipeline_cancelled", () => {
    it("records the cancelled run, releases its stream and marks it cancelled in recents", async () => {
      await mountTrackingR1();

      await emit({ type: "pipeline_cancelled", from: "r1", data: { pipeline_run_id: "r1" } });

      await waitFor(() => expect(props().lastCancelledRunId).toBe("r1"));
      expect(h.conn.detachRun).toHaveBeenCalledWith("r1");
      expect(props().activePipelineRunId).toBeNull();
      expect(lastRecentsUpdater()([row("r1", "running")])[0].status).toBe("cancelled");
    });

    it("flags a launched background run as cancelled", async () => {
      await mountTrackingR1(["r1", "r9"]);

      await emit({ type: "pipeline_cancelled", from: "r9", data: { pipeline_run_id: "r9" } });

      await waitFor(() => expect(props().backgroundRunTransition).toEqual({ runId: "r9", to: "cancelled" }));
    });

    it("ignores a cancel from a run this tab never launched", async () => {
      await mountTrackingR1();

      await emit({ type: "pipeline_cancelled", from: "r9", data: { pipeline_run_id: "r9" } });

      expect(props().lastCancelledRunId).toBeNull();
      expect(h.conn.detachRun).not.toHaveBeenCalled();
    });
  });

  describe("pipeline_diverted", () => {
    it("refetches the run list for a live divert and replaces recents with it", async () => {
      const runs = [{ id: "r1" }, { id: "target" }];
      h.api.getWorkflows.mockResolvedValue({ runs });
      await mountTrackingR1();

      await emit({ type: "pipeline_diverted", from: "r1", data: { pipeline_run_id: "r1", diverted_to_run_id: "target" } });

      await waitFor(() => expect(h.conn.setRecentRuns).toHaveBeenCalledWith(runs));
      expect(h.api.getWorkflows).toHaveBeenCalledWith(token, { limit: 50 });
    });

    it("does not refetch the run list when the divert is only replayed from the durable log", async () => {
      sessionStorage.setItem("tab_launched_run_ids", JSON.stringify(["r1"]));
      h.nav.pathname = "/runs/r1";
      h.api.getWorkflow.mockResolvedValue({ id: "r1", status: "diverted", type: "user_stories", input: "x", agentCount: 1 });
      h.api.getRunEvents.mockResolvedValue([
        { type: "pipeline_diverted", data: { pipeline_run_id: "r1", diverted_to_run_id: "target" } },
      ]);

      render(<DashboardPage />);
      await waitFor(() => expect(props()?.reopenedRunStatus).toBe("diverted"));

      expect(h.api.getRunEvents).toHaveBeenCalledWith(token, "r1");
      expect(h.api.getWorkflows).not.toHaveBeenCalled();
    });
  });
});

// ─── clarify + review gate ──────────────────────────────────────────────────

describe("DashboardPage clarify and review-gate frames", () => {
  const QUESTION = {
    question_id: "q1",
    question_text: "Who is the user?",
    options: ["admin", "guest"],
    answer_type: "multi_choice",
    recommended_answer: "admin",
    recommended_reasoning: "most common",
    recommended_display: "Admin",
    ambiguity_category: "scope",
    impact_level: "high",
  };

  it("maps a questionnaire_ready frame onto the viewed run's clarify state and flags it waiting", async () => {
    await mountTrackingR1();

    await emit({ type: "questionnaire_ready", from: "r1", data: { pipeline_run_id: "r1", questions: [QUESTION] } });

    await waitFor(() => expect(props().questionnaireData).not.toBeNull());
    expect(props().questionnaireData).toEqual({
      questions: [
        {
          id: "q1",
          question: "Who is the user?",
          options: ["admin", "guest"],
          answerType: "multi_choice",
          recommendedAnswer: "admin",
          recommendedReasoning: "most common",
          recommendedDisplay: "Admin",
          ambiguityCategory: "scope",
          impactLevel: "high",
        },
      ],
    });
    expect(props().activePipelineRunId).toBe("r1");
    expect(lastRecentsUpdater()([row("r1", "planning")])[0].status).toBe("waiting_for_user");
  });

  it("fills in defaults for a sparse question", async () => {
    await mountTrackingR1();

    await emit({
      type: "questionnaire_ready",
      from: "r1",
      data: { pipeline_run_id: "r1", questions: [{ question_id: "q2", question_text: "Sparse?" }] },
    });

    await waitFor(() => expect(props().questionnaireData).not.toBeNull());
    expect(props().questionnaireData?.questions[0]).toEqual({
      id: "q2",
      question: "Sparse?",
      options: [],
      answerType: "single_choice",
      recommendedAnswer: "",
      recommendedReasoning: "",
      recommendedDisplay: "",
      ambiguityCategory: "",
      impactLevel: "medium",
    });
  });

  it("keeps a background run's questions out of the viewed run's clarify panel", async () => {
    await mountTrackingR1(["r1", "r9"]);

    await emit({ type: "questionnaire_ready", from: "r9", data: { pipeline_run_id: "r9", questions: [QUESTION] } });

    expect(props().questionnaireData).toBeNull();
    expect(props().activePipelineRunId).toBe("r1");
  });

  it("clears the clarify state and flags the run generating on questionnaire_complete", async () => {
    await mountTrackingR1();
    await emit({ type: "questionnaire_ready", from: "r1", data: { pipeline_run_id: "r1", questions: [QUESTION] } });
    await waitFor(() => expect(props().questionnaireData).not.toBeNull());

    await emit({ type: "questionnaire_complete", from: "r1", data: {} });

    await waitFor(() => expect(props().questionnaireData).toBeNull());
    expect(lastRecentsUpdater()([row("r1", "waiting_for_user")])[0].status).toBe("generating");
  });

  describe("review gates", () => {
    const GATE = {
      pipeline_run_id: "r1",
      gate_key: "gate-1",
      agent_id: "a1",
      agent_name: "Alpha",
      output: "Draft output",
    };

    it("opens the viewed run's gate with defaulted flags, forcing the run to running", async () => {
      await mountTrackingR1();

      await emit({ type: "review_gate_ready", from: "r1", data: GATE });

      await waitFor(() => expect(props().reviewGateData).not.toBeNull());
      expect(props().reviewGateData).toEqual({
        gateKey: "gate-1",
        agentId: "a1",
        agentName: "Alpha",
        output: "Draft output",
        pipelineRunId: "r1",
        redoable: false,
        updateSpecsEligible: false,
        artifactKind: undefined,
        revisionCycle: 0,
        revisionInFlight: false,
      });
      expect(props().pipelineState.isRunning).toBe(true);
      expect(lastRecentsUpdater()([row("r1", "running")])[0].status).toBe("waiting_for_user");
    });

    it("carries the server's redo, update-specs and revision flags into the gate", async () => {
      await mountTrackingR1();

      await emit({
        type: "review_gate_ready",
        from: "r1",
        data: {
          ...GATE,
          redoable: true,
          update_specs_eligible: true,
          artifact_kind: "spec",
          revision_cycle: 2,
          revision_in_flight: true,
        },
      });

      await waitFor(() => expect(props().reviewGateData).not.toBeNull());
      expect(props().reviewGateData).toEqual(
        expect.objectContaining({ redoable: true, updateSpecsEligible: true, artifactKind: "spec", revisionCycle: 2, revisionInFlight: true }),
      );
    });

    it("closes the gate and flags the run generating when it is approved", async () => {
      await mountTrackingR1();
      await emit({ type: "review_gate_ready", from: "r1", data: GATE });
      await waitFor(() => expect(props().reviewGateData).not.toBeNull());

      await emit({ type: "review_gate_approved", from: "r1", data: {} });

      await waitFor(() => expect(props().reviewGateData).toBeNull());
      expect(lastRecentsUpdater()([row("r1", "waiting_for_user")])[0].status).toBe("generating");
    });

    it("flags a launched background run as paused at a gate, then running once approved", async () => {
      await mountTrackingR1(["r1", "r9"]);

      await emit({ type: "review_gate_ready", from: "r9", data: { ...GATE, pipeline_run_id: "r9" } });
      await waitFor(() => expect(props().backgroundRunTransition).toEqual({ runId: "r9", to: "gate" }));
      expect(props().reviewGateData).toBeNull();

      await emit({ type: "review_gate_approved", from: "r9", data: {} });
      await waitFor(() => expect(props().backgroundRunTransition).toEqual({ runId: "r9", to: "running" }));
    });
  });
});

// ─── waves ──────────────────────────────────────────────────────────────────

describe("DashboardPage wave frames", () => {
  it("builds the viewed run's wave tree from wave and subagent frames", async () => {
    await mountTrackingR1();

    await emit(
      { type: "wave_started", from: "r1", data: { wave_index: 0, step: "build", task_ids: ["t1", "t2"], wave_total: 2, task_total: 4 } },
      { type: "subagent_spawned", from: "r1", data: { wave_index: 0, step: "build", worker: 0, agent: "builder", task_id: "t1" } },
      { type: "subagent_result", from: "r1", data: { wave_index: 0, step: "build", worker: 0, agent: "builder", task_id: "t1", status: "completed" } },
    );

    await waitFor(() => expect(props().waves).toHaveLength(1));
    expect(props().waves[0]).toEqual(
      expect.objectContaining({
        waveIndex: 0,
        step: "build",
        taskIds: ["t1", "t2"],
        waveTotal: 2,
        taskTotal: 4,
        status: "running",
      }),
    );
    expect(props().waves[0].workers).toEqual([
      expect.objectContaining({ agent: "builder", worker: 0, taskId: "t1", status: "completed" }),
    ]);
  });

  it("marks a wave completed and a wave failed", async () => {
    await mountTrackingR1();

    await emit(
      { type: "wave_started", from: "r1", data: { wave_index: 0, step: "s" } },
      { type: "wave_completed", from: "r1", data: { wave_index: 0, step: "s" } },
      { type: "wave_failed", from: "r1", data: { wave_index: 1, step: "s" } },
    );

    await waitFor(() => expect(props().waves).toHaveLength(2));
    expect(props().waves.map((w) => [w.waveIndex, w.status])).toEqual([
      [0, "completed"],
      [1, "failed"],
    ]);
  });

  // SUSPECTED PRODUCTION DEFECT (reported, not fixed): the wave branch of handleWebSocketMessage reads
  // `(msg as Record)._sourceRunId`, but the SSE subscriber forwards only `{ type, data }` and passes the
  // source run as the SEPARATE `sourceRunId` argument, so `waveSourceRunId` is always undefined for frames
  // that carry no `pipeline_run_id` (wave payloads never do). The foreign-run guard therefore never fires
  // and a concurrent run's wave frames land in the VIEWED run's wave tree. `it.fails` pins the intended
  // contract: it passes while the defect exists and turns red the moment the guard is fixed (then drop `.fails`).
  it.fails("drops a wave frame from a run other than the one being built", async () => {
    await mountTrackingR1();

    await emit({ type: "wave_started", from: "r9", data: { wave_index: 0, step: "s" } });

    expect(props().waves).toEqual([]);
  });

  it("drops a wave frame that names neither a wave nor a parent task", async () => {
    await mountTrackingR1();

    await emit({ type: "wave_started", from: "r1", data: { step: "s" } });

    expect(props().waves).toEqual([]);
  });

  it("falls back to the building run for a wave frame that names no run", async () => {
    await mountTrackingR1();

    await emit({ type: "wave_started", data: { wave_index: 0, step: "s" } });

    await waitFor(() => expect(props().waves).toHaveLength(1));
  });
});

// ─── legacy chat-lane frames ────────────────────────────────────────────────

describe("DashboardPage chat-lane frames", () => {
  it("renders an error frame as a recoverable assistant message with its code", async () => {
    await mountTrackingR1();

    await emit({ type: "error", data: { error: "Model unavailable", code: "model_down", recoverable: false } });

    await waitFor(() => expect(props().messages).toHaveLength(1));
    expect(props().messages[0]).toEqual(
      expect.objectContaining({
        role: "assistant",
        content: "Error: Model unavailable [code:model_down] [recoverable:false]",
      }),
    );
  });

  it("falls back to a generic message for an error frame with no detail", async () => {
    await mountTrackingR1();

    await emit({ type: "error", data: {} });

    await waitFor(() => expect(props().messages).toHaveLength(1));
    expect(props().messages[0].content).toBe("Error: An error occurred during processing. [recoverable:true]");
  });

  it("fills the preview slots from a complete frame's final output", async () => {
    await mountTrackingR1();

    await emit({
      type: "complete",
      data: { user_stories: { epics: 1 }, ppt: "deck", prototype: ["screen"] },
    });

    await waitFor(() => expect(props().userStoryContent).toBe('{"epics":1}'));
    expect(props().pptContent).toBe('"deck"');
    expect(props().prototypeContent).toBe('["screen"]');
    expect(props().isStreaming).toBe(false);
  });

  it("publishes a chat title update and ignores one missing its session id", async () => {
    await mountTrackingR1();

    await emit({ type: "title_update", data: { title: "orphan" } });
    expect(props().chatTitleUpdate).toBeNull();

    await emit({ type: "title_update", data: { chat_session_id: "c1", title: "Renamed" } });
    await waitFor(() => expect(props().chatTitleUpdate).toEqual({ chat_session_id: "c1", title: "Renamed" }));
  });

  it("retitles only the matching run in recents on workflow_title_update", async () => {
    await mountTrackingR1();

    await emit({ type: "workflow_title_update", data: { workflow_id: "r2", title: "Clean title" } });

    const next = lastRecentsUpdater()([row("r1", "running"), row("r2", "running")]);
    expect(next.map((r) => r.title)).toEqual(["r1", "Clean title"]);
  });

  it("ignores a workflow_title_update without a title", async () => {
    await mountTrackingR1();

    await emit({ type: "workflow_title_update", data: { workflow_id: "r2" } });

    expect(h.conn.setRecentRuns).not.toHaveBeenCalled();
  });

  it("adds a process step, then updates it in place by id", async () => {
    await mountTrackingR1();

    await emit({ type: "step", data: { id: "s1", status: "running", label: "Think" } });
    await waitFor(() => expect(props().processSteps).toHaveLength(1));
    await emit(
      { type: "step", data: { id: "s2", status: "running", label: "Write" } },
      { type: "step", data: { id: "s1", status: "done", label: "Think" } },
    );

    await waitFor(() => expect(props().processSteps).toHaveLength(2));
    expect(props().processSteps.map((s) => [s.id, s.status])).toEqual([
      ["s1", "done"],
      ["s2", "running"],
    ]);
  });
});
