/**
 * DashboardLayout — launch half: what happens when the input view's Run fires
 * (reset, display title, connected vs. disconnected start, rejected launch).
 *
 * Mocked at system boundaries only: next/navigation, motion/react, @/lib/api,
 * the SSE run connection and the heavy leaf pages. The IdeaInputPage stub
 * renders a real Run button and exposes its props so the resolved launch
 * promise can be observed. Real: parseRunInput, SkillsHooks provider,
 * useNotifications.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import React from "react";
import { act, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders, screen } from "@/test/renderWithProviders";
import type { PipelineRunState, WorkflowType } from "@/types/index";
import type { IdeaInputPage } from "@/components/workflow/IdeaInputPage";
import type { PreviewPanel } from "@/components/preview/PreviewPanel";
import type { ComposerPage } from "@/components/workflow/composer/ComposerPage";

type IdeaProps = React.ComponentProps<typeof IdeaInputPage>;
type PreviewProps = React.ComponentProps<typeof PreviewPanel>;
type ComposerProps = React.ComponentProps<typeof ComposerPage>;

interface RunArgs {
  message: string;
  agentIds: string[];
  type: WorkflowType;
  extra?: Record<string, unknown>;
}

const { router, probe } = vi.hoisted(() => ({
  router: { push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() },
  probe: {
    ideaProps: undefined as IdeaProps | undefined,
    run: undefined as RunArgs | undefined,
  },
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
    getToken: () => "tok",
    getRunFamily: () => Promise.resolve({ root_id: "", members: [] }),
    getWorkflow: vi.fn(),
    postCancel: vi.fn(),
    postResume: vi.fn(),
  };
});

vi.mock("@/providers/RunConnectionProvider", () => ({
  useRunConnection: () => ({ attachRun: vi.fn() }),
}));

vi.mock("@/components/layout/AppHeader", () => ({ AppHeader: () => <header /> }));
vi.mock("@/components/catalog/HomeLaunchGrid", () => ({
  HomeLaunchGrid: () => <section aria-label="Home grid" />,
}));
vi.mock("@/components/library/LibraryPage", () => ({ LibraryPage: () => null }));
vi.mock("@/components/history/WorkflowHistory", () => ({ WorkflowHistory: () => null }));
vi.mock("@/components/settings/AccountSettings", () => ({ AccountSettings: () => null }));
vi.mock("@/components/analytics/AnalyticsPage", () => ({ AnalyticsPage: () => null }));
vi.mock("@/components/savedworkflows/SavedWorkflowsPage", () => ({ SavedWorkflowsPage: () => null }));
vi.mock("@/components/workflow/composer/ComposerPage", () => ({
  ComposerPage: (props: ComposerProps) => (
    <section aria-label="Composer page">
      <button
        type="button"
        onClick={() => props.onRun?.("custom" as WorkflowType, "Composed brief", ["c1", "c2"], { limit: 3 })}
      >
        Composer run
      </button>
    </section>
  ),
}));
vi.mock("@/components/ui/CompletionToast", () => ({ CompletionToast: () => null }));
vi.mock("@/components/chat/RunChatLane", () => ({
  RunChatLane: () => <section aria-label="Run lane" />,
}));
vi.mock("@/components/preview/PreviewPanel", () => ({
  PreviewPanel: (props: PreviewProps) => (
    <section aria-label="Preview panel">Raw type: {props.rawPipelineType}</section>
  ),
}));

vi.mock("@/components/workflow/IdeaInputPage", () => ({
  IdeaInputPage: (props: IdeaProps) => {
    probe.ideaProps = props;
    return (
      <section aria-label="Idea input page">
        <button
          type="button"
          onClick={() => {
            const run = probe.run;
            if (run) props.onRun(run.message, run.agentIds, run.type, run.extra);
          }}
        >
          Run
        </button>
      </section>
    );
  },
}));

import { DashboardLayout } from "./DashboardLayout";
import type { DashboardLayoutProps } from "./DashboardLayout";

function idlePipelineState(): PipelineRunState {
  return {
    isRunning: false,
    pipeline_type: "user_stories",
    agents: [],
    currentAgentIndex: -1,
    totalDuration: null,
    completedCount: 0,
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
    initialMainView: "input",
    initialWorkflowType: "user_stories",
    pipelineState: idlePipelineState(),
    ...overrides,
  };
}

function renderLayout(overrides: Partial<DashboardLayoutProps> = {}) {
  const user = userEvent.setup();
  const props = baseProps(overrides);
  const view = renderWithProviders(<DashboardLayout {...props} />);
  const rerenderLayout = (next: Partial<DashboardLayoutProps>) =>
    view.rerender(<DashboardLayout {...props} {...next} />);
  return { user, props, rerenderLayout, ...view };
}

function stageRun(overrides: Partial<RunArgs> = {}): RunArgs {
  const run: RunArgs = {
    message: "Build a todo app",
    agentIds: ["a1"],
    type: "user_stories" as WorkflowType,
    ...overrides,
  };
  probe.run = run;
  return run;
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
  probe.ideaProps = undefined;
  probe.run = undefined;
});

afterEach(() => {
  vi.useRealTimers();
});

describe("DashboardLayout launch", () => {
  describe("connected run", () => {
    it("resets the pipeline, starts the run and shows the execution view", async () => {
      const onResetPipeline = vi.fn();
      const onStartPipeline = vi.fn();
      const { user } = renderLayout({ onResetPipeline, onStartPipeline });
      stageRun({ extra: { gate_agent_ids: ["g1"] } });

      await user.click(screen.getByRole("button", { name: "Run" }));

      expect(onResetPipeline).toHaveBeenCalledTimes(1);
      expect(onStartPipeline).toHaveBeenCalledTimes(1);
      expect(onStartPipeline).toHaveBeenCalledWith(
        "user_stories",
        "Build a todo app",
        ["a1"],
        [],
        { gate_agent_ids: ["g1"], _display_title: "Build a todo app" },
      );
      expect(onResetPipeline.mock.invocationCallOrder[0]).toBeLessThan(
        onStartPipeline.mock.invocationCallOrder[0],
      );
      expect(region("Run lane")).toBeInTheDocument();
      expect(screen.queryByRole("region", { name: "Idea input page" })).not.toBeInTheDocument();
    });

    it("launches the resolved pipeline type rather than the type the panel was opened with", async () => {
      const onStartPipeline = vi.fn();
      const { user } = renderLayout({
        onStartPipeline,
        initialWorkflowType: "migration",
        pipelineState: undefined,
      });
      stageRun({ type: "dotnet_to_azure" as WorkflowType });

      await user.click(screen.getByRole("button", { name: "Run" }));

      expect(onStartPipeline).toHaveBeenCalledWith(
        "dotnet_to_azure",
        "Build a todo app",
        ["a1"],
        [],
        { _display_title: "Build a todo app" },
      );
      expect(screen.getByText("Raw type: dotnet_to_azure")).toBeInTheDocument();
    });

    it("shows the execution view without starting anything when no start handler is supplied", async () => {
      const onResetPipeline = vi.fn();
      const { user } = renderLayout({ onResetPipeline, onStartPipeline: undefined });
      stageRun();

      await user.click(screen.getByRole("button", { name: "Run" }));

      expect(onResetPipeline).toHaveBeenCalledTimes(1);
      expect(region("Run lane")).toBeInTheDocument();
    });
  });

  describe("display title", () => {
    it("caps the title at 60 characters", async () => {
      const onStartPipeline = vi.fn();
      const { user } = renderLayout({ onStartPipeline });
      const message = "x".repeat(80);
      stageRun({ message });

      await user.click(screen.getByRole("button", { name: "Run" }));

      const extra = onStartPipeline.mock.calls[0][4] as { _display_title: string };
      expect(extra._display_title).toBe("x".repeat(60));
      expect(onStartPipeline.mock.calls[0][1]).toBe(message);
    });

    it("uses the revision instruction instead of the surrounding context blocks", async () => {
      const onStartPipeline = vi.fn();
      const { user } = renderLayout({ onStartPipeline });
      stageRun({
        message:
          "=== EXISTING PRODUCT BACKLOG ===\nold backlog\n=== END EXISTING BACKLOG ===\n\n" +
          "=== REVISION REQUEST ===\nTighten the auth stories\n=== END REQUEST ===",
      });

      await user.click(screen.getByRole("button", { name: "Run" }));

      expect(onStartPipeline.mock.calls[0][4]).toStrictEqual({ _display_title: "Tighten the auth stories" });
    });

    it("falls back to the original brief inside a chain-context block", async () => {
      const onStartPipeline = vi.fn();
      const { user } = renderLayout({ onStartPipeline });
      stageRun({
        message:
          "=== CONTEXT FROM PREVIOUS PIPELINE (user_stories) ===\n" +
          "Original Brief: Ship a CRM\nsecond line\n=== END PREVIOUS CONTEXT ===",
      });

      await user.click(screen.getByRole("button", { name: "Run" }));

      expect(onStartPipeline.mock.calls[0][4]).toStrictEqual({ _display_title: "Ship a CRM" });
    });

    it("passes the caller's extra params through untouched when no title can be derived", async () => {
      const onStartPipeline = vi.fn();
      const { user } = renderLayout({ onStartPipeline });
      stageRun({ message: "   ", extra: { gate_agent_ids: ["g1"] } });

      await user.click(screen.getByRole("button", { name: "Run" }));

      expect(onStartPipeline.mock.calls[0][4]).toStrictEqual({ gate_agent_ids: ["g1"] });
    });
  });

  describe("disconnected run", () => {
    it("waits for the connection and then starts exactly once", async () => {
      const onStartPipeline = vi.fn();
      const onResetPipeline = vi.fn();
      const { user, rerenderLayout } = renderLayout({
        onStartPipeline,
        onResetPipeline,
        connectionStatus: "reconnecting",
      });
      stageRun({ extra: { gate_agent_ids: ["g1"] } });

      await user.click(screen.getByRole("button", { name: "Run" }));

      expect(onStartPipeline).not.toHaveBeenCalled();
      expect(onResetPipeline).toHaveBeenCalledTimes(1);
      expect(region("Run lane")).toBeInTheDocument();

      rerenderLayout({ onStartPipeline, onResetPipeline, connectionStatus: "connected" });

      expect(onStartPipeline).toHaveBeenCalledTimes(1);
      expect(onStartPipeline).toHaveBeenCalledWith(
        "user_stories",
        "Build a todo app",
        ["a1"],
        [],
        { gate_agent_ids: ["g1"], _display_title: "Build a todo app" },
      );

      rerenderLayout({ onStartPipeline, onResetPipeline, connectionStatus: "reconnecting" });
      rerenderLayout({ onStartPipeline, onResetPipeline, connectionStatus: "connected" });

      expect(onStartPipeline).toHaveBeenCalledTimes(1);
    });
  });

  describe("composer run-once", () => {
    it("resets the pipeline and starts the composed run with the composer's own arguments", async () => {
      const onResetPipeline = vi.fn();
      const onStartPipeline = vi.fn();
      const { user } = renderLayout({ initialMainView: "composer", onResetPipeline, onStartPipeline });

      await user.click(screen.getByRole("button", { name: "Composer run" }));

      expect(onResetPipeline).toHaveBeenCalledTimes(1);
      expect(onStartPipeline).toHaveBeenCalledTimes(1);
      expect(onStartPipeline).toHaveBeenCalledWith("custom", "Composed brief", ["c1", "c2"], [], { limit: 3 });
      expect(onResetPipeline.mock.invocationCallOrder[0]).toBeLessThan(
        onStartPipeline.mock.invocationCallOrder[0],
      );
    });

    it("only resets when no start handler is supplied", async () => {
      const onResetPipeline = vi.fn();
      const { user } = renderLayout({ initialMainView: "composer", onResetPipeline });

      await user.click(screen.getByRole("button", { name: "Composer run" }));

      expect(onResetPipeline).toHaveBeenCalledTimes(1);
    });
  });

  describe("wizard-staged run while disconnected", () => {
    const wizardParams = {
      brief: "Wizard brief",
      templateId: "tpl-1",
      designSystemId: "ds-1",
      discovery: null,
    };

    it.each([
      { prop: "pendingOdProtoParams", type: "prototype" },
      { prop: "pendingOdPptParams", type: "ppt" },
    ] as const)("holds the $type launch until the connection returns", ({ prop, type }) => {
      const onStartPipeline = vi.fn();
      const params = { ...wizardParams };
      const { rerenderLayout } = renderLayout({
        initialMainView: "execution",
        onStartPipeline,
        connectionStatus: "reconnecting",
        [prop]: params,
      });

      expect(onStartPipeline).not.toHaveBeenCalled();
      expect(region("Run lane")).toBeInTheDocument();

      rerenderLayout({ initialMainView: "execution", onStartPipeline, connectionStatus: "connected", [prop]: params });

      expect(onStartPipeline).toHaveBeenCalledTimes(1);
      expect(onStartPipeline).toHaveBeenCalledWith(type, "Wizard brief", [], [], {
        template_id: "tpl-1",
        design_system_id: "ds-1",
        discovery: null,
      });
    });
  });

  describe("rejected launch", () => {
    it("returns to the input view when the launch is not accepted", async () => {
      const onStartPipeline = vi.fn().mockResolvedValue(null); // ISS-1137: null = the launch was refused
      renderLayout({ onStartPipeline });
      stageRun();
      let accepted: unknown;

      await act(async () => {
        accepted = await probe.ideaProps?.onRun("Build a todo app", ["a1"], "user_stories" as WorkflowType);
      });

      expect(accepted).toBeNull();
      expect(await screen.findByRole("region", { name: "Idea input page" })).toBeInTheDocument();
      expect(screen.queryByRole("region", { name: "Run lane" })).not.toBeInTheDocument();
    });

    it("stays on the execution view when the launch is accepted", async () => {
      const onStartPipeline = vi.fn().mockResolvedValue("run-1"); // ISS-1137: the launched run id
      renderLayout({ onStartPipeline });
      let accepted: unknown;

      await act(async () => {
        accepted = await probe.ideaProps?.onRun("Build a todo app", ["a1"], "user_stories" as WorkflowType);
      });

      expect(accepted).toBe("run-1");
      expect(region("Run lane")).toBeInTheDocument();
      expect(screen.queryByRole("region", { name: "Idea input page" })).not.toBeInTheDocument();
    });
  });
});
