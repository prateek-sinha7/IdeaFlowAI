import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

import { PreviewPanel } from "./PreviewPanel";

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

    // Not framed, not markdown — a download affordance instead.
    expect(container.querySelector("iframe")).toBeNull();
    expect(screen.queryByTestId("markdown-preview")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /download/i })).toBeInTheDocument();
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
});
