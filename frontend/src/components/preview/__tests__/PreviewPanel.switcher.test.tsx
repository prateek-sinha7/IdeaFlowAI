import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import React from "react";
import { PreviewPanel } from "../PreviewPanel";
// ─── Motion mock (mirrors the sibling PreviewPanel-area component tests) ──────
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
// Stub the heavy bespoke children so we assert on PreviewPanel's OWN dispatch +
// switcher, not the children's internals. The generic iframe + MarkdownPreview
// markers let us tell WHICH renderer the dispatch/override chose.
vi.mock("../UserStoryPreview", () => ({
  UserStoryPreview: ({ content }: { content: string }) => <div data-testid="user-story-preview">{content}</div>,
}));
vi.mock("../PPTPreview", () => ({ PPTPreview: () => <div data-testid="ppt-preview" /> }));
vi.mock("../PrototypePreview", () => ({ PrototypePreview: () => <div data-testid="proto-preview" /> }));
vi.mock("../MarkdownPreview", () => ({ MarkdownPreview: ({ content }: { content: string }) => <div data-testid="markdown-preview">{content}</div> }));
vi.mock("../AppBuilderPreview", () => ({ AppBuilderPreview: () => <div data-testid="appbuilder-preview" /> }));
// ─── slugify mock — mirrors FilesTab's real slugify ─────────────────────────
const slugifyMock = (raw: string, maxWords = 8): string => {
  const clean = raw.replace(/[^a-zA-Z0-9\s]/g, "").trim();
  const words = clean.split(/\s+/).filter(Boolean).slice(0, maxWords);
  return words.join("-").toLowerCase();
};

