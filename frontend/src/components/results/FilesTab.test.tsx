import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

import { FilesTab } from "./FilesTab";

// Same motion mock as the other component tests so role-based queries
// can still find buttons inside motion.button etc.
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

// Stub the user-story exporter so we don't drag the markdown export
// pipeline into the test environment.
vi.mock("@/lib/exporters/storyExporter", () => ({
  exportUserStories: vi.fn(),
}));

describe("FilesTab — per-agent output section", () => {
  it("shows 'No files available' when both final and agent outputs are absent", () => {
    render(<FilesTab workflowType={"ppt"} />);
    expect(screen.getByText(/no files available/i)).toBeInTheDocument();
  });

  it("renders the Final-output hero (naming the derived deliverable) and no agent section when no agent files are present", () => {
    render(
      <FilesTab
        workflowType={"user_stories"}
        userStoryContent={"# Heading\n\nbody text"}
      />,
    );
    // The dark hero always carries a "Final output" eyebrow when a deliverable
    // exists; the deliverable name is the live-derived filename.
    expect(screen.getByText(/^final output$/i)).toBeInTheDocument();
    expect(screen.getByText("heading.md")).toBeInTheDocument();
    // No agent-outputs section when there are no agent files.
    expect(screen.queryByText(/^agent outputs/i)).not.toBeInTheDocument();
  });

  it("renders BOTH the Final-output hero and the per-agent outputs section", () => {
    render(
      <FilesTab
        workflowType={"user_stories"}
        userStoryContent={"# Final\nfinal body"}
        agentOutputs={[
          { name: "Domain Discovery Agent", role: "Research", output: "discovery text", agentId: "domain-analyst" },
          { name: "Backlog Architecture Agent", role: "Story Composition", output: "backlog text", agentId: "epic-architect" },
        ]}
      />,
    );
    expect(screen.getByText(/^final output$/i)).toBeInTheDocument();
    expect(screen.getByText(/agent outputs \(2\)/i)).toBeInTheDocument();
    // Both individual agent files appear as 01- / 02- prefixed markdown.
    expect(screen.getByText("01-domain-discovery-agent.md")).toBeInTheDocument();
    expect(screen.getByText("02-backlog-architecture-agent.md")).toBeInTheDocument();
    // Counter at the top includes BOTH final + agent files (1 final + 2 agents = 3).
    expect(screen.getByText(/3 files available/i)).toBeInTheDocument();
    // The subline also names the deliverable count.
    expect(screen.getByText(/1 deliverable/i)).toBeInTheDocument();
  });

  it("the Final-output hero fires the download handler and surfaces the optional Preview action", () => {
    const onOpenPreview = vi.fn();
    render(
      <FilesTab
        workflowType={"user_stories"}
        userStoryContent={"# Heading\n\nbody"}
        onOpenPreview={onOpenPreview}
      />,
    );
    // Preview action renders only when onOpenPreview is provided, and fires it.
    const preview = screen.getByRole("button", { name: /^preview$/i });
    preview.click();
    expect(onOpenPreview).toHaveBeenCalledTimes(1);
    // The hero + header both expose a Download control (Download / Download All).
    expect(screen.getByRole("button", { name: /download all/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^download$/i })).toBeInTheDocument();
  });

  it("omits the hero Preview action when onOpenPreview is not wired", () => {
    render(<FilesTab workflowType={"user_stories"} userStoryContent={"# Heading\n\nbody"} />);
    expect(screen.queryByRole("button", { name: /^preview$/i })).not.toBeInTheDocument();
  });

  it("skips agent entries with empty output", () => {
    render(
      <FilesTab
        workflowType={"user_stories"}
        userStoryContent={"# Final\nbody"}
        agentOutputs={[
          { name: "Agent A", output: "real content" },
          { name: "Agent B", output: "" },          // skipped (empty string)
          { name: "Agent C", output: "   \n  " },     // skipped (whitespace-only)
          { name: "Agent D", output: "more content" },
        ]}
      />,
    );
    expect(screen.getByText(/agent outputs \(2\)/i)).toBeInTheDocument();
    expect(screen.getByText("01-agent-a.md")).toBeInTheDocument();
    expect(screen.getByText("02-agent-d.md")).toBeInTheDocument();
    expect(screen.queryByText("02-agent-b.md")).not.toBeInTheDocument();
    expect(screen.queryByText("03-agent-c.md")).not.toBeInTheDocument();
  });

  it("renders agent outputs even when there are zero final-output files", () => {
    // E.g. a `custom` run with no final output (edge case) — the per-agent
    // files should still be visible so the user can see intermediate work.
    render(
      <FilesTab
        workflowType={"ppt"}
        agentOutputs={[
          { name: "Agent X", output: "content X" },
        ]}
      />,
    );
    expect(screen.queryByText(/no files available/i)).not.toBeInTheDocument();
    // No 'Final output' header (zero final files), only the agent section.
    expect(screen.queryByText(/^final output$/i)).not.toBeInTheDocument();
    expect(screen.getByText(/agent outputs \(1\)/i)).toBeInTheDocument();
    expect(screen.getByText("01-agent-x.md")).toBeInTheDocument();
  });
});

