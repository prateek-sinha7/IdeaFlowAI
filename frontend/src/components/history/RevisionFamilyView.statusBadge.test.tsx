/**
 * A history row never calls a finished run "Running", and a run that lost an agent reads
 * "Failed".
 *
 * Run b0642e0f lost its Validation Agent ("The model rejected this request"), continued
 * to Fidelity Check and the Presenter, delivered a 72KB prototype.html, and was persisted
 * `degraded`. The history row read "Running", eighteen hours after it ended.
 *
 * `degraded` survives as a PERSISTED status — the engine still records which agents
 * failed and the deliverable is still openable — but history says "Failed" for it, in the
 * same red as an outright failure. One failed agent is a failed run; there is no partial
 * credit in the label.
 *
 * The cause was the badge's shape, not the missing branch: four `if`s and an
 * else-fallthrough to "Running", which quietly claimed every status nobody had thought
 * about. `statusDotClass` in the same file already had `case "degraded"` beside
 * `cancelled`, so the dot and the pill on one row disagreed.
 *
 * These assert on rendered DOM rather than on the map, so they would still catch a
 * regression that reshapes the component. The compiler covers the other half: the pill
 * table is keyed on `Exclude<WorkflowStatus, InFlightStatus>`, so a new terminal status
 * fails to build until it is given a pill or declared in-flight.
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

function runWith(status: WorkflowStatus): WorkflowRun {
  return {
    id: "b0642e0f-fe74-4f7e-9f16-8b164a6e989d",
    title: "Build an interactive Inland Marine underwriting workbench",
    type: "custom",
    status,
    createdAt: "2026-09-01T14:46:55.000Z",
    agentCount: 17,
  } as WorkflowRun;
}

function renderRow(status: WorkflowStatus) {
  const run = runWith(status);
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

describe("the row for a run that ended", () => {
  it('a degraded run reads "Failed", not "Running" and not a softer word', () => {
    renderRow("degraded");
    expect(screen.getByText("Failed")).toBeTruthy();
    expect(screen.queryByText("Running")).toBeNull();
    for (const softer of ["Issues", "Partial", "Completed with issues", "Degraded"]) {
      expect(screen.queryByText(softer)).toBeNull();
    }
  });

  it("degraded and failed are indistinguishable to a reader — same word, same red", () => {
    const { container: degraded } = renderRow("degraded");
    const { container: failed } = renderRow("failed");
    const pill = (c: HTMLElement) => {
      const el = c.querySelector('[data-testid="status-pill"]');
      if (!el) throw new Error("no status pill rendered");
      return el.className;
    };
    expect(pill(degraded)).toBe(pill(failed));
    expect(pill(degraded)).toContain("text-status-failed");
  });

  it.each<[WorkflowStatus, string]>([
    ["completed", "Done"],
    ["cancelled", "Cancelled"],
    ["failed", "Failed"],
    ["diverted", "Diverted"],
    ["degraded", "Failed"],
  ])("%s reads %s", (status, label) => {
    renderRow(status);
    expect(screen.getByText(label)).toBeTruthy();
    expect(screen.queryByText("Running")).toBeNull();
  });
});

describe("a run that has NOT ended still reads Running", () => {
  it.each<WorkflowStatus>(["running", "revising", "clarifying", "waiting_for_user"])(
    "%s",
    (status) => {
      renderRow(status);
      expect(screen.getByText("Running")).toBeTruthy();
    },
  );
});
