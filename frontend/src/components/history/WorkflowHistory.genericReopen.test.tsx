import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import type { WorkflowRun } from "@/types/index";

// ─── API mocks (hoisted before module imports) ────────────────────────────────
const mockGetToken = vi.fn(() => "test-token");
const mockGetWorkflows = vi.fn<(token: string, opts?: { limit?: number }) => Promise<WorkflowRun[]>>();
const mockGetWorkflow = vi.fn<(token: string, id: string) => Promise<WorkflowRun>>();
const mockDeleteWorkflow = vi.fn<(token: string, id: string) => Promise<void>>();

vi.mock("@/lib/api", () => ({
  getToken: () => mockGetToken(),
  getWorkflows: (token: string, opts?: { limit?: number }) => mockGetWorkflows(token, opts),
  getWorkflow: (token: string, id: string) => mockGetWorkflow(token, id),
  deleteWorkflow: (token: string, id: string) => mockDeleteWorkflow(token, id),
  // B2: WorkflowHistory now fetches the revision family on detail-open. This
  // suite doesn't assert the version timeline, so return an empty family
  // (VersionTimeline renders null for <2 members) — this only prevents the
  // undefined-mock-export throw that would otherwise crash render.
  getRunFamily: () => Promise.resolve({ root_id: "", members: [] }),
}));

// Bespoke previews stubbed so we assert WorkflowHistory's OWN dispatch. The
// generic iframe + download affordance live in WorkflowHistory itself (NOT
// stubbed). MarkdownPreview is a marker so we can assert markdown was NOT chosen
// for an HTML reopen.
vi.mock("@/components/preview/PPTPreview", () => ({
  PPTPreview: ({ content }: { content: string }) => <div data-testid="ppt-preview">{content.slice(0, 20)}</div>,
}));
vi.mock("@/components/preview/UserStoryPreview", () => ({
  UserStoryPreview: ({ content }: { content: string }) => <div data-testid="userstory-preview">{content.slice(0, 20)}</div>,
}));
vi.mock("@/components/preview/PrototypePreview", () => ({
  PrototypePreview: ({ content }: { content: string }) => <div data-testid="prototype-preview">{content.slice(0, 20)}</div>,
}));
vi.mock("@/components/preview/MarkdownPreview", () => ({
  MarkdownPreview: ({ content }: { content: string }) => <div data-testid="markdown-preview">{content.slice(0, 20)}</div>,
}));
vi.mock("@/components/preview/AppBuilderPreview", () => ({
  AppBuilderPreview: () => <div data-testid="appbuilder-preview" />,
}));
vi.mock("@/components/results/FilesTab", () => ({ FilesTab: () => <div data-testid="files-tab" /> }));
vi.mock("@/components/results/AgentThinkingTab", () => ({ AgentThinkingTab: () => <div data-testid="thinking-tab" /> }));

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

import { WorkflowHistory } from "./WorkflowHistory";

function makeRun(overrides: Partial<WorkflowRun> = {}): WorkflowRun {
  return {
    id: "run-1",
    title: "Custom run",
    type: "ppt",
    status: "completed",
    input: "do a thing",
    output: "# Slide deck\n\nSome content...",
    createdAt: new Date("2026-05-12T10:00:00Z").toISOString(),
    completedAt: new Date("2026-05-12T10:05:00Z").toISOString(),
    duration: 300,
    agentCount: 4,
    parentRunId: null,
    rootRunId: "run-1",
    ...overrides,
  };
}

beforeEach(() => {
  cleanup();
  mockGetToken.mockReset().mockReturnValue("test-token");
  mockGetWorkflows.mockReset();
  mockGetWorkflow.mockReset();
  mockDeleteWorkflow.mockReset();
});

async function renderAndOpenRun(run: WorkflowRun) {
  mockGetWorkflows.mockResolvedValue([run]);
  mockGetWorkflow.mockResolvedValue(run);
  const { container } = render(<WorkflowHistory onBack={vi.fn()} />);
  const item = await screen.findByText(run.title);
  await userEvent.click(item);
  await waitFor(() => expect(screen.getAllByText(run.title).length).toBeGreaterThan(0));
  return container;
}

const HTML_OUTPUT = "<!doctype html><html><body><h1>Custom Reopen</h1></body></html>";

describe("WorkflowHistory — generic reopen deliverable (ISS-021, 2nd facet)", () => {
  it("a no-known-branch run with HTML output renders a SANDBOXED iframe (allow-scripts, NO allow-same-origin), NOT MarkdownPreview", async () => {
    const container = await renderAndOpenRun(
      makeRun({ type: "ui_custom_proto" as never, output: HTML_OUTPUT }),
    );

    const iframe = container.querySelector("iframe");
    expect(iframe).not.toBeNull();
    // T-18-05 (BLOCKING) — exactly allow-scripts; explicitly NOT same-origin.
    expect(iframe!.getAttribute("sandbox")).toBe("allow-scripts");
    expect(iframe!.getAttribute("sandbox") || "").not.toContain("allow-same-origin");
    expect(iframe!.getAttribute("srcdoc")).toContain("Custom Reopen");
    // The OLD isMarkdown=isCustom path (escaped HTML) must NOT be taken.
    expect(screen.queryByTestId("markdown-preview")).not.toBeInTheDocument();
  });

  it("a no-known-branch run with markdown output renders MarkdownPreview (NOT an iframe)", async () => {
    const container = await renderAndOpenRun(
      makeRun({ type: "ui_custom_proto" as never, output: "# A markdown deliverable\n\nbody" }),
    );

    expect(screen.getByTestId("markdown-preview")).toBeInTheDocument();
    expect(container.querySelector("iframe")).toBeNull();
  });

  it("a reopened `custom` MARKDOWN run still renders MarkdownPreview (no regression)", async () => {
    const container = await renderAndOpenRun(
      makeRun({ type: "custom", output: "# Custom markdown\n\nbody" }),
    );
    expect(screen.getByTestId("markdown-preview")).toBeInTheDocument();
    expect(container.querySelector("iframe")).toBeNull();
  });

  it("NO REGRESSION — reopened ppt renders the bespoke PPTPreview (generic iframe not taken)", async () => {
    await renderAndOpenRun(makeRun({ type: "ppt", output: "<html>deck</html>" }));
    expect(screen.getByTestId("ppt-preview")).toBeInTheDocument();
  });

  it("NO REGRESSION — reopened prototype renders the bespoke PrototypePreview", async () => {
    await renderAndOpenRun(makeRun({ id: "run-2", type: "prototype", output: "<html>proto</html>" }));
    expect(screen.getByTestId("prototype-preview")).toBeInTheDocument();
  });

  it("NO REGRESSION — reopened user_stories renders the bespoke UserStoryPreview (no iframe)", async () => {
    const container = await renderAndOpenRun(makeRun({ id: "run-3", type: "user_stories", output: "# Stories\nbody" }));
    expect(screen.getByTestId("userstory-preview")).toBeInTheDocument();
    expect(container.querySelector("iframe")).toBeNull();
  });
});
