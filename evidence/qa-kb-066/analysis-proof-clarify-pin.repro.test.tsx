/**
 * QA-KB-066 / ISS-755 — analysis proof (throwaway, NOT a regression test).
 *
 * Mounts the REAL <PreviewPanel> (the only production mount is DashboardLayout.tsx:3383, which
 * never passes `clarifications`, so none is passed here either) with the REAL
 * AgentThinkingTab -> StepsOverviewSpine -> ClarificationsCard and the REAL FilesTab. The shell
 * run (v2) has answered one clarify round live, so the page-level pipelineState.clarifications is
 * non-empty; the user then pins the OLDER member v1 from the Version menu.
 *
 * Assertions state the DESIRED behaviour (expect.soft, so every one is evaluated), therefore the
 * ones marked RED are red at HEAD — the failure text is the evidence. Each case also console.logs
 * the observed state as one JSON line prefixed "OBSERVED".
 *
 *   R0a control          — no pin: the shell run's own rounds show in Steps (must stay green)
 *   R0b control          — no pin: ... and in Files (the Files tab is hidden from the strip, TAB_CONFIG
 *                          PreviewPanel.tsx:531-543, so it is opened with a nonce'd deepLinkTarget, the
 *                          way a legacy /runs/{id}/files URL reaches it)
 *   R1  root, Steps      — pin v1: v1 must not show v2's rounds                      (RED at HEAD)
 *   R2  root, Files      — pin v1: Files must not list v2's clarifications.md        (RED at HEAD)
 *   R3  inverse          — pin v1 whose OWN rounds are persisted: they must show     (RED at HEAD)
 *   R4c control          — shell run running but NOT clarify-paused, pin v1: v1's agent row shows
 *   R4  adjacent state   — shell run clarify-PAUSED, pin v1: v1 must keep its agent
 *                          rows and must not host the live run's answer form         (RED at HEAD)
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import type { ClarifyRound, PipelineRunState } from "@/types/index";

const mockGetToken = vi.fn(() => "test-token");
const mockGetWorkflow = vi.fn();
const mockGetRunSandboxRefs = vi.fn();
const mockGetRunSandbox = vi.fn();
const mockGetRunSandboxFile = vi.fn();
const mockGetRunSandboxFileBlob = vi.fn();
const mockGetRunSandboxZip = vi.fn();
const mockResolveRunDeliverable = vi.fn();
const mockGetRunArtifacts = vi.fn();

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    getToken: () => mockGetToken(),
    getWorkflow: (...args: unknown[]) => mockGetWorkflow(...args),
    getRunFamily: vi.fn().mockResolvedValue(null),
    getRunGateEvents: vi.fn().mockResolvedValue({ gate_events: [] }),
    getWorkflowDefinitions: vi.fn().mockResolvedValue([]),
    postShareRun: vi.fn(),
    deleteShareRun: vi.fn(),
    getRunSandboxRefs: (...args: unknown[]) => mockGetRunSandboxRefs(...args),
    getRunSandbox: (...args: unknown[]) => mockGetRunSandbox(...args),
    getRunSandboxFile: (...args: unknown[]) => mockGetRunSandboxFile(...args),
    getRunSandboxFileBlob: (...args: unknown[]) => mockGetRunSandboxFileBlob(...args),
    getRunSandboxZip: (...args: unknown[]) => mockGetRunSandboxZip(...args),
    resolveRunDeliverable: (...args: unknown[]) => mockResolveRunDeliverable(...args),
    getRunArtifacts: (...args: unknown[]) => mockGetRunArtifacts(...args),
  };
});

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/runs/member-uuid-v2/steps",
  useSearchParams: () => new URLSearchParams(),
}));

const STRIPPED_MOTION_PROPS = new Set([
  "initial", "animate", "exit", "transition", "whileHover",
  "whileTap", "whileFocus", "whileInView", "viewport", "layout",
  "layoutId", "drag", "dragConstraints", "variants", "custom",
]);
vi.mock("motion/react", () => ({
  motion: new Proxy(
    {},
    {
      get: (_target, prop: string) =>
        ({ children, ...rest }: { children?: React.ReactNode } & Record<string, unknown>) => {
          const cleaned = Object.fromEntries(
            Object.entries(rest).filter(([k]) => !STRIPPED_MOTION_PROPS.has(k)),
          );
          return React.createElement(prop, cleaned, children);
        },
    },
  ),
  AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));

// Not under test — stubbed exactly as PreviewPanel.versionRunInput.test.tsx does.
vi.mock("@/components/preview/UserStoryPreview", () => ({ UserStoryPreview: () => <div data-testid="user-story-preview" /> }));
vi.mock("@/components/preview/PPTPreview", () => ({ PPTPreview: () => <div data-testid="ppt-preview" /> }));
vi.mock("@/components/preview/PrototypePreview", () => ({ PrototypePreview: () => <div data-testid="proto-preview" /> }));
vi.mock("@/components/preview/MarkdownPreview", () => ({ MarkdownPreview: () => <div data-testid="markdown-preview" /> }));
vi.mock("@/components/preview/AppBuilderPreview", () => ({ AppBuilderPreview: () => <div data-testid="appbuilder-preview" /> }));
vi.mock("@/components/workflow/TokenUsageSummary", () => ({ TokenUsageSummary: () => <div data-testid="token-usage" /> }));
// AuditTab + SandboxTab are not the subject and fetch on mount.
vi.mock("@/components/results/AuditTab", () => ({ AuditTab: () => <div data-testid="audit-tab" /> }));
vi.mock("@/components/results/SandboxTab", () => ({ SandboxTab: () => <div data-testid="sandbox-tab" /> }));

import { PreviewPanel } from "@/components/preview/PreviewPanel";

const V1_ID = "member-uuid-v1";
const V2_ID = "member-uuid-v2";
// The Files tab is hidden from the strip (TAB_CONFIG, PreviewPanel.tsx:531-543) and initialTab is overridden by the
// state-keyed default-tab effect (:1260-1297); a nonce'd deep link — what a legacy /runs/{id}/files URL becomes —
// is the one thing that lands on it.
const FILES_DEEP_LINK = { tab: "files", nonce: 1 };

const family = {
  root_id: V1_ID,
  members: [
    { id: V1_ID, type: "prototype", title: "v1 run", status: "completed", revision_index: 1, parent_run_id: null, created_at: "2026-09-01T00:00:00Z", completed_at: "2026-09-01T01:00:00Z", git_tag: "v1" },
    { id: V2_ID, type: "prototype_revision", title: "v2 run", status: "completed", revision_index: 2, parent_run_id: V1_ID, created_at: "2026-09-02T00:00:00Z", completed_at: "2026-09-02T01:00:00Z", git_tag: "v2" },
  ],
};

// What the SHELL run (v2) answered live in this page session: retainClarifyRound -> pipelineState.clarifications.
const V2_ROUND: ClarifyRound = {
  round: 1,
  qa: [
    { question_id: "q-v2-1", question_text: "V2-ROUND-Q1 which auth provider?", impact_level: "high", answer: "V2-ANSWER OAuth" },
    { question_id: "q-v2-2", question_text: "V2-ROUND-Q2 which database?", impact_level: "low", answer: "V2-ANSWER Postgres" },
  ],
};

const shellState = (over: Partial<PipelineRunState> = {}) => ({
  isRunning: false, pipelineRunId: V2_ID, pipeline_type: "prototype_revision",
  agents: [], currentAgentIndex: -1, totalDuration: null, completedCount: 0,
  deliverableFilename: "prototype.html",
  clarifications: [V2_ROUND],
  ...over,
}) as unknown as PipelineRunState;

const v1Run = (over: Record<string, unknown> = {}) => ({
  id: V1_ID, title: "v1 run", type: "prototype", status: "completed",
  input: "V1 BRIEF", output: "<html>v1</html>",
  agentOutputs: [{ agent_id: "prototype-build", name: "Prototype Build", role: "build", icon: "", output: "v1 built output", thinking: "" }],
  parentRunId: null, rootRunId: V1_ID,
  ...over,
});

beforeEach(() => {
  mockGetToken.mockReset().mockReturnValue("test-token");
  mockGetRunSandboxRefs.mockReset().mockResolvedValue(["v1", "v2"]);
  mockGetRunSandbox.mockReset().mockResolvedValue({ run_id: "run-1", expired: false, truncated: false, files: [] });
  mockGetRunSandboxFile.mockReset().mockResolvedValue("<html></html>");
  mockResolveRunDeliverable.mockReset().mockResolvedValue(null);
  mockGetRunArtifacts.mockReset().mockResolvedValue({ artifacts: [] });
  mockGetWorkflow.mockReset().mockImplementation((_t: string, id: string) =>
    Promise.resolve(id === V1_ID ? v1Run() : null));
});

function mountShell(props: Record<string, unknown> = {}, state: PipelineRunState = shellState()) {
  return render(
    <PreviewPanel
      workflowType="prototype"
      prototypeContent="<html>v2 live</html>"
      pipelineState={state}
      liveRunId={V2_ID}
      runFamily={family}
      runInput="V2 BRIEF"
      initialTab="preview"
      {...props}
    />,
  );
}

async function pinV1() {
  await waitFor(() => expect(mockGetRunSandboxRefs).toHaveBeenCalled());
  await userEvent.click(screen.getByRole("button", { name: /^v2\b/ }));
  await userEvent.click(screen.getByRole("option", { name: "v1" }));
  await waitFor(() => expect(mockGetWorkflow).toHaveBeenCalledWith("test-token", V1_ID));
  await waitFor(() => expect(screen.getAllByText(/Viewing v1/i).length).toBeGreaterThan(0));
}

const clarifyCard = () => screen.queryByRole("button", { name: /^Clarifications, \d+ question/ });

async function expandClarifyCard() {
  const btn = clarifyCard();
  if (btn) await userEvent.click(btn);
  return btn;
}

describe("QA-KB-066 analysis proof — the clarify rounds fed to Steps/Files under a version pin", () => {
  it("R0a control: NO pin -> Steps shows the shell run's own 2-question card", async () => {
    mountShell();
    await waitFor(() => expect(mockGetRunSandboxRefs).toHaveBeenCalled());

    await userEvent.click(screen.getByRole("tab", { name: /steps/i }));
    const card = clarifyCard();
    expect(card, "Steps clarify card present for the un-pinned shell run").not.toBeNull();
    expect(card!.getAttribute("aria-label")).toBe("Clarifications, 2 questions");
    console.log("OBSERVED R0a " + JSON.stringify({ stepsCard: card!.getAttribute("aria-label") }));
  });

  it("R0b control: NO pin -> Files lists the shell run's clarifications.md", async () => {
    mountShell({ deepLinkTarget: FILES_DEEP_LINK });
    await waitFor(() => expect(mockGetRunSandboxRefs).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryAllByText("clarifications.md").length).toBeGreaterThan(0));
    console.log("OBSERVED R0b " + JSON.stringify({ filesClarificationsMd: screen.queryAllByText("clarifications.md").length }));
  });

  it("R1 root, Steps: pin v1 -> v1 must NOT show v2's clarify rounds (RED at HEAD)", async () => {
    mountShell();
    await pinV1();
    await userEvent.click(screen.getByRole("tab", { name: /steps/i }));

    const card = await expandClarifyCard();
    const v2QuestionVisible = !!screen.queryByText(/V2-ROUND-Q1/);
    const v2AnswerVisible = !!screen.queryByText(/V2-ANSWER OAuth/);
    console.log("OBSERVED R1 " + JSON.stringify({
      pinBannerShown: screen.queryAllByText(/Viewing v1/i).length > 0,
      clarifyCardShown: !!card,
      cardLabel: card?.getAttribute("aria-label") ?? null,
      v2QuestionVisible, v2AnswerVisible,
    }));
    expect.soft(card, "no clarify card for pinned v1 (it has none of its own loaded)").toBeNull();
    expect.soft(v2QuestionVisible, "v2's question text must not render under the v1 pin").toBe(false);
    expect.soft(v2AnswerVisible, "v2's answer text must not render under the v1 pin").toBe(false);
  });

  it("R2 root, Files: pin v1 -> Files must NOT list the shell run's clarifications.md (RED at HEAD)", async () => {
    mountShell({ deepLinkTarget: FILES_DEEP_LINK });
    await pinV1();
    // let the Files tab settle (it resolves the deliverable on mount / on the pin)
    await waitFor(() => expect(mockGetRunSandbox.mock.calls.length + mockResolveRunDeliverable.mock.calls.length).toBeGreaterThan(0));
    const rows = screen.queryAllByText("clarifications.md");
    console.log("OBSERVED R2 " + JSON.stringify({ pinBannerShown: screen.queryAllByText(/Viewing v1/i).length > 0, clarificationsMdRows: rows.length, promptMdRows: screen.queryAllByText("prompt.md").length }));
    expect.soft(rows.length, "clarifications.md (v2's Q&A) must not be offered under the v1 pin").toBe(0);
  });

  it("R3 inverse: pin v1 whose OWN rounds are persisted (shell has none) -> they should show (RED at HEAD)", async () => {
    mockGetRunArtifacts.mockResolvedValue({
      artifacts: [{ content: JSON.stringify([{ question_id: "q-v1-1", question_text: "V1-OWN-Q1 which tone?", impact_level: "high", answer: "V1-OWN-ANSWER formal", round: 1 }]) }],
    });
    mountShell({}, shellState({ clarifications: [] }));
    await pinV1();
    await userEvent.click(screen.getByRole("tab", { name: /steps/i }));
    await expandClarifyCard();
    const requested = mockGetRunArtifacts.mock.calls.map((c) => JSON.stringify(c.slice(1)));
    console.log("OBSERVED R3 " + JSON.stringify({ getRunArtifactsCalls: requested, v1OwnQuestionVisible: !!screen.queryByText(/V1-OWN-Q1/), clarifyCardShown: !!clarifyCard() }));
    expect.soft(mockGetRunArtifacts, "pinning v1 should request v1's persisted kind=clarifications artifacts").toHaveBeenCalled();
    expect.soft(!!screen.queryByText(/V1-OWN-Q1/), "v1's own question should render under its pin").toBe(true);
  });

  it("R4 control: shell run RUNNING but NOT clarify-paused, pin v1 -> v1's own agent row shows (isolates hasClarify as the cause)", async () => {
    mountShell({}, shellState({ isRunning: true, clarifications: [] }));
    await pinV1();
    await userEvent.click(screen.getByRole("tab", { name: /steps/i }));
    const agentRows = screen.queryAllByTestId("steps-agent-row").length;
    console.log("OBSERVED R4-control " + JSON.stringify({ pinnedAgentRowsShown: agentRows }));
    expect(agentRows).toBeGreaterThan(0);
  });

  it("R4 adjacent state: shell run clarify-PAUSED, pin v1 -> v1 keeps its agent rows, no live answer form (RED at HEAD)", async () => {
    mountShell(
      {
        clarifyQuestions: [{ id: "q-live-1", question: "LIVE-V2-PENDING which tone should the deck use?", options: ["Formal", "Casual"] }],
        onSubmitClarify: vi.fn(),
      },
      shellState({ isRunning: true, clarifications: [] }),
    );
    await pinV1();
    await userEvent.click(screen.getByRole("tab", { name: /steps/i }));
    const liveFormShown = !!screen.queryByText(/LIVE-V2-PENDING/);
    const agentRows = screen.queryAllByTestId("steps-agent-row").length;
    console.log("OBSERVED R4 " + JSON.stringify({ pinBannerShown: screen.queryAllByText(/Viewing v1/i).length > 0, liveAnswerFormShownUnderPin: liveFormShown, pinnedAgentRowsShown: agentRows }));
    expect.soft(liveFormShown, "the live run's pending question must not be answerable inside read-only v1").toBe(false);
    expect.soft(agentRows, "pinned v1's own agent row must stay visible").toBeGreaterThan(0);
  });
});