vi.mock("@/components/results/FilesTab", () => ({
  FilesTab: () => <div data-testid="files-tab" />,
  deriveDeliverableFilename: (workflowType: string, content?: string, fallback?: string) => {
    if (workflowType === "user_stories" || workflowType === "user_stories_revision") {
      if (content) {
        const h = content.match(/^#\s+(.+)/m);
        const stem = h ? slugifyMock(h[1]) : "user-stories";
        return `${stem || "user-stories"}.md`;
      }
      return fallback || "user-stories.md";
    }
    if (workflowType === "custom") {
      if (content) {
        const h = content.match(/^#\s+(.+)/m);
        const stem = h ? slugifyMock(h[1]) : "custom-output";
        return `${stem || "custom-output"}.md`;
      }
      return fallback || "custom-output.md";
    }
    if (workflowType === "ppt" || workflowType === "ppt_revision") {
      if (content) {
        const t = content.match(/<title>([^<]+)<\/title>/i);
        const h1 = content.match(/<h1[^>]*>([^<]+)<\/h1>/i);
        let stem = "presentation";
        if (t && t[1] !== "Presentation") stem = slugifyMock(t[1]) || "presentation";
        else if (h1) stem = slugifyMock(h1[1]) || "presentation";
        return `${stem}.html`;
      }
      return fallback || "presentation.html";
    }
    if (workflowType === "prototype" || workflowType === "prototype_revision") {
      if (content) {
        const t = content.match(/<title>(.+?)<\/title>/i);
        const stem = t ? slugifyMock(t[1]) : "prototype";
        return `${stem || "prototype"}.html`;
      }
      return fallback || "prototype.html";
    }
    if (workflowType === "app_builder" || workflowType === "app_builder_revision") {
      return "project.zip";
    }
    return fallback || "deliverable";
  },
}));
vi.mock("@/components/results/AgentThinkingTab", () => ({ AgentThinkingTab: () => <div data-testid="thinking-tab" /> }));
const HTML_DELIVERABLE = "<!doctype html><html><body><h1>Custom Output</h1></body></html>";
const MD_DELIVERABLE = "# Markdown Output\n\nSome body text.";
describe("PreviewPanel — typed-renderer switcher (plan 07, manual override over generic dispatch)", () => {
  it("DEFAULT: the generic FIRST_PARTY_RENDERERS dispatch is PRIMARY and unchanged (first-party type renders its bespoke renderer)", () => {
    render(
      <PreviewPanel
        workflowType="user_stories"
        userStoryContent="# A user story"
      />,
    );
    // No override → the generic dispatch routes the first-party user_stories
    // renderType to its bespoke renderer, exactly as before the switcher existed.
    expect(screen.getByTestId("user-story-preview")).toBeInTheDocument();
  });
  it("DEFAULT: a generic (unknown-workflow) text/html deliverable auto-dispatches to the sandboxed iframe (generic route unchanged)", () => {
    const { container } = render(
      <PreviewPanel
        workflowType={"ui_custom_proto" as never}
        genericDeliverable={{ content: HTML_DELIVERABLE, mimetype: "text/html", filename: "out.html" }}
      />,
    );
    const iframe = container.querySelector("iframe");
    expect(iframe).not.toBeNull();
    expect(iframe?.getAttribute("sandbox")).toBe("allow-scripts");
    expect(iframe?.getAttribute("title")).toBe("Deliverable Preview");
  });
  it("OVERRIDE: selecting a typed renderer forces it over the auto-selected one (markdown auto → HTML override renders the iframe)", () => {
    const { container } = render(
      <PreviewPanel
        workflowType={"ui_custom_proto" as never}
        genericDeliverable={{ content: MD_DELIVERABLE, mimetype: "text/markdown", filename: "out.md" }}
      />,
    );
    // Auto: text/markdown → MarkdownPreview; no iframe yet.
    expect(screen.getByTestId("markdown-preview")).toBeInTheDocument();
    expect(container.querySelector("iframe")).toBeNull();
    // Manually override to the HTML typed renderer.
    const htmlPill = screen.getByRole("button", { name: /^HTML$/i });
    fireEvent.click(htmlPill);
    // The override forces the sandboxed-iframe (HTML) renderer; markdown is gone.
    const iframe = container.querySelector("iframe");
    expect(iframe).not.toBeNull();
    expect(iframe?.getAttribute("sandbox")).toBe("allow-scripts");
    expect(screen.queryByTestId("markdown-preview")).toBeNull();
  });
  it("CLEAR: returning the switcher to Auto restores the generic auto-dispatch", () => {
    const { container } = render(
      <PreviewPanel
        workflowType={"ui_custom_proto" as never}
        genericDeliverable={{ content: MD_DELIVERABLE, mimetype: "text/markdown", filename: "out.md" }}
      />,
    );
    // Override → HTML iframe.
    const htmlPill = screen.getByRole("button", { name: /^HTML$/i });
    fireEvent.click(htmlPill);
    expect(container.querySelector("iframe")).not.toBeNull();
    // Clear → back to the generic auto-dispatch (markdown), iframe gone.
    const autoPill = screen.getByRole("button", { name: /^Auto$/i });
    fireEvent.click(autoPill);
    expect(screen.getByTestId("markdown-preview")).toBeInTheDocument();
    expect(container.querySelector("iframe")).toBeNull();
  });
  it("SC-001: the switcher option VALUES are generic renderType/mimetype tokens, never a workflow name", () => {
    render(
      <PreviewPanel
        workflowType={"ui_custom_proto" as never}
        genericDeliverable={{ content: MD_DELIVERABLE, mimetype: "text/markdown", filename: "out.md" }}
      />,
    );
    // The switcher pills represent renderType/mimetype tokens (SC-001, never a workflow name).
    // We expect: "Auto", "HTML", "Markdown", "Bundle" pills.
    const pills = screen.getAllByTestId("renderer-pill");
    const labels = pills.map((p) => p.textContent);
    // Every pill label is a structural renderType / mimetype token label.
    const ALLOWED = new Set(["Auto", "HTML", "Markdown", "Bundle", "User Stories", "Slides", "Prototype", "Code"]);
    for (const label of labels) expect(label && ALLOWED.has(label)).toBe(true);
    // Explicitly NOT keyed on any workflow name / raw pipeline type.
    const FORBIDDEN = ["od_prototype", "od_ppt", "prototype_revision", "app_builder_revision", "ui_custom_proto"];
    for (const bad of FORBIDDEN) expect(labels).not.toContain(bad);
  });
});
