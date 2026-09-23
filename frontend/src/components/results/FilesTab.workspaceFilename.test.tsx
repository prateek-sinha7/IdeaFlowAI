import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import type { WorkflowRun } from "@/types/index";

// ─────────────────────────────────────────────────────────────────────────────
// QA-PS-007 (ISS-651 / ISS-659 / ISS-660) — the Files tab's Final Output row is
// always named after the generic on-disk workspace file ("presentation.html" /
// "prototype.html") even when the run's own content clearly names a topic.
//
// deriveDeliverableFiles() DOES parse the deck/prototype's own <title> into a
// topic-derived name — but withWorkspaceFile() (FilesTab.tsx:451) unconditionally
// overwrites that name with `file.path.split("/").pop()` once the run's real
// workspace file is resolved, and every ppt/prototype run's on-disk file is
// literally "presentation.html" / "prototype.html" (backend AGENT.md prompts
// hardcode the write target). So the row's displayed name collapses to the
// generic literal for every completed run, current run (ISS-651 ppt / ISS-659
// prototype) and parent "From v{n-1}" row alike (ISS-660).
//
// Scaffold mirrors FilesTab.baseVersion.test.tsx (same @/lib/api mock idiom).
// ─────────────────────────────────────────────────────────────────────────────

const mockGetToken = vi.fn(() => "test-token");
const mockGetWorkflow = vi.fn<(token: string, id: string) => Promise<WorkflowRun>>();
const mockResolveRunDeliverable = vi.fn();

vi.mock("@/lib/api", () => ({
  getToken: () => mockGetToken(),
  getWorkflow: (token: string, id: string) => mockGetWorkflow(token, id),
  resolveRunDeliverable: (token: string, runId: string, declared?: string | null) =>
    mockResolveRunDeliverable(token, runId, declared),
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
  mockResolveRunDeliverable.mockReset();
});

describe("QA-PS-007 — Files tab Final Output name survives workspace-file resolution", () => {
  // ISS-651 unfixed: `{ fails: true }` is vitest's xfail — this test must FAIL
  // today (asserting correct behaviour) and will start reporting a hard
  // failure ("expected fail... test did not fail") the moment the fix lands,
  // which is the signal to remove this flag.
  it("ISS-651: a completed ppt run's row keeps a topic-derived name, not the generic on-disk 'presentation.html'", { fails: true }, async () => {
    mockResolveRunDeliverable.mockResolvedValue({
      path: "presentation.html",
      size: 34_000,
      modified: 0,
      text: true,
    });

    render(
      <FilesTab
        workflowType="ppt"
        pptContent="<html><head><title>Lateral Thinking</title></head><body>deck</body></html>"
        runId="run-1"
        isRunning={false}
      />,
    );

    // Before resolution settles the content-derived name is already shown.
    expect(await screen.findByText("lateral-thinking.html")).toBeInTheDocument();

    await waitFor(() => expect(mockResolveRunDeliverable).toHaveBeenCalled());

    // The bug: once the workspace file resolves, the row's name collapses to
    // the raw on-disk basename regardless of the run's topic.
    expect(screen.queryByText("presentation.html")).not.toBeInTheDocument();
    expect(screen.getByText("lateral-thinking.html")).toBeInTheDocument();
  });

  // ISS-659 unfixed: `{ fails: true }` is vitest's xfail (see ISS-651 comment above).
  it("ISS-659: a completed prototype run's row keeps a topic-derived name, not the generic on-disk 'prototype.html'", { fails: true }, async () => {
    mockResolveRunDeliverable.mockResolvedValue({
      path: "prototype.html",
      size: 12_000,
      modified: 0,
      text: true,
    });

    render(
      <FilesTab
        workflowType="prototype"
        prototypeContent="<html><head><title>Expense Tracker</title></head><body>app</body></html>"
        runId="run-2"
        isRunning={false}
      />,
    );

    expect(await screen.findByText("expense-tracker.html")).toBeInTheDocument();
    await waitFor(() => expect(mockResolveRunDeliverable).toHaveBeenCalled());

    expect(screen.queryByText("prototype.html")).not.toBeInTheDocument();
    expect(screen.getByText("expense-tracker.html")).toBeInTheDocument();
  });

  // ISS-660 unfixed: `{ fails: true }` is vitest's xfail (see ISS-651 comment above).
  it("ISS-660: the 'From v{n-1}' base-version row for a ppt parent also keeps its topic-derived name", { fails: true }, async () => {
    mockGetWorkflow.mockResolvedValue({
      id: "parent-1",
      type: "ppt",
      output: "<html><head><title>Github Dashboard</title></head><body>deck</body></html>",
    } as WorkflowRun);
    mockResolveRunDeliverable.mockResolvedValue({
      path: "presentation.html",
      size: 30_000,
      modified: 0,
      text: true,
    });

    render(
      <FilesTab
        workflowType="ppt_revision"
        pptContent="<html><head><title>Github Dashboard v2</title></head></html>"
        parentRunId="parent-1"
        parentVersionNumber={1}
      />,
    );

    const toggle = screen.getByLabelText("From version 1");
    fireEvent.click(toggle);
    await waitFor(() => expect(mockGetWorkflow).toHaveBeenCalledWith("test-token", "parent-1"));
    await waitFor(() => expect(mockResolveRunDeliverable).toHaveBeenCalledWith("test-token", "parent-1", undefined));

    // The bug: the parent row also collapses to the generic on-disk name.
    await waitFor(() => expect(screen.queryByText("presentation.html")).not.toBeInTheDocument());
    expect(screen.getByText("github-dashboard.html")).toBeInTheDocument();
  });
});
