import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

import { PreviewPanel } from "./PreviewPanel";
import type { PipelineRunState } from "@/types/index";

// Terminal (not-running) pipeline state — models a completed reopen. Mirrors the
// helper in PreviewPanel.degraded.test.tsx.
function terminalPipelineState(overrides: Partial<PipelineRunState> = {}): PipelineRunState {
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
vi.mock("./AppBuilderPreview", () => ({ AppBuilderPreview: () => <div data-testid="appbuilder-preview" /> }));
vi.mock("@/components/results/FilesTab", () => ({ FilesTab: () => <div data-testid="files-tab" /> }));
vi.mock("@/components/results/AgentThinkingTab", () => ({ AgentThinkingTab: () => <div data-testid="thinking-tab" /> }));

const HTML_DELIVERABLE = "<!doctype html><html><body><h1>Custom Output</h1></body></html>";

describe("PreviewPanel — generic mimetype-dispatched deliverable (ISS-021, live)", () => {
  it("unknown type + text/html → renders a SANDBOXED iframe (sandbox=allow-scripts, NO allow-same-origin), NOT the empty state", () => {
    const { container } = render(
      <PreviewPanel
        // A pipeline_type that matches none of the known render branches.
        workflowType={"ui_custom_proto" as never}
        isStreaming={false}
        genericDeliverable={{ mimetype: "text/html", filename: "custom.html", content: HTML_DELIVERABLE }}
      />,
    );

    const iframe = container.querySelector("iframe");
    expect(iframe).not.toBeNull();
    // T-18-05 (BLOCKING): exactly allow-scripts, and explicitly NOT same-origin.
    expect(iframe!.getAttribute("sandbox")).toBe("allow-scripts");
    expect(iframe!.getAttribute("sandbox") || "").not.toContain("allow-same-origin");
    // The HTML is framed via srcDoc, not escaped through markdown.
    expect(iframe!.getAttribute("srcdoc")).toContain("Custom Output");
    expect(screen.queryByTestId("markdown-preview")).not.toBeInTheDocument();
    expect(screen.queryByText(/output will appear here/i)).not.toBeInTheDocument();
  });

  // ─── CR-01 (18 review) regression lock ──────────────────────────────────────
  // `custom` is the ACTUAL pipeline_type the live agent-composer emits. It must
  // NOT be a known render branch (which routed it to MarkdownPreview → escaped
  // HTML). A LIVE custom run with text/html must render the SANDBOXED iframe,
  // agreeing with the reopen surface. A live custom markdown run must still
  // render MarkdownPreview (no regression to existing markdown-custom reports).
  it("CR-01 — LIVE `custom` + text/html → SANDBOXED iframe (NOT MarkdownPreview)", () => {
    const { container } = render(
      <PreviewPanel
        workflowType="custom"
        isStreaming={false}
        genericDeliverable={{ mimetype: "text/html", filename: "custom.html", content: HTML_DELIVERABLE }}
      />,
    );

    const iframe = container.querySelector("iframe");
    expect(iframe).not.toBeNull();
    expect(iframe!.getAttribute("sandbox")).toBe("allow-scripts");
    expect(iframe!.getAttribute("sandbox") || "").not.toContain("allow-same-origin");
    expect(iframe!.getAttribute("srcdoc")).toContain("Custom Output");
    // The bug was: custom HTML rendered through MarkdownPreview (escaped text).
    expect(screen.queryByTestId("markdown-preview")).not.toBeInTheDocument();
  });

  it("CR-01 — LIVE `custom` + text/markdown → MarkdownPreview (no regression)", () => {
    const { container } = render(
      <PreviewPanel
        workflowType="custom"
        isStreaming={false}
        genericDeliverable={{ mimetype: "text/markdown", content: "# Custom report\n\nbody" }}
      />,
    );

    expect(screen.getByTestId("markdown-preview")).toBeInTheDocument();
    expect(container.querySelector("iframe")).toBeNull();
  });

  it("unknown type + text/markdown → renders MarkdownPreview (NOT an iframe)", () => {
    const { container } = render(
      <PreviewPanel
        workflowType={"ui_custom_proto" as never}
        isStreaming={false}
        genericDeliverable={{ mimetype: "text/markdown", content: "# Hello\n\nbody" }}
      />,
    );

    expect(screen.getByTestId("markdown-preview")).toBeInTheDocument();
    expect(container.querySelector("iframe")).toBeNull();
  });

  it("unknown type + application/zip → renders the file-bundle (AppBuilder) view", () => {
    render(
      <PreviewPanel
        workflowType={"ui_custom_proto" as never}
        isStreaming={false}
        genericDeliverable={{
          mimetype: "application/zip",
          filename: "bundle.zip",
          content: "```filename: app/main.py\nprint('hi')\n```",
        }}
      />,
    );

    expect(screen.getByTestId("appbuilder-preview")).toBeInTheDocument();
  });

  it("unknown type + unknown mimetype → a safe download affordance (no inline/iframe execution)", () => {
    const { container } = render(
      <PreviewPanel
        workflowType={"ui_custom_proto" as never}
        isStreaming={false}
        genericDeliverable={{ mimetype: "application/octet-stream", filename: "data.bin", content: "rawbytes" }}
      />,
    );

    // Not framed, not markdown — a download affordance instead. Scope to the
    // deliverable's own "Download <filename>" button so it is not confused with
    // the Phase-39 run-header "Download the deliverable" button.
    expect(container.querySelector("iframe")).toBeNull();
    expect(screen.queryByTestId("markdown-preview")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /download data\.bin/i })).toBeInTheDocument();
  });

  it("NO REGRESSION — known renderTypes still render their bespoke renderers; the generic branch is NOT taken", () => {
    const { rerender, container } = render(
      <PreviewPanel workflowType="user_stories" isStreaming={false} userStoryContent="# Stories" />,
    );
    expect(screen.getByTestId("user-story-preview")).toBeInTheDocument();
    expect(container.querySelector("iframe")).toBeNull();

    rerender(<PreviewPanel workflowType="ppt" isStreaming={false} pptContent="<html>deck</html>" />);
    expect(screen.getByTestId("ppt-preview")).toBeInTheDocument();

    rerender(<PreviewPanel workflowType="prototype" isStreaming={false} prototypeContent="<html>proto</html>" />);
    expect(screen.getByTestId("proto-preview")).toBeInTheDocument();

    rerender(<PreviewPanel workflowType="app_builder" isStreaming={false} userStoryContent="```filename: a.py\nx\n```" />);
    expect(screen.getByTestId("appbuilder-preview")).toBeInTheDocument();
  });

  it("a known type whose content is present does NOT fall into the generic channel even if a generic deliverable is also set", () => {
    render(
      <PreviewPanel
        workflowType="user_stories"
        isStreaming={false}
        userStoryContent="# Real stories"
        genericDeliverable={{ mimetype: "text/html", content: HTML_DELIVERABLE }}
      />,
    );
    // The bespoke user-stories renderer wins; no generic iframe.
    expect(screen.getByTestId("user-story-preview")).toBeInTheDocument();
  });

  // ─── 22-07 (UXFIX-04 / D-21) — generic mimetype renderer is PRIMARY ──────────
  // The dispatch is a mimetype-dispatch TABLE: the generic renderer is the
  // PRIMARY route and the 4 first-party types are registered entries the
  // dispatcher routes to. A custom/unknown deliverable renders via the generic
  // path as the primary route (not reached only after 4 first-party branches
  // fail), and the first-party types still render identically (no regression).
  describe("22-07 UXFIX-04 — generic-primary mimetype-dispatch table", () => {
    it("a custom deliverable renders via the generic path as the PRIMARY route", () => {
      const { container } = render(
        <PreviewPanel
          workflowType="custom"
          isStreaming={false}
          genericDeliverable={{ mimetype: "text/html", filename: "out.html", content: HTML_DELIVERABLE }}
        />,
      );
      // Primary route → the generic sandboxed iframe, with the P18 contract.
      const iframe = container.querySelector("iframe");
      expect(iframe).not.toBeNull();
      expect(iframe!.getAttribute("sandbox")).toBe("allow-scripts");
      expect(iframe!.getAttribute("sandbox") || "").not.toContain("allow-same-origin");
    });

    it("each of the 4 first-party types routes through the dispatch table and renders its bespoke renderer (no regression)", () => {
      const cases: { type: string; props: Record<string, unknown>; testid: string }[] = [
        { type: "user_stories", props: { userStoryContent: "# S" }, testid: "user-story-preview" },
        { type: "ppt", props: { pptContent: "<html>deck</html>" }, testid: "ppt-preview" },
        { type: "prototype", props: { prototypeContent: "<html>proto</html>" }, testid: "proto-preview" },
        { type: "app_builder", props: { userStoryContent: "```filename: a.py\nx\n```" }, testid: "appbuilder-preview" },
      ];
      for (const c of cases) {
        const { unmount, container } = render(
          <PreviewPanel workflowType={c.type as never} isStreaming={false} {...c.props} />,
        );
        expect(screen.getByTestId(c.testid)).toBeInTheDocument();
        // A first-party type must NOT leak into the generic iframe.
        expect(container.querySelector("iframe")).toBeNull();
        unmount();
      }
    });

    it("a brand-new (unmapped) workflow type with a markdown deliverable routes generically with ZERO first-party branch", () => {
      // SC-001 dividend: a workflow the FE has never heard of still renders via
      // the mimetype-keyed table — no per-workflow-name branch needed.
      render(
        <PreviewPanel
          workflowType={"totally_new_workflow_2026" as never}
          isStreaming={false}
          genericDeliverable={{ mimetype: "text/markdown", content: "# Brand new\n\nbody" }}
        />,
      );
      expect(screen.getByTestId("markdown-preview")).toBeInTheDocument();
    });
  });

  // ─── BUG-008 — reopened generic deliverable survives a STALE workflowType ─────
  // On a terminal reopen the `isRunning`-gated workflowType binder never fires, so
  // `workflowType` sits at the stale "user_stories" default → `isKnownRenderType`
  // is true. Before the fix that starved `hasGenericDeliverable` and the Preview
  // short-circuited to "Output will appear here". After the fix a PRESENT generic
  // deliverable renders whenever the typed renderer for the (stale) renderType has
  // nothing to show — routing through the unchanged P18 sandboxed iframe.
  describe("BUG-008 — reopened generic deliverable survives a STALE workflowType", () => {
    it("stale workflowType='user_stories' + empty typed content + text/html generic → SANDBOXED iframe, NOT the empty state", () => {
      const { container } = render(
        <PreviewPanel
          workflowType="user_stories"
          userStoryContent=""
          pptContent=""
          prototypeContent=""
          isStreaming={false}
          pipelineState={terminalPipelineState()}
          genericDeliverable={{ mimetype: "text/html", filename: "reopen.html", content: HTML_DELIVERABLE }}
        />,
      );

      const iframe = container.querySelector("iframe");
      expect(iframe).not.toBeNull();
      // P18 contract preserved: exactly allow-scripts, never same-origin.
      expect(iframe!.getAttribute("sandbox")).toBe("allow-scripts");
      expect(iframe!.getAttribute("sandbox") || "").not.toContain("allow-same-origin");
      expect(iframe!.getAttribute("srcdoc")).toContain("Custom Output");
      expect(screen.queryByText(/output will appear here/i)).not.toBeInTheDocument();
    });

    it("stale workflowType='user_stories' + empty typed content + text/markdown generic → MarkdownPreview, no iframe", () => {
      const { container } = render(
        <PreviewPanel
          workflowType="user_stories"
          userStoryContent=""
          pptContent=""
          prototypeContent=""
          isStreaming={false}
          pipelineState={terminalPipelineState()}
          genericDeliverable={{ mimetype: "text/markdown", content: "# Hi\n\nbody" }}
        />,
      );

      expect(screen.getByTestId("markdown-preview")).toBeInTheDocument();
      expect(container.querySelector("iframe")).toBeNull();
      expect(screen.queryByText(/output will appear here/i)).not.toBeInTheDocument();
    });
  });
});