// ─── ISS-021 (18-03) — generic deliverable row ────────────────────────────────
describe("FilesTab — generic deliverable row (ISS-021)", () => {
  it("a present generic deliverable yields exactly ONE generic row, with the resolved filename", () => {
    render(
      <FilesTab
        // An unknown pipeline_type that hits no known FileTab branch.
        workflowType={"ui_custom_proto" as never}
        genericDeliverable={{ mimetype: "text/html", filename: "custom.html", content: "<!doctype html><html></html>" }}
      />,
    );
    // Exactly one generic row, named from the resolved filename.
    expect(screen.getByText("custom.html")).toBeInTheDocument();
    expect(screen.getByText(/1 file available/i)).toBeInTheDocument();
  });

  it("derives a filename from the mimetype when deliverable_filename is absent", () => {
    render(
      <FilesTab
        workflowType={"ui_custom_proto" as never}
        genericDeliverable={{ mimetype: "text/markdown", content: "# md" }}
      />,
    );
    expect(screen.getByText("deliverable.md")).toBeInTheDocument();
  });

  it("the generic row coexists with the per-agent .md outputs (both visible)", () => {
    render(
      <FilesTab
        workflowType={"ui_custom_proto" as never}
        genericDeliverable={{ mimetype: "text/html", filename: "out.html", content: "<!doctype html><html></html>" }}
        agentOutputs={[
          { name: "Agent One", output: "one" },
          { name: "Agent Two", output: "two" },
        ]}
      />,
    );
    // Generic deliverable row + both per-agent rows.
    expect(screen.getByText("out.html")).toBeInTheDocument();
    expect(screen.getByText(/agent outputs \(2\)/i)).toBeInTheDocument();
    expect(screen.getByText("01-agent-one.md")).toBeInTheDocument();
    expect(screen.getByText("02-agent-two.md")).toBeInTheDocument();
    // 1 deliverable + 2 agent files = 3 total.
    expect(screen.getByText(/3 files available/i)).toBeInTheDocument();
  });

  it("does NOT add a generic row for a known type (the generic channel is a fallback only)", () => {
    render(
      <FilesTab
        workflowType={"user_stories"}
        userStoryContent={"# Stories\nbody"}
        // Even if a stale generic deliverable were passed, a known-type final
        // file already exists → the generic row is suppressed (files.length>0).
        genericDeliverable={{ mimetype: "text/html", filename: "stale.html", content: "<!doctype html>" }}
      />,
    );
    expect(screen.getByText("stories.md")).toBeInTheDocument();
    expect(screen.queryByText("stale.html")).not.toBeInTheDocument();
  });
});
