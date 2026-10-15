/**
 * ISS-1154 (QA-KB-110) / ISS-1171 - "Edit brief & run again" on a failed run.
 * Correct behaviour asserted (regression guard; fix landed in FIX-777).
 *
 * The push to /create/<type> REMOUNTS DashboardLayout (page.tsx:3547-3551), so a brief held in
 * component state (pendingHomeBrief) is lost. A same-instance test stays green on the bug; the
 * remount is modelled as cleanup() + a fresh mount with the props page.tsx derives from the URL.
 */
import React from "react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import ts from "typescript";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import { parseViewPath } from "@/lib/routes";
import type { PipelineRunState, WorkflowType } from "@/types/index";


const h = vi.hoisted(() => ({
  push: vi.fn(),
  getWorkflow: vi.fn(),
}));

vi.mock("next/navigation", () => {
  const router = { push: h.push, replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() };
  return { useRouter: () => router };
});

vi.mock("@/lib/api", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/api")>();
  return {
    ...actual,
    getToken: () => "test-token",
    getRunFamily: () => Promise.resolve({ root_id: "", members: [] }),
    getWorkflow: (...args: unknown[]) => h.getWorkflow(...args),
  };
});

const STRIPPED = new Set([
  "initial", "animate", "exit", "transition", "whileHover", "whileTap", "whileFocus",
  "whileInView", "viewport", "layout", "layoutId", "drag", "dragConstraints", "variants", "custom",
]);
vi.mock("motion/react", async () => {
  const React = await import("react");
  return {
    motion: new Proxy({}, {
      get: (_t, prop: string) =>
        ({ children, ...rest }: { children?: React.ReactNode } & Record<string, unknown>) =>
          React.createElement(prop, Object.fromEntries(Object.entries(rest).filter(([k]) => !STRIPPED.has(k))), children),
    }),
    AnimatePresence: ({ children }: { children?: React.ReactNode }) => React.createElement(React.Fragment, null, children),
  };
});

vi.mock("@/components/chat/RunChatLane", async () => {
  const React = await import("react");
  return {
    RunChatLane: (p: { onEditBrief?: () => void; onRelaunch?: () => void }) =>
      React.createElement("button", {
        "data-testid": "chat-relaunch-secondary",
        // RunChatLane.tsx:1942
        onClick: () => (p.onEditBrief ?? p.onRelaunch)?.(),
      }),
  };
});

vi.mock("@/components/workflow/IdeaInputPage", async () => {
  const React = await import("react");
  function Stub({ initialInput, workflowType }: { initialInput?: string; workflowType: string }) {
    // IdeaInputPage.tsx:970 — seeded once, at mount.
    const [value] = React.useState(initialInput ?? "");
    return React.createElement("textarea", {
      "data-testid": "brief", "data-workflow-type": workflowType, value, readOnly: true,
    });
  }
  return { IdeaInputPage: (p: { initialInput?: string; workflowType: string }) => React.createElement(Stub, p) };
});

// Heavy children: inert markers (same set the repo's own DashboardLayout tests stub).
vi.mock("@/components/layout/AppHeader", async () => { const React = await import("react"); return { AppHeader: () => React.createElement("div") }; });
vi.mock("@/components/preview/PreviewPanel", async () => { const React = await import("react"); return { PreviewPanel: () => React.createElement("div") }; });
vi.mock("@/components/workflow/AgentProgressPanel", async () => { const React = await import("react"); return { AgentProgressPanel: () => React.createElement("div") }; });
vi.mock("@/components/ui/CompletionToast", async () => { const React = await import("react"); return { CompletionToast: () => React.createElement("div") }; });
vi.mock("@/components/catalog/HomeLaunchGrid", async () => { const React = await import("react"); return { HomeLaunchGrid: () => React.createElement("div") }; });
vi.mock("@/components/home/CreationHub", async () => { const React = await import("react"); return { CreationHub: () => React.createElement("div") }; });
vi.mock("@/components/library/LibraryPage", async () => { const React = await import("react"); return { LibraryPage: () => React.createElement("div") }; });
vi.mock("@/components/history/WorkflowHistory", async () => { const React = await import("react"); return { WorkflowHistory: () => React.createElement("div") }; });
vi.mock("@/components/settings/AccountSettings", async () => { const React = await import("react"); return { AccountSettings: () => React.createElement("div") }; });
vi.mock("@/components/analytics/AnalyticsPage", async () => { const React = await import("react"); return { AnalyticsPage: () => React.createElement("div") }; });

import { DashboardLayout } from "@/components/layout/DashboardLayout";
import type { DashboardLayoutProps } from "@/components/layout/DashboardLayout";

