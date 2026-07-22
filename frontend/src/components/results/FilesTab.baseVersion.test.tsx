import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import type { WorkflowRun } from "@/types/index";

// ─────────────────────────────────────────────────────────────────
// Base-version "From v{n-1}" Files section (B3 / POR §5 D6): real rendered-DOM
// specs for the collapsed base section + lazy parent-file fetch (UI-SPEC
// Surface 4). FilesTab fetches the parent via a DYNAMIC import("@/lib/api") on
// first expand — vi.mock intercepts it. Scaffold mirrors FilesTab.test.tsx.
// ─────────────────────────────────────────────────────────────────

const mockGetToken = vi.fn(() => "test-token");
const mockGetWorkflow = vi.fn<(token: string, id: string) => Promise<WorkflowRun>>();

vi.mock("@/lib/api", () => ({
  getToken: () => mockGetToken(),
  getWorkflow: (token: string, id: string) => mockGetWorkflow(token, id),
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

vi.mock("@/lib/exporters/storyExporter", () => ({ exportUserStories: vi.fn() }));

import { FilesTab } from "./FilesTab";

beforeEach(() => {
  mockGetToken.mockReset().mockReturnValue("test-token");
  mockGetWorkflow.mockReset();
});

describe("Base-version Files section (B3 / D6)", () => {
  it("presence + lazy fetch: a collapsed 'From v1' section renders, fetches nothing while collapsed, and loads the parent's files via getWorkflow on first expand", async () => {
    mockGetWorkflow.mockResolvedValue({
      id: "parent-1",
      type: "prototype",
      output: "<html><title>Base Proto</title></html>",
    } as WorkflowRun);

    render(
      <FilesTab
        workflowType="prototype"
        prototypeContent="<html><title>My Proto</title></html>"
        parentRunId="parent-1"
        parentVersionNumber={1}
      />,
    );

    // Current-run file renders.
    expect(screen.getByText("my-proto.html")).toBeInTheDocument();
    // Collapsed base section toggle is present, and NO fetch has happened yet.
    const toggle = screen.getByLabelText("From version 1");
    expect(toggle).toBeInTheDocument();
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(mockGetWorkflow).not.toHaveBeenCalled();

    // Expand → lazily fetch the parent run's files.
    fireEvent.click(toggle);
    await waitFor(() => expect(mockGetWorkflow).toHaveBeenCalledWith("test-token", "parent-1"));
    // The parent's derived file row renders.
    await screen.findByText("base-proto.html");
  });

  it("absence: a non-revision run (parentRunId null) shows NO base section; the current-run file still renders", () => {
    render(
      <FilesTab
        workflowType="prototype"
        prototypeContent="<html><title>My Proto</title></html>"
        parentRunId={null}
      />,
    );

    expect(screen.queryByLabelText(/From version/)).toBeNull();
    expect(screen.queryByText(/^From v/)).toBeNull();
    // Existing behavior intact — the current-run prototype file renders.
    expect(screen.getByText("my-proto.html")).toBeInTheDocument();
    expect(mockGetWorkflow).not.toHaveBeenCalled();
  });
});
