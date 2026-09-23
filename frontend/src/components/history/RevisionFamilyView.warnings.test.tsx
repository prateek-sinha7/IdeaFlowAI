/**
 * A14 — the history-list "Completed" pill gains a small amber indicator when the
 * run's `warnings` carry a review-loop cap message absorbed with a resolved
 * deliverable (server-side status stays "completed", never "degraded"). The
 * indicator's hover text names the count. Failed/degraded rows are untouched —
 * they already read "Failed" in red regardless of `warnings`.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { FamilyGroupCard, type FamilyGroup } from "./RevisionFamilyView";
import type { WorkflowRun, WorkflowStatus } from "@/types/index";

vi.mock("@/hooks/useWorkflowMetadata", () => ({
  useWorkflowShortNames: () => () => undefined,
}));
vi.mock("framer-motion", () => ({
  motion: new Proxy({}, { get: () => (p: Record<string, unknown>) => React.createElement("div", p) }),
  AnimatePresence: ({ children }: { children: React.ReactNode }) => children,
}));

function runWith(status: WorkflowStatus, warnings?: string[]): WorkflowRun {
  return {
    id: "a786cc27-fe74-4f7e-9f16-8b164a6e989d",
    title: "Build an interactive underwriting workbench",
    type: "custom",
    status,
    createdAt: "2026-09-01T14:46:55.000Z",
    agentCount: 17,
    warnings,
  } as WorkflowRun;
}

function renderRow(status: WorkflowStatus, warnings?: string[]) {
  const run = runWith(status, warnings);
  const group: FamilyGroup = { root: run, members: [run], latest: run } as FamilyGroup;
  return render(
    <FamilyGroupCard
      group={group}
      index={0}
      expanded={false}
      onToggle={() => {}}
      onSelectRun={() => {}}
      openMenuId={null}
      onToggleMenu={() => {}}
      onDeleteClick={() => {}}
    />,
  );
}

describe("history pill — A14 warnings indicator", () => {
  it('a completed run with no warnings reads plain "Done", no indicator', () => {
    renderRow("completed");
    expect(screen.getByText("Done")).toBeTruthy();
    expect(screen.queryByLabelText(/warning/)).toBeNull();
  });

  it("a completed run WITH warnings keeps the Done pill and adds an amber indicator naming the count", () => {
    renderRow("completed", ["step 'review-planner' exceeded loop_max_iterations=2"]);
    expect(screen.getByText("Done")).toBeTruthy();
    const indicator = screen.getByLabelText("1 warning");
    expect(indicator).toBeTruthy();
    expect(indicator).toHaveAttribute("title", "1 warning");
  });

  it("pluralizes the hover text for multiple warnings", () => {
    renderRow("completed", ["first cap message", "second cap message"]);
    expect(screen.getByLabelText("2 warnings")).toBeTruthy();
  });

  it("an empty warnings array reads exactly like no warnings", () => {
    renderRow("completed", []);
    expect(screen.queryByLabelText(/warning/)).toBeNull();
  });

  it("a failed run stays exactly Failed/red — warnings never attach to it", () => {
    renderRow("failed", ["some cap message"]);
    expect(screen.getByText("Failed")).toBeTruthy();
    expect(screen.queryByLabelText(/warning/)).toBeNull();
  });

  it("a degraded run stays exactly Failed/red — warnings never attach to it", () => {
    renderRow("degraded", ["some cap message"]);
    expect(screen.getByText("Failed")).toBeTruthy();
    expect(screen.queryByLabelText(/warning/)).toBeNull();
  });
});
