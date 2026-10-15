/**
 * QA-KB-066 / ISS-755, ISS-1006, ISS-1007, ISS-1008 - clarify rounds under a version pin.
 * Each `it.fails` asserts the CORRECT behaviour and is red today; when the fix lands the case
 * goes green and vitest fails it ("expected to fail"), so drop `.fails` then.
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

describe("QA-KB-066 - clarify rounds fed to Steps/Files follow the pinned version", () => {
  it("control: NO pin -> Steps shows the shell run's own 2-question card", async () => {
    mountShell();
    await waitFor(() => expect(mockGetRunSandboxRefs).toHaveBeenCalled());
    await userEvent.click(screen.getByRole("tab", { name: /steps/i }));
    expect(clarifyCard()!.getAttribute("aria-label")).toBe("Clarifications, 2 questions");
  });

  it("ISS-755 - pin v1: Steps must NOT show v2's clarify rounds", async () => {
    mountShell();
    await pinV1();
    await userEvent.click(screen.getByRole("tab", { name: /steps/i }));
    await expandClarifyCard();
    expect(screen.queryByText(/V2-ROUND-Q1/)).toBeNull();
    expect(screen.queryByText(/V2-ANSWER OAuth/)).toBeNull();
  });

  it("ISS-755 - pin v1: Files must NOT list the shell run's clarifications.md", async () => {
    mountShell({ deepLinkTarget: FILES_DEEP_LINK });
    await pinV1();
    await waitFor(() => expect(mockGetRunSandbox.mock.calls.length + mockResolveRunDeliverable.mock.calls.length).toBeGreaterThan(0));
    expect(screen.queryAllByText("clarifications.md").length).toBe(0);
  });

  it("ISS-1006 - pin v1 whose OWN rounds are persisted: they show under the pin", async () => {
    mockGetRunArtifacts.mockResolvedValue({
      artifacts: [{ content: JSON.stringify([{ question_id: "q-v1-1", question_text: "V1-OWN-Q1 which tone?", impact_level: "high", answer: "V1-OWN-ANSWER formal", round: 1 }]) }],
    });
    mountShell({}, shellState({ clarifications: [] }));
    await pinV1();
    await userEvent.click(screen.getByRole("tab", { name: /steps/i }));
    await expandClarifyCard();
    expect(screen.queryByText(/V1-OWN-Q1/)).not.toBeNull();
  });

  it("ISS-1007 - shell run clarify-PAUSED, pin v1: no live answer form, v1 keeps its agent rows", async () => {
    mountShell(
      {
        clarifyQuestions: [{ id: "q-live-1", question: "LIVE-V2-PENDING which tone should the deck use?", options: ["Formal", "Casual"] }],
        onSubmitClarify: vi.fn(),
      },
      shellState({ isRunning: true, clarifications: [] }),
    );
    await pinV1();
    await userEvent.click(screen.getByRole("tab", { name: /steps/i }));
    expect(screen.queryByText(/LIVE-V2-PENDING/)).toBeNull();
    expect(screen.queryAllByTestId("steps-agent-row").length).toBeGreaterThan(0);
  });

  it("ISS-1008 - reopened run (no pin, empty pipelineState.clarifications): persisted rounds still show in Steps", async () => {
    mockGetRunArtifacts.mockResolvedValue({
      artifacts: [{ content: JSON.stringify([{ question_id: "q-v2-9", question_text: "REOPEN-Q1 which region?", impact_level: "high", answer: "REOPEN-ANSWER eu", round: 1 }]) }],
    });
    mountShell({}, shellState({ clarifications: [] }));
    await waitFor(() => expect(mockGetRunSandboxRefs).toHaveBeenCalled());
    await userEvent.click(screen.getByRole("tab", { name: /steps/i }));
    await expandClarifyCard();
    await waitFor(() => expect(screen.queryByText(/REOPEN-Q1/)).not.toBeNull());
  });
});
