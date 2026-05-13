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

  it("renders the final output without the 'Final output' header when no agent files are present", () => {
    render(
      <FilesTab
        workflowType={"user_stories"}
        userStoryContent={"# Heading\n\nbody text"}
      />,
    );
    expect(screen.queryByText(/^final output$/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^agent outputs/i)).not.toBeInTheDocument();
    // The final markdown file is listed (name derived from first heading).
    expect(screen.getByText("heading.md")).toBeInTheDocument();
  });

  it("renders BOTH final and per-agent outputs with section headers", () => {
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
    expect(screen.getByText(/^3 files available$/i)).toBeInTheDocument();
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
