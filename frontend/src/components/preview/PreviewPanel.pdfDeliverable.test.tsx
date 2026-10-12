import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { PreviewPanel } from "./PreviewPanel";
import type { PipelineRunState } from "@/types/index";
// Terminal (not-running) pipeline state — models a completed reopen. Mirrors the
// helper in PreviewPanel.degraded.test.tsx.
function _terminalPipelineState(overrides: Partial<PipelineRunState> = {}): PipelineRunState {
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
// ─── Motion mock (same as the other PreviewPanel-area component tests) ────────
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
// Stub the heavy bespoke preview children so we assert on PreviewPanel's own
// dispatch, not the children's internals. The generic iframe + download
// affordance live in PreviewPanel itself (not stubbed). MarkdownPreview is
// stubbed to a marker so we can assert markdown was chosen (NOT an iframe).
vi.mock("./UserStoryPreview", () => ({
  UserStoryPreview: ({ content }: { content: string }) => <div data-testid="user-story-preview">{content}</div>,
}));
vi.mock("./PPTPreview", () => ({ PPTPreview: () => <div data-testid="ppt-preview" /> }));
vi.mock("./PrototypePreview", () => ({ PrototypePreview: () => <div data-testid="proto-preview" /> }));
vi.mock("./MarkdownPreview", () => ({ MarkdownPreview: ({ content }: { content: string }) => <div data-testid="markdown-preview">{content}</div> }));
vi.mock("./SandboxPdfPreview", () => ({
  SandboxPdfPreview: ({ runId, path, fallback }: { runId: string; path: string; fallback: React.ReactNode }) => (
    <div data-testid="pdf-preview" data-run={runId} data-path={path}><div data-testid="pdf-fallback">{fallback}</div></div>
  ),
}));
vi.mock("./AppBuilderPreview", () => ({ AppBuilderPreview: () => <div data-testid="appbuilder-preview" /> }));
vi.mock("@/components/results/FilesTab", () => ({
  FilesTab: () => <div data-testid="files-tab" />,
  deriveDeliverableFilename: (workflowType: string, content?: string, fallback?: string) => {
    if (workflowType === "user_stories" || workflowType === "user_stories_revision") {
      return fallback || "user-stories.md";
    }
    if (workflowType === "custom") {
      return fallback || "custom-output.md";
    }
    if (workflowType === "ppt" || workflowType === "ppt_revision") {
      return fallback || "presentation.html";
    }
    if (workflowType === "prototype" || workflowType === "prototype_revision") {
      return fallback || "prototype.html";
    }
    if (workflowType === "app_builder" || workflowType === "app_builder_revision") {
      return "project.zip";
    }
    return fallback || "deliverable";
  },
}));
vi.mock("@/components/results/AgentThinkingTab", () => ({ AgentThinkingTab: () => <div data-testid="thinking-tab" /> }));
const MD = { mimetype: "text/markdown", filename: "backlog.md", content: "# Backlog" };
// The contract: a PDF deliverable carries its text form inline; the viewer reads the file.
const PDF = { mimetype: "application/pdf", filename: "Backlog.pdf", content: "# Backlog" };

describe("PreviewPanel — a PDF deliverable renders in the PDF viewer (dispatch on mimetype)", () => {
  it("application/pdf → the PDF viewer, reading the declared file of this run", () => {
    render(<PreviewPanel workflowType={"custom" as never} rawPipelineType="custom" liveRunId="run-1" isStreaming={false} genericDeliverable={PDF} />);
    const pdf = screen.getByTestId("pdf-preview");
    expect(pdf.getAttribute("data-run")).toBe("run-1");
    expect(pdf.getAttribute("data-path")).toBe("Backlog.pdf");
    expect(screen.queryByText(/output will appear here/i)).not.toBeInTheDocument();
  });

  it("the preview's address bar names the declared PDF", () => {
    render(<PreviewPanel workflowType={"custom" as never} rawPipelineType="custom" liveRunId="run-1" isStreaming={false} genericDeliverable={PDF} />);
    expect(screen.getAllByText("Backlog.pdf").length).toBeGreaterThan(0);
  });

  it("text/markdown → the markdown preview, no PDF viewer (unchanged)", () => {
    render(<PreviewPanel workflowType={"custom" as never} rawPipelineType="custom" liveRunId="run-1" isStreaming={false} genericDeliverable={MD} />);
    expect(screen.queryByTestId("pdf-preview")).not.toBeInTheDocument();
    expect(screen.getByTestId("markdown-preview")).toBeInTheDocument();
  });
});
