/**
 * QA-KB-110 / ISS-1154 analysis probe. OFFLINE (jsdom), read-only on the repo: it imports the
 * REAL DashboardLayout and the REAL routes.ts, slices the three module-private route helpers
 * out of page.tsx the way initialWorkflowType.bug023.source.test.ts does, and edits nothing.
 * It is evidence for the analysis, not a repo test (it lives outside frontend/src).
 *
 * Question: "Edit brief & run again" sets the viewed run's brief on DashboardLayout state
 * (`pendingHomeBrief`) and then router.push()es to /create/<type>. The [...view] catch-all
 * remounts page.tsx on that push (page.tsx:3547-3551, DashboardLayout.tsx:551-557, Next's
 * layout-router.js keys the subtree by the segment value). Does the brief reach the composer?
 *
 * TWO MODES (same file, same assertions table):
 *   default                 observes today's behaviour.
 *   QA_KB_110_MUTATE=1      a Vite transform (vitest.probe.config.ts) rewrites TWO anchored statements of
 *                           DashboardLayout.tsx IN MEMORY while the test runs; the file on disk is never
 *                           written. It adds the smallest candidate fix (a one-shot sessionStorage hand-off
 *                           for the destinations that have none) so the analysis can say what the fix
 *                           changes and what it leaves red. It is a probe of the fix SHAPE, not the fix.
 *
 * What is stubbed, and why it is faithful:
 *   - RunChatLane  -> one button whose onClick is the real line RunChatLane.tsx:1942,
 *                     `(onEditBrief ?? onRelaunch)?.()`. Everything else about the lane is not
 *                     on the click path.
 *   - IdeaInputPage -> a textarea seeded exactly like IdeaInputPage.tsx:970,
 *                     `useState(initialInput ?? "")`, i.e. ONCE at mount.
 *   - next/navigation useRouter().push -> a spy. Under jsdom a spy cannot remount anything,
 *                     which is also why no existing unit test can see this defect.
 *   - getWorkflow  -> resolves the failed run with a non-empty `input`, as GET /api/runs/{id}
 *                     does (api.ts:1344-1349, normalizeWorkflowRun api.ts:1132 `input: raw.input`).
 *   - A remount is modelled as cleanup() + a fresh render with the props page.tsx derives from
 *                     the pushed URL (initialMainViewFor / initialWorkflowTypeFor, sliced from
 *                     page.tsx, applied to the real parseViewPath).
 */
import React from "react";
import { readFileSync } from "node:fs";
import ts from "typescript";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import { parseViewPath } from "@/lib/routes";
import type { PipelineRunState, WorkflowType } from "@/types/index";

const FRONTEND =
  process.env.QA_KB_110_FRONTEND ??
  "/Users/bilala/Developer/Projects/VELOCITY-AI-worktrees/feat-user-stories-v2/frontend";

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
const pageSrc = readFileSync(`${FRONTEND}/src/app/[...view]/page.tsx`, "utf8");
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

const FIXED = process.env.QA_KB_110_MUTATE === "1";
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

const log: string[] = [];
const say = (s: string) => { log.push(s); };

beforeEach(() => { cleanup(); sessionStorage.clear(); });
afterEach(() => { cleanup(); });

