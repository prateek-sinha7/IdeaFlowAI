import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

// ─────────────────────────────────────────────────────────────────
// "Build incomplete" banner (Phase 39-03, W6): renders ONLY when
// status is failed/degraded AND no deliverable is present.
// ─────────────────────────────────────────────────────────────────

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

vi.mock("@/lib/exporters/storyExporter", () => ({ exportUserStories: vi.fn() }));

import { FilesTab } from "./FilesTab";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("Build incomplete banner", () => {
  it("(case 1) degraded status with deliverable present: banner NOT rendered", () => {
    // Degraded run that HAS a prototype deliverable.
    render(
      <FilesTab
        workflowType="prototype"
        prototypeContent="<html><title>My Proto</title></html>"
        runStatus="degraded"
      />,
    );

    // The deliverable file should render.
    expect(screen.getByText("my-proto.html")).toBeInTheDocument();
    // Banner should NOT be present.
    expect(
      screen.queryByText(/Build incomplete.*only the planning artifacts/),
    ).not.toBeInTheDocument();
  });

  it("(case 2) failed status with no deliverable but agent outputs: banner rendered", () => {
    // Failed run with no final deliverable, but has agent outputs (e.g., from planning agents).
    render(
      <FilesTab
        workflowType="prototype"
        prototypeContent={undefined}
        agentOutputs={[
          { name: "Planner", output: "# Planning notes\nSome planning work" },
        ]}
        runStatus="failed"
      />,
    );

    // No final deliverable should be present.
    expect(screen.queryByText(/prototype.html|Final output/)).not.toBeInTheDocument();
    // Agent output should render (via genericAgentFiles).
    expect(screen.getByText("01-planner.md")).toBeInTheDocument();
    // Banner SHOULD be present.
    expect(
      screen.getByText(/Build incomplete.*only the planning artifacts/),
    ).toBeInTheDocument();
  });

  it("(case 3) completed status: banner NOT rendered", () => {
    // Completed run (runStatus undefined, the default).
    render(
      <FilesTab
        workflowType="prototype"
        prototypeContent="<html><title>My Proto</title></html>"
        runStatus={undefined}
      />,
    );

    // Deliverable should render.
    expect(screen.getByText("my-proto.html")).toBeInTheDocument();
    // Banner should NOT be present.
    expect(
      screen.queryByText(/Build incomplete.*only the planning artifacts/),
    ).not.toBeInTheDocument();
  });
});
