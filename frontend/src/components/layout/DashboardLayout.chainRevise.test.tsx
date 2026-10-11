/**
 * DashboardLayout — revise and chain flows: the lane's "revise" composer, the
 * lane's "chain into" suggestion chips, and the history page's chain action.
 * Covers the per-type revise handlers (REST revision vs. text-injection
 * start), wizard hand-off through sessionStorage, direct chained starts,
 * and the hold-until-connected path.
 *
 * Mocked at system boundaries only: next/navigation, motion/react, @/lib/api
 * (token, chain context, revisions), the SSE run connection, and the heavy leaf
 * components. The chain targets come from the real Redux catalog (preloaded
 * state), through the real useWorkflowChaining selector. The lane and history
 * stubs render real buttons that call the props DashboardLayout hands them.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import React from "react";
import { cleanup, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders, screen } from "@/test/renderWithProviders";
import type { PipelineRunState, WorkflowRun, WorkflowType } from "@/types/index";
import type { WorkflowSummary } from "@/store/api/workflows";
import { getChainContext, getToken, postRevision } from "@/lib/api";
import {
  CHAIN_BRIEF_KEY,
  CHAIN_CONTEXT_BLOCK_KEY,
  CHAIN_FROM_KEY,
  CHAIN_SOURCE_RUN_ID_KEY,
} from "@/lib/workflowChaining";
import type { RunChatLane } from "@/components/chat/RunChatLane";
import type { WorkflowHistory } from "@/components/history/WorkflowHistory";

type LaneProps = React.ComponentProps<typeof RunChatLane>;
type HistoryProps = React.ComponentProps<typeof WorkflowHistory>;

const { router, attachRun } = vi.hoisted(() => ({
  router: { push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() },
  attachRun: vi.fn(),
}));

vi.mock("next/navigation", () => ({ useRouter: () => router }));

const STRIPPED_MOTION_PROPS = new Set([
  "initial", "animate", "exit", "transition", "whileHover",
  "whileTap", "whileFocus", "whileInView", "viewport", "layout",
  "layoutId", "drag", "dragConstraints", "variants", "custom",
]);
type MotionStub = (props: { children?: React.ReactNode } & Record<string, unknown>) => React.ReactElement;
vi.mock("motion/react", () => {
  // One component per tag: a fresh function on every access would remount the
  // whole view each time DashboardLayout re-renders.
  const cache = new Map<string, MotionStub>();
  return {
    motion: new Proxy(
      {},
      {
        get: (_target, prop: string) => {
          let stub = cache.get(prop);
          if (!stub) {
            stub = ({ children, ...rest }) => {
              const cleaned = Object.fromEntries(
                Object.entries(rest).filter(([k]) => !STRIPPED_MOTION_PROPS.has(k)),
              );
              return React.createElement(prop, cleaned, children);
            };
            cache.set(prop, stub);
          }
          return stub;
        },
      },
    ),
    AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  };
});

vi.mock("@/lib/api", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/api")>();
  return {
    ...actual,
    getToken: vi.fn(),
    getRunFamily: () => Promise.resolve({ root_id: "", members: [] }),
    getChainContext: vi.fn(),
    postRevision: vi.fn(),
  };
});

vi.mock("@/providers/RunConnectionProvider", () => {
  const connection = { attachRun };
  return { useRunConnection: () => connection };
});

vi.mock("@/components/layout/AppHeader", () => ({ AppHeader: () => <header /> }));
vi.mock("@/components/catalog/HomeLaunchGrid", () => ({
  HomeLaunchGrid: () => <section aria-label="Home grid" />,
}));
vi.mock("@/components/library/LibraryPage", () => ({ LibraryPage: () => null }));
vi.mock("@/components/settings/AccountSettings", () => ({ AccountSettings: () => null }));
vi.mock("@/components/analytics/AnalyticsPage", () => ({ AnalyticsPage: () => null }));
vi.mock("@/components/savedworkflows/SavedWorkflowsPage", () => ({ SavedWorkflowsPage: () => null }));
vi.mock("@/components/workflow/composer/ComposerPage", () => ({ ComposerPage: () => null }));
vi.mock("@/components/workflow/IdeaInputPage", () => ({ IdeaInputPage: () => null }));
vi.mock("@/components/preview/PreviewPanel", () => ({
  PreviewPanel: () => <section aria-label="Preview panel" />,
}));
vi.mock("@/components/ui/CompletionToast", () => ({ CompletionToast: () => null }));

vi.mock("@/components/chat/RunChatLane", () => ({
  RunChatLane: (props: LaneProps) => (
    <section aria-label="Run lane">
      {props.onRevise && (
        <button type="button" onClick={() => props.onRevise?.("tweak it")}>Revise</button>
      )}
      {props.suggestions?.map((s) => (
        <button key={s.id} type="button" onClick={() => props.onSuggestion?.(s.id)}>
          Chain {s.id}
        </button>
      ))}
    </section>
  ),
}));

const HISTORY_RUN: WorkflowRun = {
  id: "hist-1",
  title: "History run",
  type: "user_stories" as WorkflowType,
  status: "completed",
  input: "Original brief",
  output: "OUT",
  parentRunId: null,
  rootRunId: "hist-1",
  createdAt: "2025-01-01T00:00:00.000Z",
  agentCount: 1,
};

vi.mock("@/components/history/WorkflowHistory", () => ({
  WorkflowHistory: (props: HistoryProps) => (
    <section aria-label="History page">
      <button type="button" onClick={() => props.onChainPipeline?.(HISTORY_RUN, "prototype" as WorkflowType)}>
        Chain prototype from history
      </button>
      <button type="button" onClick={() => props.onChainPipeline?.({ ...HISTORY_RUN, id: "" }, "prototype" as WorkflowType)}>
        Chain prototype from unsaved run
      </button>
      <button type="button" onClick={() => props.onChainPipeline?.(HISTORY_RUN, "app_builder" as WorkflowType)}>
        Chain app from history
      </button>
      <button type="button" onClick={() => props.onChainPipeline?.(HISTORY_RUN, "app_builder" as WorkflowType, "uw-1")}>
        Chain app with saved workflow
      </button>
      <button type="button" onClick={() => props.onChainPipeline?.({ ...HISTORY_RUN, input: "" }, "app_builder" as WorkflowType)}>
        Chain app from empty brief
      </button>
    </section>
  ),
}));

import { DashboardLayout } from "./DashboardLayout";
import type { DashboardLayoutProps } from "./DashboardLayout";

function catalogEntry(id: string, text: string): WorkflowSummary {
  return {
    id,
    name: id,
    description: "",
    step_count: 1,
    steps: [],
    user_launchable: true,
    chained_from: [{ id: "user_stories", beta: false, text }],
  };
}

const CATALOG: WorkflowSummary[] = [
  catalogEntry("prototype", "Build a prototype"),
  catalogEntry("app_builder", "Build the app"),
];

function idlePipelineState(overrides: Partial<PipelineRunState> = {}): PipelineRunState {
  return {
    isRunning: false,
    pipeline_type: "user_stories",
    agents: [],
    currentAgentIndex: -1,
    totalDuration: null,
    completedCount: 0,
    ...overrides,
  };
}

function baseProps(overrides: Partial<DashboardLayoutProps> = {}): DashboardLayoutProps {
  return {
    activeChatId: null,
    messages: [],
    isStreaming: false,
    streamingContent: "",
    userStoryContent: "",
    pptContent: "",
    prototypeContent: "",
    connectionStatus: "connected",
    onSendMessage: vi.fn(),
    onSelectChat: vi.fn(),
    onNewChat: vi.fn(),
    onDeleteChat: vi.fn(),
    onLogout: vi.fn(),
    onReconnect: vi.fn(),
    initialMainView: "execution",
    contentSourceRunType: "user_stories" as WorkflowType,
    pipelineState: idlePipelineState(),
    ...overrides,
  };
}

function renderLayout(overrides: Partial<DashboardLayoutProps> = {}) {
  const user = userEvent.setup();
  const props = baseProps(overrides);
  const view = renderWithProviders(<DashboardLayout {...props} />, {
    preloadedState: {
      global: {
        workflows: CATALOG,
        workflowsStatus: "succeeded",
        workflowsError: null,
        recentRuns: [],
        recentRunsStatus: "idle",
        recentRunsError: null,
      },
    },
  });
  const rerenderLayout = (next: Partial<DashboardLayoutProps>) =>
    view.rerender(<DashboardLayout {...props} {...next} />);
  return { user, props, rerenderLayout, ...view };
}

function region(name: string): HTMLElement {
  return screen.getByRole("region", { name });
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  sessionStorage.clear();
  localStorage.clear();
  window.history.replaceState(null, "", "/");
  vi.mocked(getToken).mockReturnValue("tok");
  vi.mocked(postRevision).mockReset().mockResolvedValue({ run_id: "rev-1" });
  vi.mocked(getChainContext)
    .mockReset()
    .mockResolvedValue({ brief: "ctx brief", context_block: "CTX" } as Awaited<ReturnType<typeof getChainContext>>);
});

afterEach(() => {
  vi.useRealTimers();
});


describe("DashboardLayout revise from the lane", () => {
  it("offers no revise composer for a run type without a revise path", () => {
    renderLayout({ contentSourceRunType: "migration" as WorkflowType });

    expect(screen.queryByRole("button", { name: "Revise" })).not.toBeInTheDocument();
  });

  describe("presentation", () => {
    const pptProps = { contentSourceRunType: "ppt" as WorkflowType };

    it("launches a REST revision of the on-screen run and attaches the new run", async () => {
      const onResetPipeline = vi.fn();
      const onRevisionLaunched = vi.fn();
      const { user } = renderLayout({
        ...pptProps,
        contentSourceRunId: "run-src",
        onResetPipeline,
        onRevisionLaunched,
      });

      await user.click(screen.getByRole("button", { name: "Revise" }));

      expect(postRevision).toHaveBeenCalledWith("tok", "run-src", {
        target_artifact_type: "ppt_output",
        instruction: "tweak it",
      });
      await waitFor(() => expect(attachRun).toHaveBeenCalledWith("rev-1"));
      expect(onRevisionLaunched).toHaveBeenCalledWith("rev-1");
      expect(onResetPipeline).toHaveBeenCalledTimes(1);
      // The parent run is not the revision run, so nothing is pushed for it.
      expect(router.push).not.toHaveBeenCalled();
      expect(region("Run lane")).toBeInTheDocument();
    });

    it("does not attach anything when the revision returns no run id", async () => {
      vi.mocked(postRevision).mockResolvedValue({ run_id: "" });
      const onRevisionLaunched = vi.fn();
      const { user } = renderLayout({ ...pptProps, contentSourceRunId: "run-src", onRevisionLaunched });

      await user.click(screen.getByRole("button", { name: "Revise" }));

      await waitFor(() => expect(postRevision).toHaveBeenCalledTimes(1));
      expect(attachRun).not.toHaveBeenCalled();
      expect(onRevisionLaunched).not.toHaveBeenCalled();
    });

    it("logs a rejected revision request", async () => {
      const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
      const failure = new Error("revision failed");
      vi.mocked(postRevision).mockRejectedValue(failure);
      const { user } = renderLayout({ ...pptProps, contentSourceRunId: "run-src" });

      await user.click(screen.getByRole("button", { name: "Revise" }));

      await waitFor(() => expect(errorSpy).toHaveBeenCalledWith("postRevision failed", failure));
      errorSpy.mockRestore();
    });

    it("injects the existing deck into a new run when no parent run is known", async () => {
      const onResetPipeline = vi.fn();
      const onStartPipeline = vi.fn();
      const { user } = renderLayout({ ...pptProps, pptContent: "<html>deck</html>", onResetPipeline, onStartPipeline });

      await user.click(screen.getByRole("button", { name: "Revise" }));

      expect(postRevision).not.toHaveBeenCalled();
      expect(onResetPipeline).toHaveBeenCalledTimes(1);
      expect(onStartPipeline).toHaveBeenCalledWith(
        "ppt_revision",
        "=== EXISTING HTML DECK ===\n<html>deck</html>\n=== END EXISTING DECK ===\n\n" +
          "=== REVISION REQUEST ===\ntweak it\n=== END REQUEST ===",
        undefined,
        [],
      );
    });

    it("only resets when no start handler is supplied for the legacy path", async () => {
      const onResetPipeline = vi.fn();
      const { user } = renderLayout({ ...pptProps, pptContent: "<html>deck</html>", onResetPipeline });

      await user.click(screen.getByRole("button", { name: "Revise" }));

      expect(onResetPipeline).toHaveBeenCalledTimes(1);
    });

    it("does nothing when there is neither a parent run nor a deck", async () => {
      const onResetPipeline = vi.fn();
      const onStartPipeline = vi.fn();
      const { user } = renderLayout({ ...pptProps, onResetPipeline, onStartPipeline });

      await user.click(screen.getByRole("button", { name: "Revise" }));

      expect(postRevision).not.toHaveBeenCalled();
      expect(onResetPipeline).not.toHaveBeenCalled();
      expect(onStartPipeline).not.toHaveBeenCalled();
    });
  });

  describe("user stories", () => {
    it("restarts with the backlog embedded and the on-screen run as parent", async () => {
      const onResetPipeline = vi.fn();
      const onStartPipeline = vi.fn();
      const { user } = renderLayout({
        userStoryContent: "# Backlog",
        contentSourceRunId: "run-src",
        onResetPipeline,
        onStartPipeline,
      });

      await user.click(screen.getByRole("button", { name: "Revise" }));

      expect(onResetPipeline).toHaveBeenCalledTimes(1);
      expect(onStartPipeline).toHaveBeenCalledWith(
        "user_stories_revision",
        "=== EXISTING PRODUCT BACKLOG ===\n# Backlog\n=== END EXISTING BACKLOG ===\n\n" +
          "=== REVISION REQUEST ===\ntweak it\n=== END REQUEST ===",
        undefined,
        [],
        { source_workflow_run_id: "run-src", _display_title: "tweak it" },
      );
    });

    it("does nothing without a backlog on screen", async () => {
      const onStartPipeline = vi.fn();
      const { user } = renderLayout({ onStartPipeline });

      await user.click(screen.getByRole("button", { name: "Revise" }));

      expect(onStartPipeline).not.toHaveBeenCalled();
    });

    it("only resets when no start handler is supplied", async () => {
      const onResetPipeline = vi.fn();
      const { user } = renderLayout({ userStoryContent: "# Backlog", onResetPipeline });

      await user.click(screen.getByRole("button", { name: "Revise" }));

      expect(onResetPipeline).toHaveBeenCalledTimes(1);
    });
  });

  describe("prototype", () => {
    const prototypeProps = { contentSourceRunType: "prototype" as WorkflowType, prototypeContent: "<html>proto</html>" };

    it("restarts with the prototype embedded and links the on-screen run", async () => {
      const onStartPipeline = vi.fn();
      const { user } = renderLayout({ ...prototypeProps, contentSourceRunId: "run-src", onStartPipeline });

      await user.click(screen.getByRole("button", { name: "Revise" }));

      expect(onStartPipeline).toHaveBeenCalledWith(
        "prototype_revision",
        "=== EXISTING PROTOTYPE HTML ===\n<html>proto</html>\n=== END EXISTING HTML ===\n\n" +
          "=== REVISION REQUEST ===\ntweak it\n=== END REQUEST ===",
        undefined,
        [],
        { source_workflow_run_id: "run-src", _display_title: "tweak it" },
      );
    });

    it("omits the parent link when no run is on screen", async () => {
      const onStartPipeline = vi.fn();
      const { user } = renderLayout({ ...prototypeProps, onStartPipeline });

      await user.click(screen.getByRole("button", { name: "Revise" }));

      expect(onStartPipeline.mock.calls[0][4]).toStrictEqual({ _display_title: "tweak it" });
    });

    it("does nothing without a prototype on screen", async () => {
      const onStartPipeline = vi.fn();
      const { user } = renderLayout({
        contentSourceRunType: "prototype" as WorkflowType,
        onStartPipeline,
      });

      await user.click(screen.getByRole("button", { name: "Revise" }));

      expect(onStartPipeline).not.toHaveBeenCalled();
    });
  });

  describe("app builder", () => {
    const appProps = { contentSourceRunType: "app_builder" as WorkflowType };

    it("restarts with the blueprint capped at 40000 characters", async () => {
      const onStartPipeline = vi.fn();
      const { user } = renderLayout({
        ...appProps,
        userStoryContent: "b".repeat(45000),
        contentSourceRunId: "run-src",
        onStartPipeline,
      });

      await user.click(screen.getByRole("button", { name: "Revise" }));

      expect(onStartPipeline).toHaveBeenCalledWith(
        "app_builder_revision",
        `=== EXISTING APP BLUEPRINT ===\n${"b".repeat(40000)}\n=== END EXISTING BLUEPRINT ===\n\n` +
          "=== REVISION REQUEST ===\ntweak it\n=== END REQUEST ===",
        undefined,
        [],
        { source_workflow_run_id: "run-src", _display_title: "tweak it" },
      );
    });

    it("does nothing without a blueprint on screen", async () => {
      const onStartPipeline = vi.fn();
      const { user } = renderLayout({ ...appProps, onStartPipeline });

      await user.click(screen.getByRole("button", { name: "Revise" }));

      expect(onStartPipeline).not.toHaveBeenCalled();
    });
  });

  describe("custom workflow", () => {
    const customProps = { contentSourceRunType: "custom" as WorkflowType };

    it("launches a custom revision of the on-screen run and attaches it", async () => {
      const onResetPipeline = vi.fn();
      const onRevisionLaunched = vi.fn();
      const { user } = renderLayout({
        ...customProps,
        contentSourceRunId: "run-src",
        onResetPipeline,
        onRevisionLaunched,
      });

      await user.click(screen.getByRole("button", { name: "Revise" }));

      expect(postRevision).toHaveBeenCalledWith("tok", "run-src", {
        target_artifact_type: "custom_output",
        instruction: "tweak it",
      });
      await waitFor(() => expect(attachRun).toHaveBeenCalledWith("rev-1"));
      expect(onRevisionLaunched).toHaveBeenCalledWith("rev-1");
      expect(onResetPipeline).toHaveBeenCalledTimes(1);
    });

    it("attaches nothing when the revision returns no run id", async () => {
      vi.mocked(postRevision).mockResolvedValue({ run_id: "" });
      const { user } = renderLayout({ ...customProps, contentSourceRunId: "run-src" });

      await user.click(screen.getByRole("button", { name: "Revise" }));

      await waitFor(() => expect(postRevision).toHaveBeenCalledTimes(1));
      expect(attachRun).not.toHaveBeenCalled();
    });

    it("logs a rejected custom revision", async () => {
      const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
      const failure = new Error("revision failed");
      vi.mocked(postRevision).mockRejectedValue(failure);
      const { user } = renderLayout({ ...customProps, contentSourceRunId: "run-src" });

      await user.click(screen.getByRole("button", { name: "Revise" }));

      await waitFor(() => expect(errorSpy).toHaveBeenCalledWith("postRevision (custom) failed", failure));
      errorSpy.mockRestore();
    });

    it("does nothing without an on-screen run", async () => {
      const onResetPipeline = vi.fn();
      const { user } = renderLayout({ ...customProps, onResetPipeline });

      await user.click(screen.getByRole("button", { name: "Revise" }));

      expect(postRevision).not.toHaveBeenCalled();
      expect(onResetPipeline).not.toHaveBeenCalled();
    });
  });
});

describe("DashboardLayout chain from the lane", () => {
  it("offers the catalog's chain targets for the viewed run type", () => {
    renderLayout();

    expect(screen.getByRole("button", { name: "Chain prototype" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Chain app_builder" })).toBeInTheDocument();
  });

  describe("wizard target", () => {
    it("hands the run context to the wizard through sessionStorage and navigates to it", async () => {
      const { user } = renderLayout({ contentSourceRunId: "run-src" });

      await user.click(screen.getByRole("button", { name: "Chain prototype" }));

      expect(getChainContext).toHaveBeenCalledWith("tok", "run-src");
      expect(sessionStorage.getItem(CHAIN_FROM_KEY)).toBe("user_stories");
      expect(sessionStorage.getItem(CHAIN_SOURCE_RUN_ID_KEY)).toBe("run-src");
      expect(sessionStorage.getItem(CHAIN_CONTEXT_BLOCK_KEY)).toBe("CTX");
      expect(sessionStorage.getItem(CHAIN_BRIEF_KEY)).toBe("ctx brief");
      expect(router.push).toHaveBeenCalledWith("/workflow/create?mode=prototype");
    });

    it("clears a stale context block when the source run has none", async () => {
      sessionStorage.setItem(CHAIN_CONTEXT_BLOCK_KEY, "STALE");
      vi.mocked(getChainContext).mockResolvedValue({ brief: "ctx brief", context_block: "" } as Awaited<
        ReturnType<typeof getChainContext>
      >);
      const { user } = renderLayout({ contentSourceRunId: "run-src" });

      await user.click(screen.getByRole("button", { name: "Chain prototype" }));

      expect(sessionStorage.getItem(CHAIN_CONTEXT_BLOCK_KEY)).toBeNull();
      expect(router.push).toHaveBeenCalledWith("/workflow/create?mode=prototype");
    });

    it("still navigates with an empty brief when the context cannot be fetched", async () => {
      vi.mocked(getChainContext).mockRejectedValue(new Error("offline"));
      const { user } = renderLayout({ contentSourceRunId: "run-src" });

      await user.click(screen.getByRole("button", { name: "Chain prototype" }));

      await waitFor(() => expect(router.push).toHaveBeenCalledWith("/workflow/create?mode=prototype"));
      expect(sessionStorage.getItem(CHAIN_BRIEF_KEY)).toBe("");
    });

    it("skips the context fetch when there is no session token", async () => {
      vi.mocked(getToken).mockReturnValue(null);
      const { user } = renderLayout({ contentSourceRunId: "run-src" });

      await user.click(screen.getByRole("button", { name: "Chain prototype" }));

      expect(getChainContext).not.toHaveBeenCalled();
      expect(sessionStorage.getItem(CHAIN_SOURCE_RUN_ID_KEY)).toBe("run-src");
      expect(router.push).toHaveBeenCalledWith("/workflow/create?mode=prototype");
    });

    it("clears the source run key when no run is known", async () => {
      sessionStorage.setItem(CHAIN_SOURCE_RUN_ID_KEY, "stale-run");
      const { user } = renderLayout({ contentSourceRunId: null });

      await user.click(screen.getByRole("button", { name: "Chain prototype" }));

      expect(getChainContext).not.toHaveBeenCalled();
      expect(sessionStorage.getItem(CHAIN_SOURCE_RUN_ID_KEY)).toBeNull();
      expect(router.push).toHaveBeenCalledWith("/workflow/create?mode=prototype");
    });
  });

  describe("direct target", () => {
    it("starts the chained run with the source run's brief and parent link", async () => {
      const onResetPipeline = vi.fn();
      const onStartPipeline = vi.fn();
      const { user } = renderLayout({ contentSourceRunId: "run-src", onResetPipeline, onStartPipeline });

      await user.click(screen.getByRole("button", { name: "Chain app_builder" }));

      expect(getChainContext).toHaveBeenCalledWith("tok", "run-src");
      expect(onResetPipeline).toHaveBeenCalledTimes(1);
      expect(onStartPipeline).toHaveBeenCalledWith("app_builder", "ctx brief", [], [], {
        _display_title: "ctx brief",
        source_workflow_run_id: "run-src",
      });
      expect(onResetPipeline.mock.invocationCallOrder[0]).toBeLessThan(
        onStartPipeline.mock.invocationCallOrder[0],
      );
      expect(region("Run lane")).toBeInTheDocument();
    });

    it("falls back to the newest completed run of the type when none is on screen", async () => {
      const onStartPipeline = vi.fn();
      const { user } = renderLayout({
        contentSourceRunId: null,
        onStartPipeline,
        recentRuns: [
          { ...HISTORY_RUN, id: "failed-run", status: "failed" },
          { ...HISTORY_RUN, id: "recent-1" },
        ],
      });

      await user.click(screen.getByRole("button", { name: "Chain app_builder" }));

      expect(getChainContext).toHaveBeenCalledWith("tok", "recent-1");
      expect(onStartPipeline.mock.calls[0][4]).toStrictEqual({
        _display_title: "ctx brief",
        source_workflow_run_id: "recent-1",
      });
    });

    it("starts with an empty brief and no parent link when no source run exists", async () => {
      const onStartPipeline = vi.fn();
      const { user } = renderLayout({ contentSourceRunId: null, onStartPipeline });

      await user.click(screen.getByRole("button", { name: "Chain app_builder" }));

      expect(getChainContext).not.toHaveBeenCalled();
      expect(onStartPipeline).toHaveBeenCalledWith("app_builder", "", [], [], { _display_title: "" });
    });

    it("starts with an empty brief when the context cannot be fetched", async () => {
      vi.mocked(getChainContext).mockRejectedValue(new Error("offline"));
      const onStartPipeline = vi.fn();
      const { user } = renderLayout({ contentSourceRunId: "run-src", onStartPipeline });

      await user.click(screen.getByRole("button", { name: "Chain app_builder" }));

      await waitFor(() => expect(onStartPipeline).toHaveBeenCalledTimes(1));
      expect(onStartPipeline).toHaveBeenCalledWith("app_builder", "", [], [], {
        _display_title: "",
        source_workflow_run_id: "run-src",
      });
    });

    it("skips the context fetch without a session token", async () => {
      vi.mocked(getToken).mockReturnValue(null);
      const onStartPipeline = vi.fn();
      const { user } = renderLayout({ contentSourceRunId: "run-src", onStartPipeline });

      await user.click(screen.getByRole("button", { name: "Chain app_builder" }));

      expect(getChainContext).not.toHaveBeenCalled();
      expect(onStartPipeline).toHaveBeenCalledTimes(1);
    });

    it("shows the execution view without starting when no start handler is supplied", async () => {
      const onResetPipeline = vi.fn();
      const { user } = renderLayout({ contentSourceRunId: "run-src", onResetPipeline, onStartPipeline: undefined });

      await user.click(screen.getByRole("button", { name: "Chain app_builder" }));

      expect(onResetPipeline).toHaveBeenCalledTimes(1);
      expect(region("Run lane")).toBeInTheDocument();
    });

    it("holds the chained start until the connection returns, then starts once", async () => {
      const onStartPipeline = vi.fn();
      const { user, rerenderLayout } = renderLayout({
        contentSourceRunId: "run-src",
        onStartPipeline,
        connectionStatus: "reconnecting",
      });

      await user.click(screen.getByRole("button", { name: "Chain app_builder" }));
      await waitFor(() => expect(getChainContext).toHaveBeenCalledTimes(1));
      expect(onStartPipeline).not.toHaveBeenCalled();

      rerenderLayout({ contentSourceRunId: "run-src", onStartPipeline, connectionStatus: "connected" });

      expect(onStartPipeline).toHaveBeenCalledTimes(1);
      expect(onStartPipeline).toHaveBeenCalledWith("app_builder", "ctx brief", [], [], {
        _display_title: "ctx brief",
        source_workflow_run_id: "run-src",
      });
    });
  });
});

describe("DashboardLayout chain from history", () => {
  it("hands the historical run to the wizard through sessionStorage", async () => {
    const { user } = renderLayout({ initialMainView: "history" });

    await user.click(screen.getByRole("button", { name: "Chain prototype from history" }));

    expect(getChainContext).toHaveBeenCalledWith("tok", "hist-1");
    expect(sessionStorage.getItem(CHAIN_FROM_KEY)).toBe("user_stories");
    expect(sessionStorage.getItem(CHAIN_SOURCE_RUN_ID_KEY)).toBe("hist-1");
    expect(sessionStorage.getItem(CHAIN_CONTEXT_BLOCK_KEY)).toBe("CTX");
    expect(sessionStorage.getItem(CHAIN_BRIEF_KEY)).toBe("Original brief");
    expect(router.push).toHaveBeenCalledWith("/workflow/create?mode=prototype");
  });

  it("clears a stale context block when the historical run has none", async () => {
    sessionStorage.setItem(CHAIN_CONTEXT_BLOCK_KEY, "STALE");
    vi.mocked(getChainContext).mockResolvedValue({ brief: "ctx brief", context_block: "" } as Awaited<
      ReturnType<typeof getChainContext>
    >);
    const { user } = renderLayout({ initialMainView: "history" });

    await user.click(screen.getByRole("button", { name: "Chain prototype from history" }));

    expect(sessionStorage.getItem(CHAIN_CONTEXT_BLOCK_KEY)).toBeNull();
  });

  it("clears the source keys for a run without an id", async () => {
    sessionStorage.setItem(CHAIN_SOURCE_RUN_ID_KEY, "stale-run");
    sessionStorage.setItem(CHAIN_CONTEXT_BLOCK_KEY, "STALE");
    const { user } = renderLayout({ initialMainView: "history" });

    await user.click(screen.getByRole("button", { name: "Chain prototype from unsaved run" }));

    expect(getChainContext).not.toHaveBeenCalled();
    expect(sessionStorage.getItem(CHAIN_SOURCE_RUN_ID_KEY)).toBeNull();
    expect(sessionStorage.getItem(CHAIN_CONTEXT_BLOCK_KEY)).toBeNull();
    expect(router.push).toHaveBeenCalledWith("/workflow/create?mode=prototype");
  });

  it("starts a direct chained run from the historical run and shows the execution view", async () => {
    const onResetPipeline = vi.fn();
    const onStartPipeline = vi.fn();
    const { user } = renderLayout({ initialMainView: "history", onResetPipeline, onStartPipeline });

    await user.click(screen.getByRole("button", { name: "Chain app from history" }));

    expect(region("Run lane")).toBeInTheDocument();
    expect(onResetPipeline).toHaveBeenCalledTimes(1);
    expect(onStartPipeline).toHaveBeenCalledWith("app_builder", "Original brief", [], [], {
      _display_title: "Original brief",
      source_workflow_run_id: "hist-1",
    });
  });

  it("adds the saved workflow id when the user picked a saved chain target", async () => {
    const onStartPipeline = vi.fn();
    const { user } = renderLayout({ initialMainView: "history", onStartPipeline });

    await user.click(screen.getByRole("button", { name: "Chain app with saved workflow" }));

    expect(onStartPipeline.mock.calls[0][4]).toStrictEqual({
      _display_title: "Original brief",
      source_workflow_run_id: "hist-1",
      user_workflow_id: "uw-1",
    });
  });

  it("uses the fetched brief when the historical run has no input", async () => {
    const onStartPipeline = vi.fn();
    const { user } = renderLayout({ initialMainView: "history", onStartPipeline });

    await user.click(screen.getByRole("button", { name: "Chain app from empty brief" }));

    expect(onStartPipeline).toHaveBeenCalledWith("app_builder", "ctx brief", [], [], {
      _display_title: "ctx brief",
      source_workflow_run_id: "hist-1",
    });
  });

  it("holds the chained start until the connection returns, then starts once", async () => {
    const onStartPipeline = vi.fn();
    const { user, rerenderLayout } = renderLayout({
      initialMainView: "history",
      onStartPipeline,
      connectionStatus: "reconnecting",
    });

    await user.click(screen.getByRole("button", { name: "Chain app from history" }));
    expect(onStartPipeline).not.toHaveBeenCalled();

    rerenderLayout({ initialMainView: "history", onStartPipeline, connectionStatus: "connected" });

    expect(onStartPipeline).toHaveBeenCalledTimes(1);
    expect(onStartPipeline).toHaveBeenCalledWith("app_builder", "Original brief", [], [], {
      _display_title: "Original brief",
      source_workflow_run_id: "hist-1",
    });
  });

  it("starts with an empty brief when the context cannot be fetched and the run has no input", async () => {
    vi.mocked(getChainContext).mockRejectedValue(new Error("offline"));
    const onStartPipeline = vi.fn();
    const { user } = renderLayout({ initialMainView: "history", onStartPipeline });

    await user.click(screen.getByRole("button", { name: "Chain app from empty brief" }));

    await waitFor(() => expect(onStartPipeline).toHaveBeenCalledTimes(1));
    expect(onStartPipeline.mock.calls[0][1]).toBe("");
  });

  it("shows the execution view without starting when no start handler is supplied", async () => {
    const onResetPipeline = vi.fn();
    const { user } = renderLayout({ initialMainView: "history", onResetPipeline, onStartPipeline: undefined });

    await user.click(screen.getByRole("button", { name: "Chain app from history" }));

    expect(region("Run lane")).toBeInTheDocument();
    expect(onResetPipeline).toHaveBeenCalledTimes(1);
  });
});

