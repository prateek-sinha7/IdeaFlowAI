import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import type { WorkflowRun } from "@/types/index";

// ISS-972 (sibling of ISS-665 / QA-KB-053) — expanding "From v{n-1}" resolves the
// parent's file via resolveRunDeliverable with no ref, i.e. from the live tree
// (the NEWEST member's file). Fixed: the parent's own git tag is threaded through.

const mockResolve = vi.fn();
const mockGetWorkflow = vi.fn<(token: string, id: string) => Promise<WorkflowRun>>();
vi.mock("@/lib/api", () => ({
  getToken: () => "test-token",
  getWorkflow: (t: string, id: string) => mockGetWorkflow(t, id),
  resolveRunDeliverable: (...args: unknown[]) => mockResolve(...args),
}));
vi.mock("motion/react", () => ({
  motion: new Proxy({}, {
    get: (_t, prop: string) => ({ children, ...rest }: { children?: React.ReactNode } & Record<string, unknown>) =>
      React.createElement(prop, Object.fromEntries(Object.entries(rest).filter(([k]) => !["initial", "animate", "exit", "transition", "layout", "layoutId", "variants", "whileHover", "whileTap"].includes(k))), children),
  }),
  AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));
vi.mock("@/lib/exporters/storyExporter", () => ({ exportUserStories: vi.fn() }));

import { FilesTab } from "./FilesTab";

beforeEach(() => {
  mockResolve.mockReset().mockResolvedValue(null);
  mockGetWorkflow.mockReset();
});

describe("Base-version Files section — parent ref (ISS-972)", () => {
  it("ISS-972: resolves the parent's deliverable at the parent's own tag, not the live tree", async () => {
    mockGetWorkflow.mockResolvedValue({
      id: "parent-1", type: "prototype", deliverableFilename: "prototype.html",
      output: "<html><title>Base Proto</title></html>",
    } as WorkflowRun);

    render(
      <FilesTab workflowType="prototype" prototypeContent="<html><title>My</title></html>"
        parentRunId="parent-1" parentVersionNumber={1} parentGitTag="v1" />,
    );
    fireEvent.click(screen.getByLabelText("From version 1"));
    await waitFor(() => expect(mockResolve).toHaveBeenCalled());

    expect(mockResolve.mock.calls[0][3]).toBe("v1");
  });
});