describe("QA-KB-110 probe", () => {
  it("[A] in-place (no remount): the same DashboardLayout instance DOES hand the brief to the composer", async () => {
    const { utils, target, runPage } = await clickEditBrief("ex_A1_loop");
    expect(target).toBe("/create/ex_A1_loop");
    // The URL moved but the instance survived: page.tsx re-renders it with the new URL's props.
    const next = pagePropsFor(target);
    utils.rerender(<DashboardLayout {...runPage} initialMainView={next.initialMainView} />);
    const ta = screen.getByTestId("brief") as HTMLTextAreaElement;
    say(`[A] in-place   push=${target}  textarea=${JSON.stringify(ta.value)}  workflowType=${ta.getAttribute("data-workflow-type")}`);
    expect(ta.value).toBe(BRIEF);                         // FIX-331's in-memory channel works while the instance lives...
    expect(ta.getAttribute("data-workflow-type")).toBe("user_stories"); // ...but the panel would be the WRONG type (handleEditBrief never sets it)
  });

  it("[B] after the remount page.tsx causes: the brief is gone and the panel type comes from the URL", async () => {
    const { target } = await clickEditBrief("ex_A1_loop");
    const after = remountAt(target);
    say(`[B] remounted   push=${target}  textarea=${JSON.stringify(after.brief)}  workflowType=${after.type}`);
    expect(after.wizard).toBeUndefined();
    expect(after.type).toBe("ex_A1_loop");               // matches the live screenshot: "Retry until it passes" panel
    expect(after.brief).toBe(FIXED ? BRIEF : "");        // default: the defect. mutated: the brief survives the remount
  });

  it.each([
    ["backlog", "/create/backlog"],
    ["user_stories", "/create/user-stories"],
    ["app_builder", "/create/app"],
    ["custom", "/create/custom"],
    ["ex_A2_branch", "/create/ex_A2_branch"],
  ])("[C] non-wizard type %s: nothing is staged for the destination, and the remounted composer is empty", async (type, route) => {
    const { target, staged } = await clickEditBrief(type);
    const after = remountAt(target);
    say(`[C] ${type.padEnd(13)} push=${target}  staged=${JSON.stringify(Object.keys(staged))}  remounted textarea=${JSON.stringify(after.brief)}`);
    expect(target).toBe(route);
    expect(Object.keys(staged)).toEqual(FIXED ? ["idea.draft"] : []);   // default: no storage channel at all for this destination
    expect(after.brief).toBe(FIXED ? BRIEF : "");
  });

  it.each([
    ["ppt", "ppt.draft"], ["ppt_v2", "ppt.draft"], ["prototype", "prototype.draft"], ["prototype_v2", "prototype.draft"],
  ])("[D] wizard type %s: the brief is staged in sessionStorage[%s] and the push lands on the wizard", async (type, key) => {
    const { target, staged } = await clickEditBrief(type);
    const wizard = wizardModeFor(parse(target));
    say(`[D] ${type.padEnd(13)} push=${target}  staged=${JSON.stringify(staged)}  wizardModeFor=${wizard}`);
    expect(JSON.parse(staged[key])).toEqual({ brief: BRIEF });
    expect(wizard).toBeTruthy();                          // LaunchWizard restores the draft (LaunchWizard.tsx:449-491)
  });

  it.each([
    ["ppt_revision", "ppt.draft"], ["prototype_revision", "prototype.draft"], ["prototype_v2_revision", "prototype.draft"],
    ["prototype_v2_feature_revision", null], ["backlog_revision", null], ["user_stories_revision", null],
  ])("[E] revision type %s: draft key %s is staged for a destination that is not the wizard", async (type, key) => {
    const { target, staged } = await clickEditBrief(type);
    const wizard = wizardModeFor(parse(target));
    const after = remountAt(target);
    say(`[E] ${type.padEnd(30)} push=${target}  staged=${JSON.stringify(Object.keys(staged))}  wizardModeFor=${wizard}  remounted textarea=${JSON.stringify(after.brief)}`);
    expect(wizard).toBeUndefined();
    if (key) {
      expect(JSON.parse(staged[key])).toEqual({ brief: BRIEF });          // orphan: nothing on /create/<x>_revision reads it
      expect(after.brief).toBe("");                                        // still empty even with the mutation: the slot is keyed by the BASE type
    } else {
      expect(Object.keys(staged)).toEqual(FIXED ? ["idea.draft"] : []);
      expect(after.brief).toBe(FIXED ? BRIEF : "");
    }
  });

  it("[F] empty input: a run with no input opens an empty composer without throwing", async () => {
    const { target } = await clickEditBrief("ex_A1_loop", "");
    const after = remountAt(target);
    say(`[F] empty input push=${target} remounted textarea=${JSON.stringify(after.brief)}`);
    expect(after.brief).toBe("");
  });

  it("[G] one-shot: the staged brief is consumed by the composer that shows it, so a later fresh visit is not pre-filled", async () => {
    if (!FIXED) return; // only meaningful once a hand-off exists
    const { target } = await clickEditBrief("ex_A1_loop");
    const first = remountAt(target);
    const leftover = sessionStorage.getItem("idea.draft");
    const second = remountAt(target);   // user leaves and opens /create/ex_A1_loop again, no Edit brief click
    say(`[G] one-shot  first=${JSON.stringify(first.brief)}  keyAfterFirstMount=${JSON.stringify(leftover)}  secondVisit=${JSON.stringify(second.brief)}`);
    expect(first.brief).toBe(BRIEF);
    expect(leftover).toBeNull();
    expect(second.brief).toBe("");
  });

  it("[H] StrictMode (the dev default): a read-only initializer plus a clearing effect survives the double invoke", async () => {
    if (!FIXED) return;
    const { target } = await clickEditBrief("backlog");
    cleanup();
    const p = pagePropsFor(target);
    renderWithProviders(
      <React.StrictMode>
        <DashboardLayout {...baseProps({ initialMainView: p.initialMainView, initialWorkflowType: p.initialWorkflowType })} />
      </React.StrictMode>,
    );
    const ta = screen.getByTestId("brief") as HTMLTextAreaElement;
    say(`[H] StrictMode  push=${target}  remounted textarea=${JSON.stringify(ta.value)}  keyAfterMount=${JSON.stringify(sessionStorage.getItem("idea.draft"))}`);
    expect(ta.value).toBe(BRIEF);
    expect(sessionStorage.getItem("idea.draft")).toBeNull();
  });

  it("[Z] summary", () => {
    // eslint-disable-next-line no-console
    console.log("\n" + log.join("\n") + "\n");
    expect(log.length).toBeGreaterThan(0);
  });
});