// ── page.tsx helpers, sliced from the real source ─────────────────────────────────────────────
const pageSrc = readFileSync(resolve(__dirname, "../../app/[...view]/page.tsx"), "utf8");
function sliceFn(name: string) {
  const start = pageSrc.indexOf(`function ${name}(`);
  if (start < 0) throw new Error(`page.tsx has no function ${name}`);
  const end = pageSrc.indexOf("\n}\n", start) + 3;
  const js = ts.transpileModule(pageSrc.slice(start, end), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  return new Function(`${js}; return ${name};`)() as (p: ReturnType<typeof parseViewPath>) => string | undefined;
}
const initialMainViewFor = sliceFn("initialMainViewFor");
const initialWorkflowTypeFor = sliceFn("initialWorkflowTypeFor");
const wizardModeFor = sliceFn("wizardModeFor");
const parse = (url: string) => parseViewPath(url.split("/").filter(Boolean));

/** What page.tsx hands DashboardLayout for `url` on a fresh mount. */
function pagePropsFor(url: string) {
  const parsed = parse(url);
  return {
    wizard: wizardModeFor(parsed),           // truthy => page.tsx returns <LaunchWizard>, DashboardLayout never mounts
    initialMainView: initialMainViewFor(parsed) as DashboardLayoutProps["initialMainView"],
    initialWorkflowType: initialWorkflowTypeFor(parsed),
  };
}

const BRIEF = "Greet the team with a short emoji hello.";
const RUN_ID = "run-1";

function idle(): PipelineRunState {
  return { isRunning: false, pipeline_type: "user_stories", agents: [], currentAgentIndex: -1, totalDuration: null, completedCount: 0 };
}
function baseProps(over: Partial<DashboardLayoutProps>): DashboardLayoutProps {
  return {
    activeChatId: null, messages: [], isStreaming: false, streamingContent: "", userStoryContent: "",
    pptContent: "", prototypeContent: "", connectionStatus: "connected", onSendMessage: vi.fn(),
    onSelectChat: vi.fn(), onNewChat: vi.fn(), onDeleteChat: vi.fn(), onLogout: vi.fn(), onReconnect: vi.fn(),
    pipelineState: idle(), ...over,
  };
}
function storage(): Record<string, string> {
  const out: Record<string, string> = {};
  for (let i = 0; i < sessionStorage.length; i++) {
    const k = sessionStorage.key(i)!;
    out[k] = sessionStorage.getItem(k)!;
  }
  return out;
}

/** Mount the failed run's page (what /runs/<id> renders), click Edit brief & run again. */
async function clickEditBrief(runType: string, input = BRIEF) {
  h.getWorkflow.mockImplementation(async (_t: string, id: string) => ({
    id, title: "t", type: runType, status: "failed", input, agentCount: 0, createdAt: "2026-10-09T00:00:00Z",
  }));
  h.push.mockClear();
  sessionStorage.clear();
  const runPage = baseProps({
    initialMainView: "execution", contentSourceRunId: RUN_ID,
    contentSourceRunType: runType as WorkflowType, onResetPipeline: vi.fn(),
  });
  const utils = renderWithProviders(<DashboardLayout {...runPage} />);
  fireEvent.click(screen.getByTestId("chat-relaunch-secondary"));
  await waitFor(() => expect(h.push).toHaveBeenCalledTimes(1));
  return { utils, target: h.push.mock.calls[0][0] as string, staged: storage(), runPage };
}

/** A page.tsx remount: the old subtree goes away, a new one mounts from the pushed URL alone. */
function remountAt(url: string) {
  cleanup();
  const p = pagePropsFor(url);
  if (p.wizard) return { wizard: p.wizard, brief: undefined as string | undefined, type: undefined as string | undefined };
  renderWithProviders(
    <DashboardLayout {...baseProps({ initialMainView: p.initialMainView, initialWorkflowType: p.initialWorkflowType })} />,
  );
  const ta = screen.getByTestId("brief") as HTMLTextAreaElement;
  return { wizard: undefined, brief: ta.value, type: ta.getAttribute("data-workflow-type") };
}


beforeEach(() => { cleanup(); sessionStorage.clear(); });
afterEach(() => { cleanup(); });

describe("ISS-1154 edit brief hand-off survives the remount", () => {
  // ISS-1154: red today, composer is "" for every non-wizard type.
  it.each(["ex_A1_loop", "backlog", "user_stories", "app_builder"])(
    "%s: the remounted composer holds the failed run's own brief",
    async (type) => {
      const { target } = await clickEditBrief(type);
      const after = remountAt(target);
      expect(after.wizard).toBeUndefined();
      expect(after.brief).toBe(BRIEF);
    },
  );

  // Controls, green today: wizard types stage the draft and land on the wizard.
  it.each([["ppt_v2", "ppt.draft"], ["prototype_v2", "prototype.draft"]])(
    "%s: wizard type stages the brief in %s",
    async (type, key) => {
      const { target, staged } = await clickEditBrief(type);
      expect(JSON.parse(staged[key])).toEqual({ brief: BRIEF });
      expect(wizardModeFor(parse(target))).toBeTruthy();
    },
  );
});

describe("ISS-1171 no draft is staged for a destination that will not read it", () => {
  // Red today: ppt.draft / prototype.draft are written but /create/<x>_revision is not the wizard.
  it.each(["ppt_revision", "prototype_revision", "prototype_v2_revision"])(
    "%s: any staged draft is consumed by the pushed route",
    async (type) => {
      const { target, staged } = await clickEditBrief(type);
      const wizard = wizardModeFor(parse(target));
      if (!wizard) expect(Object.keys(staged).filter((k) => k === "ppt.draft" || k === "prototype.draft")).toEqual([]);
    },
  );
});
