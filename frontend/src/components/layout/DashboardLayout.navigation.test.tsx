/**
 * DashboardLayout — navigation half (header routes, cold start / re-sync,
 * feature selection, Back + unsaved-changes guard, connection banners, saved
 * workflow launch).
 *
 * Mocked at system boundaries only: next/navigation, motion/react, @/lib/api
 * (token + run family), the SSE run connection, and the heavy leaf pages. Each
 * leaf stub renders real semantic controls so tests drive DashboardLayout the
 * way a user does. Real: routes, goBackOr, the wizard-path selector, the
 * SkillsHooks provider, useNotifications.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { MockInstance } from "vitest";
import React from "react";
import { cleanup, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders, screen } from "@/test/renderWithProviders";
import type { PipelineRunState, WorkflowType } from "@/types/index";
import type { UserWorkflowSummary } from "@/lib/api";
import type { AppHeader } from "@/components/layout/AppHeader";
import type { HomeLaunchGrid } from "@/components/catalog/HomeLaunchGrid";
import type { IdeaInputPage } from "@/components/workflow/IdeaInputPage";
import type { ComposerPage } from "@/components/workflow/composer/ComposerPage";
import type { SavedWorkflowsPage } from "@/components/savedworkflows/SavedWorkflowsPage";
import type { AccountSettings } from "@/components/settings/AccountSettings";
import type { AnalyticsPage } from "@/components/analytics/AnalyticsPage";
import type { WorkflowHistory } from "@/components/history/WorkflowHistory";
import type { PreviewPanel } from "@/components/preview/PreviewPanel";

type HeaderProps = React.ComponentProps<typeof AppHeader>;
type GridProps = React.ComponentProps<typeof HomeLaunchGrid>;
type IdeaProps = React.ComponentProps<typeof IdeaInputPage>;
type ComposerProps = React.ComponentProps<typeof ComposerPage>;
type SavedPageProps = React.ComponentProps<typeof SavedWorkflowsPage>;
type SettingsProps = React.ComponentProps<typeof AccountSettings>;
type AnalyticsProps = React.ComponentProps<typeof AnalyticsPage>;
type HistoryProps = React.ComponentProps<typeof WorkflowHistory>;
type PreviewProps = React.ComponentProps<typeof PreviewPanel>;

const { router, probe } = vi.hoisted(() => ({
  router: { push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() },
  probe: {
    settingsInstances: 0,
    savedToLaunch: undefined as UserWorkflowSummary | undefined,
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
  // whole view (and drop input focus) each time DashboardLayout re-renders.
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

vi.mock("@/components/layout/AppHeader", () => ({
  AppHeader: (props: HeaderProps) => (
    <header>
      <p>Header page: {props.currentPage}</p>
      <button type="button" onClick={() => props.onNavigate("home")}>Go Home</button>
      <button type="button" onClick={() => props.onNavigate("library")}>Go Library</button>
      <button type="button" onClick={() => props.onNavigate("history")}>Go History</button>
      <button type="button" onClick={() => props.onNavigate("settings")}>Go Settings</button>
      <button type="button" onClick={() => props.onNavigate("settings", { settingsSection: "security" })}>
        Go Settings Security
      </button>
      <button type="button" onClick={() => props.onNavigate("analytics")}>Go Analytics</button>
      <button type="button" onClick={() => props.onNavigate("saved-workflows")}>Go Saved Workflows</button>
      <button type="button" onClick={() => props.onNavigate("catalog")}>Go Catalog</button>
    </header>
  ),
}));

const GRID_TYPES = ["user_stories", "app_builder", "dotnet_to_azure", "custom", "ppt", "prototype", "a b"];
vi.mock("@/components/catalog/HomeLaunchGrid", () => ({
  HomeLaunchGrid: (props: GridProps) => (
    <section aria-label="Home grid">
      <label>
        Brief
        <input type="text" value={props.brief ?? ""} onChange={(e) => props.onBriefChange?.(e.target.value)} />
      </label>
      {GRID_TYPES.map((type) => (
        <button key={type} type="button" onClick={() => props.onSelectFeature(type as WorkflowType)}>
          Select {type}
        </button>
      ))}
      <button type="button" onClick={props.onBuild}>Build</button>
    </section>
  ),
}));

vi.mock("@/components/library/LibraryPage", () => ({
  LibraryPage: () => <section aria-label="Library page" />,
}));

vi.mock("@/components/history/WorkflowHistory", () => ({
  WorkflowHistory: (props: HistoryProps) => (
    <section aria-label="History page">
      <button type="button" onClick={props.onBack}>History back</button>
    </section>
  ),
}));

vi.mock("@/components/settings/AccountSettings", () => ({
  AccountSettings: (props: SettingsProps) => {
    const [instance] = React.useState(() => ++probe.settingsInstances);
    return (
      <section aria-label="Settings page">
        <p>Settings section: {props.initialSection}</p>
        <p>Settings instance: {instance}</p>
        <button type="button" onClick={props.onBack}>Settings back</button>
      </section>
    );
  },
}));

vi.mock("@/components/analytics/AnalyticsPage", () => ({
  AnalyticsPage: (props: AnalyticsProps) => (
    <section aria-label="Analytics page">
      <button type="button" onClick={props.onBack}>Analytics back</button>
    </section>
  ),
}));

vi.mock("@/components/savedworkflows/SavedWorkflowsPage", () => ({
  SavedWorkflowsPage: (props: SavedPageProps) => (
    <section aria-label="Saved workflows page">
      <button
        type="button"
        onClick={() => {
          if (probe.savedToLaunch) props.onLaunchSaved?.(probe.savedToLaunch);
        }}
      >
        Launch saved
      </button>
      <button type="button" onClick={props.onCreateNew}>Create new</button>
    </section>
  ),
}));

vi.mock("@/components/workflow/IdeaInputPage", () => ({
  IdeaInputPage: (props: IdeaProps) => (
    <section aria-label="Idea input page">
      <p>Input page: {props.workflowType}</p>
      <p>Initial input: [{props.initialInput ?? ""}]</p>
      <p>Initial agents: {JSON.stringify(props.initialAgentIds ?? null)}</p>
      <button type="button" onClick={props.onBack}>Input back</button>
      <button type="button" onClick={() => props.onRun("go", ["a1"], props.workflowType)}>Input run</button>
      <button
        type="button"
        onClick={() =>
          props.onOpenInCanvas?.({ agentIds: [], modelOverrides: {}, selections: {} })
        }
      >
        Open canvas
      </button>
    </section>
  ),
}));

vi.mock("@/components/workflow/composer/ComposerPage", () => ({
  ComposerPage: (props: ComposerProps) => (
    <section aria-label="Composer page">
      <p>Composer type: {props.workflowType}</p>
      <p>Composer name: [{props.initialName ?? ""}]</p>
      <p>Composer saved id: [{props.initialUserWorkflowId ?? ""}]</p>
      <p>Composer selections: {JSON.stringify(props.initialSelections ?? null)}</p>
      <button type="button" onClick={props.onBack}>Composer back</button>
      <button type="button" onClick={() => props.onUnsavedChange?.(true)}>Mark dirty</button>
      <button type="button" onClick={() => props.onUnsavedChange?.(false)}>Mark clean</button>
    </section>
  ),
}));

vi.mock("@/components/chat/RunChatLane", () => ({
  RunChatLane: () => <section aria-label="Run lane" />,
}));

vi.mock("@/components/preview/PreviewPanel", () => ({
  PreviewPanel: (props: PreviewProps) => (
    <section aria-label="Preview panel">Raw type: {props.rawPipelineType}</section>
  ),
}));

vi.mock("@/components/ui/CompletionToast", () => ({
  CompletionToast: () => null,
}));

import { DashboardLayout } from "./DashboardLayout";
import type { DashboardLayoutProps, SavedComposition } from "./DashboardLayout";

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
    pipelineState: idlePipelineState(),
    ...overrides,
  };
}

function savedFixture(overrides: Partial<UserWorkflowSummary> = {}): UserWorkflowSummary {
  return {
    id: "wf-1",
    name: "My workflow",
    base_pipeline_type: "user_stories",
    agent_ids: ["a1", "a2"],
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

function region(name: string): HTMLElement {
  return screen.getByRole("region", { name });
}

function queryRegion(name: string): HTMLElement | null {
  return screen.queryByRole("region", { name });
}

let historyLength: MockInstance<() => number>;

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  sessionStorage.clear();
  localStorage.clear();
  window.history.replaceState(null, "", "/");
  probe.settingsInstances = 0;
  probe.savedToLaunch = undefined;
  // jsdom history never shrinks, so pin the length instead of depending on test order.
  historyLength = vi.spyOn(window.history, "length", "get").mockReturnValue(1);
});

afterEach(() => {
  historyLength.mockRestore();
  vi.useRealTimers();
});

describe("DashboardLayout navigation", () => {
  describe("header navigation", () => {
    it.each([
      { button: "Go Home", header: "home", marker: "Home grid", path: "/dashboard" },
      { button: "Go Library", header: "library", marker: "Library page", path: "/library" },
      { button: "Go History", header: "history", marker: "History page", path: "/runs" },
      { button: "Go Settings", header: "settings", marker: "Settings page", path: "/settings/profile" },
      { button: "Go Analytics", header: "analytics", marker: "Analytics page", path: "/analytics" },
      { button: "Go Saved Workflows", header: "saved-workflows", marker: "Saved workflows page", path: "/workflows" },
    ])(
      "shows the $header view and pushes $path when $button is clicked",
      async ({ button, header, marker, path }) => {
        const { user } = renderLayout({ initialMainView: "execution" });
        expect(region("Run lane")).toBeInTheDocument();

        await user.click(screen.getByRole("button", { name: button }));

        expect(region(marker)).toBeInTheDocument();
        expect(queryRegion("Run lane")).not.toBeInTheDocument();
        expect(screen.getByText(`Header page: ${header}`)).toBeInTheDocument();
        expect(router.push).toHaveBeenCalledTimes(1);
        expect(router.push).toHaveBeenCalledWith(path);
      },
    );

    it("pushes the create route and leaves the content area empty when the catalog is opened", async () => {
      const { user } = renderLayout({ initialMainView: "execution" });

      await user.click(screen.getByRole("button", { name: "Go Catalog" }));

      expect(router.push).toHaveBeenCalledTimes(1);
      expect(router.push).toHaveBeenCalledWith("/create");
      expect(screen.getByText("Header page: catalog")).toBeInTheDocument();
      expect(queryRegion("Run lane")).not.toBeInTheDocument();
      expect(queryRegion("Home grid")).not.toBeInTheDocument();
    });
  });

  describe("settings tab requests", () => {
    it("remounts AccountSettings on every settings navigation and honors the requested tab", async () => {
      const { user } = renderLayout();

      await user.click(screen.getByRole("button", { name: "Go Settings Security" }));
      expect(screen.getByText("Settings section: security")).toBeInTheDocument();
      expect(screen.getByText("Settings instance: 1")).toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: "Go Settings" }));
      expect(screen.getByText("Settings section: profile")).toBeInTheDocument();
      expect(screen.getByText("Settings instance: 2")).toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: "Go Settings" }));
      expect(screen.getByText("Settings section: profile")).toBeInTheDocument();
      expect(screen.getByText("Settings instance: 3")).toBeInTheDocument();
    });

    it("opens on the URL-derived tab when cold-loaded with initialSettingsSection", () => {
      renderLayout({ initialMainView: "settings", initialSettingsSection: "model" });

      expect(screen.getByText("Settings section: model")).toBeInTheDocument();
      expect(screen.getByText("Settings instance: 1")).toBeInTheDocument();
    });

    it("remounts AccountSettings on the new tab when initialSettingsSection changes later", () => {
      const { rerenderLayout } = renderLayout({ initialMainView: "settings", initialSettingsSection: "profile" });
      expect(screen.getByText("Settings section: profile")).toBeInTheDocument();

      rerenderLayout({ initialMainView: "settings", initialSettingsSection: "security" });

      expect(screen.getByText("Settings section: security")).toBeInTheDocument();
      expect(screen.getByText("Settings instance: 2")).toBeInTheDocument();
    });
  });

  describe("cold start and URL re-sync", () => {
    it("follows initialMainView changes and ignores a change to undefined", () => {
      const { rerenderLayout } = renderLayout({ initialMainView: "analytics" });
      expect(region("Analytics page")).toBeInTheDocument();

      rerenderLayout({ initialMainView: "library" });
      expect(region("Library page")).toBeInTheDocument();
      expect(queryRegion("Analytics page")).not.toBeInTheDocument();

      rerenderLayout({ initialMainView: undefined });
      expect(region("Library page")).toBeInTheDocument();
    });

    it.each([
      { key: "prototype.pending", type: "prototype" },
      { key: "ppt.pending", type: "ppt" },
    ])("starts in the execution view for the staged $key run", ({ key, type }) => {
      sessionStorage.setItem(key, "1");

      renderLayout({ pipelineState: undefined });

      expect(region("Run lane")).toBeInTheDocument();
      expect(queryRegion("Home grid")).not.toBeInTheDocument();
      expect(screen.getByText(`Raw type: ${type}`)).toBeInTheDocument();
    });

    it("starts on the home grid when nothing is staged", () => {
      renderLayout();

      expect(region("Home grid")).toBeInTheDocument();
      expect(queryRegion("Run lane")).not.toBeInTheDocument();
    });

    it("opens the input view on the workflow named by the cold-loaded URL", () => {
      renderLayout({ initialMainView: "input", initialWorkflowType: "dotnet_to_azure" });

      expect(screen.getByText("Input page: dotnet_to_azure")).toBeInTheDocument();
    });

    it("prefers initialMainView over a staged run", () => {
      sessionStorage.setItem("ppt.pending", "1");

      renderLayout({ initialMainView: "library" });

      expect(region("Library page")).toBeInTheDocument();
      expect(queryRegion("Run lane")).not.toBeInTheDocument();
    });
  });

  describe("saved composition from the URL", () => {
    const composition: SavedComposition = {
      agentIds: ["a1"],
      modelOverrides: {},
      selections: { _wizard: { brief: "hidden" }, a1: { lever: 2 } },
      name: "Edited flow",
      id: "wf-9",
    };

    it("pre-loads the composer when a saved composition arrives after the first render", () => {
      const { rerenderLayout } = renderLayout({ initialMainView: "composer", initialSavedComposition: null });
      expect(screen.getByText("Composer name: []")).toBeInTheDocument();
      expect(screen.getByText("Composer saved id: []")).toBeInTheDocument();

      rerenderLayout({ initialMainView: "composer", initialSavedComposition: composition });

      expect(screen.getByText("Composer name: [Edited flow]")).toBeInTheDocument();
      expect(screen.getByText("Composer saved id: [wf-9]")).toBeInTheDocument();
    });

    it("hands the composer the saved selections without the wizard key", () => {
      renderLayout({ initialMainView: "composer", initialSavedComposition: composition });

      expect(screen.getByText('Composer selections: {"a1":{"lever":2}}')).toBeInTheDocument();
    });
  });

  describe("feature selection", () => {
    it.each([
      { type: "user_stories", path: "/create/user-stories" },
      { type: "app_builder", path: "/create/app" },
      { type: "dotnet_to_azure", path: "/create/dotnet_to_azure" },
      { type: "a b", path: "/create/a%20b" },
    ])("opens the input view for $type and pushes $path", async ({ type, path }) => {
      const { user } = renderLayout();

      await user.click(screen.getByRole("button", { name: `Select ${type}` }));

      expect(region("Idea input page")).toBeInTheDocument();
      expect(screen.getByText(`Input page: ${type}`)).toBeInTheDocument();
      expect(router.push).toHaveBeenCalledTimes(1);
      expect(router.push).toHaveBeenCalledWith(path);
    });

    it("opens the composer for the custom type", async () => {
      const { user } = renderLayout();

      await user.click(screen.getByRole("button", { name: "Select custom" }));

      expect(region("Composer page")).toBeInTheDocument();
      expect(screen.getByText("Composer type: custom")).toBeInTheDocument();
      expect(router.push).toHaveBeenCalledWith("/workflows/new");
    });

    it.each([
      { type: "ppt", path: "/workflow/create?mode=ppt" },
      { type: "prototype", path: "/workflow/create?mode=prototype" },
    ])("routes $type to its wizard and keeps the home grid", async ({ type, path }) => {
      const { user } = renderLayout();

      await user.click(screen.getByRole("button", { name: `Select ${type}` }));

      expect(router.push).toHaveBeenCalledTimes(1);
      expect(router.push).toHaveBeenCalledWith(path);
      expect(region("Home grid")).toBeInTheDocument();
      expect(queryRegion("Idea input page")).not.toBeInTheDocument();
    });

    it("carries the trimmed home brief into the input view", async () => {
      const { user } = renderLayout();

      await user.type(screen.getByRole("textbox", { name: "Brief" }), "  ship it  ");
      await user.click(screen.getByRole("button", { name: "Select user_stories" }));

      expect(screen.getByText("Initial input: [ship it]")).toBeInTheDocument();
    });

    it("hands an empty brief to the input view when the home brief is only whitespace", async () => {
      const { user } = renderLayout();

      await user.type(screen.getByRole("textbox", { name: "Brief" }), "   ");
      await user.click(screen.getByRole("button", { name: "Select user_stories" }));

      expect(screen.getByText("Initial input: []")).toBeInTheDocument();
    });

    it("opens the composer when Build is pressed", async () => {
      const { user } = renderLayout();

      await user.click(screen.getByRole("button", { name: "Build" }));

      expect(region("Composer page")).toBeInTheDocument();
      expect(router.push).toHaveBeenCalledWith("/workflows/new");
    });

    it("opens the composer from the saved-workflows Create new button", async () => {
      const { user } = renderLayout({ initialMainView: "saved-workflows" });

      await user.click(screen.getByRole("button", { name: "Create new" }));

      expect(region("Composer page")).toBeInTheDocument();
      expect(router.push).toHaveBeenCalledWith("/workflows/new");
    });
  });

  describe("open in canvas", () => {
    it("opens the built-in canvas route for a workflow type", async () => {
      const { user } = renderLayout();
      await user.click(screen.getByRole("button", { name: "Select user_stories" }));
      router.push.mockClear();

      await user.click(screen.getByRole("button", { name: "Open canvas" }));

      expect(region("Composer page")).toBeInTheDocument();
      expect(router.push).toHaveBeenCalledTimes(1);
      expect(router.push).toHaveBeenCalledWith("/workflows/user_stories/canvas");
    });

    it("opens a blank composer for the custom type", async () => {
      const { user } = renderLayout({ initialMainView: "input", initialWorkflowType: "custom" });

      await user.click(screen.getByRole("button", { name: "Open canvas" }));

      expect(region("Composer page")).toBeInTheDocument();
      expect(router.push).toHaveBeenCalledWith("/workflows/new");
    });
  });

  describe("Back", () => {
    it("goes home when there is no earlier history entry", async () => {
      const onResetPipeline = vi.fn();
      const { user } = renderLayout({ onResetPipeline });
      await user.click(screen.getByRole("button", { name: "Go Settings" }));
      router.push.mockClear();

      await user.click(screen.getByRole("button", { name: "Settings back" }));

      expect(region("Home grid")).toBeInTheDocument();
      expect(router.back).not.toHaveBeenCalled();
      expect(router.push).toHaveBeenCalledTimes(1);
      expect(router.push).toHaveBeenCalledWith("/dashboard");
      expect(onResetPipeline).toHaveBeenCalledTimes(1);
    });

    it("pops the history entry when there is one", async () => {
      const { user } = renderLayout({ initialMainView: "analytics" });
      historyLength.mockReturnValue(2);

      await user.click(screen.getByRole("button", { name: "Analytics back" }));

      expect(router.back).toHaveBeenCalledTimes(1);
      expect(router.push).not.toHaveBeenCalled();
    });

    it("keeps the running pipeline when Back is pressed mid-run", async () => {
      const onResetPipeline = vi.fn();
      const { user, rerenderLayout } = renderLayout({ initialMainView: "history", onResetPipeline });
      // A running pipeline pulls the layout into the execution view; the user then
      // opens History again from the header while the run is still going.
      rerenderLayout({ pipelineState: { ...idlePipelineState(), isRunning: true } });
      await user.click(screen.getByRole("button", { name: "Go History" }));

      await user.click(screen.getByRole("button", { name: "History back" }));

      expect(onResetPipeline).not.toHaveBeenCalled();
    });
  });

  describe("unsaved changes guard", () => {
    async function openDirtyComposer() {
      const view = renderLayout();
      await view.user.click(screen.getByRole("button", { name: "Select custom" }));
      await view.user.click(screen.getByRole("button", { name: "Mark dirty" }));
      router.push.mockClear();
      await view.user.click(screen.getByRole("button", { name: "Composer back" }));
      return view;
    }

    it("asks before leaving and stays put on Stay", async () => {
      const { user } = await openDirtyComposer();

      expect(screen.getByRole("dialog", { name: "Leave without saving?" })).toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "Stay" }));

      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(region("Composer page")).toBeInTheDocument();
      expect(router.push).not.toHaveBeenCalled();
      expect(router.back).not.toHaveBeenCalled();
    });

    it("dismisses the dialog when its backdrop is clicked but not when its body is", async () => {
      const { user } = await openDirtyComposer();
      const dialog = screen.getByRole("dialog", { name: "Leave without saving?" });

      await user.click(within(dialog).getByText("You have unsaved changes. Leaving now will discard them."));
      expect(screen.getByRole("dialog")).toBeInTheDocument();

      await user.click(dialog);
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(region("Composer page")).toBeInTheDocument();
    });

    it("discards the work and goes home on Leave anyway", async () => {
      const onResetPipeline = vi.fn();
      const view = renderLayout({ onResetPipeline });
      await view.user.click(screen.getByRole("button", { name: "Select custom" }));
      await view.user.click(screen.getByRole("button", { name: "Mark dirty" }));
      await view.user.click(screen.getByRole("button", { name: "Composer back" }));
      router.push.mockClear();

      await view.user.click(screen.getByRole("button", { name: "Leave anyway" }));

      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(region("Home grid")).toBeInTheDocument();
      expect(router.push).toHaveBeenCalledTimes(1);
      expect(router.push).toHaveBeenCalledWith("/dashboard");
      expect(onResetPipeline).toHaveBeenCalledTimes(1);
    });

    it("pops history on Leave anyway when there is an earlier entry", async () => {
      const { user } = await openDirtyComposer();
      historyLength.mockReturnValue(2);

      await user.click(screen.getByRole("button", { name: "Leave anyway" }));

      expect(router.back).toHaveBeenCalledTimes(1);
      expect(router.push).not.toHaveBeenCalled();
    });

    it("does not ask once the composer reports clean", async () => {
      const { user } = renderLayout();
      await user.click(screen.getByRole("button", { name: "Select custom" }));
      await user.click(screen.getByRole("button", { name: "Mark dirty" }));
      await user.click(screen.getByRole("button", { name: "Mark clean" }));
      router.push.mockClear();

      await user.click(screen.getByRole("button", { name: "Composer back" }));

      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(region("Home grid")).toBeInTheDocument();
      expect(router.push).toHaveBeenCalledWith("/dashboard");
    });
  });

  describe("connection banners", () => {
    it("shows the reconnecting banner only while reconnecting", () => {
      renderLayout({ connectionStatus: "reconnecting" });

      expect(screen.getByText("Reconnecting...")).toBeInTheDocument();
      expect(screen.queryByText("Connection lost.")).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Reconnect" })).not.toBeInTheDocument();
    });

    it("shows the lost banner with a working Reconnect button when the connection failed", async () => {
      const onReconnect = vi.fn();
      const { user } = renderLayout({ connectionStatus: "failed", onReconnect });

      expect(screen.getByText("Connection lost.")).toBeInTheDocument();
      expect(screen.queryByText("Reconnecting...")).not.toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "Reconnect" }));

      expect(onReconnect).toHaveBeenCalledTimes(1);
    });

    it("shows no banner while connected", () => {
      renderLayout({ connectionStatus: "connected" });

      expect(screen.queryByText("Reconnecting...")).not.toBeInTheDocument();
      expect(screen.queryByText("Connection lost.")).not.toBeInTheDocument();
    });
  });

  describe("launching a saved workflow", () => {
    const WIZARD_TYPES = ["ppt", "prototype"] as const;

    it.each(WIZARD_TYPES)(
      "stores the full %s wizard draft and routes to the wizard",
      async (type) => {
        probe.savedToLaunch = savedFixture({
          base_pipeline_type: type,
          description: "Saved desc",
          model_overrides: { a1: "model-x" },
          selections: {
            _wizard: {
              templateId: "tpl-1",
              designSystemId: "ds-1",
              brief: "Wizard brief",
              customDsBody: "DS body",
              customTemplateBody: "Template body",
              gateAgentIds: ["g1"],
            },
            a1: { lever: 1 },
          },
        });
        const { user } = renderLayout({ initialMainView: "saved-workflows" });

        await user.click(screen.getByRole("button", { name: "Launch saved" }));

        expect(JSON.parse(sessionStorage.getItem(`${type}.draft`) ?? "null")).toStrictEqual({
          templateId: "tpl-1",
          designSystemId: "ds-1",
          brief: "Wizard brief",
          customDsBody: "DS body",
          customTemplateBody: "Template body",
          gateAgentIds: ["g1"],
          modelOverrides: { a1: "model-x" },
          selections: { a1: { lever: 1 } },
          agentIds: ["a1", "a2"],
          id: "wf-1",
          name: "My workflow",
          description: "Saved desc",
        });
        expect(router.push).toHaveBeenCalledTimes(1);
        expect(router.push).toHaveBeenCalledWith(`/workflow/create?mode=${type}`);
        expect(region("Saved workflows page")).toBeInTheDocument();
      },
    );

    it.each(WIZARD_TYPES)(
      "omits empty optional fields from the %s wizard draft",
      async (type) => {
        probe.savedToLaunch = savedFixture({
          base_pipeline_type: type,
          model_overrides: {},
          selections: { _wizard: {} },
        });
        const { user } = renderLayout({ initialMainView: "saved-workflows" });

        await user.click(screen.getByRole("button", { name: "Launch saved" }));

        expect(JSON.parse(sessionStorage.getItem(`${type}.draft`) ?? "null")).toStrictEqual({
          templateId: null,
          designSystemId: null,
          brief: "",
          agentIds: ["a1", "a2"],
          id: "wf-1",
          name: "My workflow",
        });
        expect(router.push).toHaveBeenCalledWith(`/workflow/create?mode=${type}`);
      },
    );

    it("opens the composer pre-loaded for a custom saved workflow", async () => {
      probe.savedToLaunch = savedFixture({ base_pipeline_type: "custom" });
      const { user } = renderLayout({ initialMainView: "saved-workflows" });

      await user.click(screen.getByRole("button", { name: "Launch saved" }));

      expect(region("Composer page")).toBeInTheDocument();
      expect(screen.getByText("Composer name: [My workflow]")).toBeInTheDocument();
      expect(screen.getByText("Composer saved id: [wf-1]")).toBeInTheDocument();
      expect(router.push).toHaveBeenCalledTimes(1);
      expect(router.push).toHaveBeenCalledWith("/workflows/wf-1/run");
    });

    it("opens the composer for a manifest that contains composed agents", async () => {
      probe.savedToLaunch = savedFixture({
        base_pipeline_type: "user_stories",
        manifest: { steps: [{ agent: "custom-agent", instance_id: "emoji", name: "Emoji" }] },
      });
      const { user } = renderLayout({ initialMainView: "saved-workflows" });

      await user.click(screen.getByRole("button", { name: "Launch saved" }));

      expect(region("Composer page")).toBeInTheDocument();
      expect(queryRegion("Idea input page")).not.toBeInTheDocument();
      expect(router.push).toHaveBeenCalledWith("/workflows/wf-1/run");
    });

    it("opens the input view pre-loaded with the saved agents and brief for other types", async () => {
      probe.savedToLaunch = savedFixture({
        base_pipeline_type: "user_stories",
        selections: { _wizard: { brief: "Saved brief" } },
      });
      const { user } = renderLayout({ initialMainView: "saved-workflows" });

      await user.click(screen.getByRole("button", { name: "Launch saved" }));

      expect(region("Idea input page")).toBeInTheDocument();
      expect(screen.getByText("Input page: user_stories")).toBeInTheDocument();
      expect(screen.getByText('Initial agents: ["a1","a2"]')).toBeInTheDocument();
      expect(screen.getByText("Initial input: [Saved brief]")).toBeInTheDocument();
      expect(router.push).toHaveBeenCalledTimes(1);
      expect(router.push).toHaveBeenCalledWith("/workflows/wf-1/run");
    });

    it("attaches the saved workflow's hooks to the run it launches", async () => {
      const onStartPipeline = vi.fn();
      probe.savedToLaunch = savedFixture({
        attached_hooks: [
          { id: "h1", name: "Lint", event: "pre_run", trigger: "always", description: "Runs lint" },
          { id: "h2", name: "Format", event: "post_run", trigger: "on_save" },
        ],
      });
      const { user } = renderLayout({ initialMainView: "saved-workflows", onStartPipeline });

      await user.click(screen.getByRole("button", { name: "Launch saved" }));
      await user.click(screen.getByRole("button", { name: "Input run" }));

      expect(onStartPipeline).toHaveBeenCalledTimes(1);
      expect(onStartPipeline.mock.calls[0][3]).toStrictEqual([
        { id: "h1", name: "Lint", event: "pre_run", trigger: "always", description: "Runs lint" },
        { id: "h2", name: "Format", event: "post_run", trigger: "on_save" },
      ]);
    });

    it("drops the previous workflow's hooks when another saved workflow is launched", async () => {
      const onStartPipeline = vi.fn();
      probe.savedToLaunch = savedFixture({
        attached_hooks: [{ id: "h1", name: "Lint", event: "pre_run", trigger: "always" }],
      });
      const { user } = renderLayout({ initialMainView: "saved-workflows", onStartPipeline });
      await user.click(screen.getByRole("button", { name: "Launch saved" }));
      await user.click(screen.getByRole("button", { name: "Go Saved Workflows" }));
      probe.savedToLaunch = savedFixture({ id: "wf-2", attached_hooks: null });

      await user.click(screen.getByRole("button", { name: "Launch saved" }));
      await user.click(screen.getByRole("button", { name: "Input run" }));

      expect(onStartPipeline).toHaveBeenCalledTimes(1);
      expect(onStartPipeline.mock.calls[0][3]).toStrictEqual([]);
    });

    it("does not leak a typed home brief into a saved workflow launch", async () => {
      probe.savedToLaunch = savedFixture({ base_pipeline_type: "user_stories" });
      const { user } = renderLayout();
      await user.type(screen.getByRole("textbox", { name: "Brief" }), "stale brief");
      await user.click(screen.getByRole("button", { name: "Select user_stories" }));
      expect(screen.getByText("Initial input: [stale brief]")).toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "Input back" }));
      await user.click(screen.getByRole("button", { name: "Go Saved Workflows" }));

      await user.click(screen.getByRole("button", { name: "Launch saved" }));

      expect(screen.getByText("Initial input: []")).toBeInTheDocument();
    });
  });
});
