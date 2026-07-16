import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import type { WorkflowRun, RunFamily } from "@/types/index";

// ─────────────────────────────────────────────────────────────────
// Revision Families (B2 / POR §5 D3+D4): behavior specs for the history
// family grouping (Surface 1) + the detail version timeline (Surface 2).
// Real rendered-DOM asserts (never source-lock) — the B1 revise spec proves
// WorkflowHistory renders fine in vitest. Scaffold cloned from
// WorkflowHistory.revise.test.tsx, with getRunFamily added to the api mock.
// ─────────────────────────────────────────────────────────────────

const mockGetToken = vi.fn(() => "test-token");
const mockGetWorkflows = vi.fn<(token: string, opts?: { limit?: number }) => Promise<{ runs: WorkflowRun[]; total: number }>>();
const mockGetWorkflow = vi.fn<(token: string, id: string) => Promise<WorkflowRun>>();
const mockDeleteWorkflow = vi.fn<(token: string, id: string) => Promise<void>>();
const mockGetRunFamily = vi.fn<(token: string, id: string) => Promise<RunFamily>>();

vi.mock("@/lib/api", () => ({
  getToken: () => mockGetToken(),
  getWorkflows: (token: string, opts?: { limit?: number }) => mockGetWorkflows(token, opts),
  getWorkflow: (token: string, id: string) => mockGetWorkflow(token, id),
  deleteWorkflow: (token: string, id: string) => mockDeleteWorkflow(token, id),
  getRunFamily: (token: string, id: string) => mockGetRunFamily(token, id),
  // C2: WorkflowHistory now statically imports+calls getRunArtifacts on reopen;
  // return an empty artifact shape so ClarificationsCard renders null (no rounds)
  // and StartingPointCard renders from selectedRun.input unchanged (avoids the
  // B2 undefined-mock-export crash).
  getRunArtifacts: () => Promise.resolve({ workflow_id: "x", artifacts: [] }),
}));

vi.mock("@/components/preview/PPTPreview", () => ({
  PPTPreview: ({ content }: { content: string }) => <div data-testid="ppt-preview">{content.slice(0, 20)}</div>,
}));
vi.mock("@/components/preview/UserStoryPreview", () => ({
  UserStoryPreview: ({ content }: { content: string }) => <div data-testid="userstory-preview">{content.slice(0, 20)}</div>,
}));
vi.mock("@/components/preview/PrototypePreview", () => ({
  PrototypePreview: ({ content }: { content: string }) => <div data-testid="prototype-preview">{content.slice(0, 20)}</div>,
}));
vi.mock("@/components/preview/MarkdownPreview", () => ({
  MarkdownPreview: ({ content }: { content: string }) => <div data-testid="markdown-preview">{content.slice(0, 20)}</div>,
}));
vi.mock("@/components/results/FilesTab", () => ({
  FilesTab: () => <div data-testid="files-tab" />,
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

import { WorkflowHistory } from "./WorkflowHistory";

function makeRun(overrides: Partial<WorkflowRun> = {}): WorkflowRun {
  return {
    id: "hist-7",
    title: "Interactive prototype",
    type: "prototype",
    status: "completed",
    input: "build a landing page",
    output: "<!doctype html><html><body>hello</body></html>",
    createdAt: new Date("2026-05-12T10:00:00Z").toISOString(),
    completedAt: new Date("2026-05-12T10:05:00Z").toISOString(),
    duration: 300,
    agentCount: 4,
    parentRunId: null,
    rootRunId: "hist-7",
    ...overrides,
  };
}

// Distinct chronological timestamps so ordering is deterministic.
const t0 = new Date("2026-05-12T10:00:00Z").toISOString();
const t1 = new Date("2026-05-12T11:00:00Z").toISOString();
const t2 = new Date("2026-05-12T12:00:00Z").toISOString();
const t3 = new Date("2026-05-12T13:00:00Z").toISOString();

// A 3-member family (root + 2 revisions sharing rootRunId "root").
function familyRuns(): WorkflowRun[] {
  return [
    makeRun({ id: "root", title: "Root run", type: "prototype", parentRunId: null, rootRunId: "root", createdAt: t0, output: "<html>root</html>" }),
    makeRun({ id: "r1", title: "Rev one", type: "prototype_revision", parentRunId: "root", rootRunId: "root", createdAt: t1, output: "<html>r1</html>" }),
    makeRun({
      id: "r2", title: "Rev two", type: "prototype_revision", parentRunId: "r1", rootRunId: "root", createdAt: t2,
      input: "=== REVISION REQUEST ===\nmake the header blue",
      output: "<html>r2</html>",
    }),
  ];
}

function familyPayload(): RunFamily {
  return {
    root_id: "root",
    members: [
      { id: "root", type: "prototype", title: "Root run", status: "completed", revision_index: 0, parent_run_id: null, created_at: t0, completed_at: t0 },
      { id: "r1", type: "prototype_revision", title: "Rev one", status: "completed", revision_index: 1, parent_run_id: "root", created_at: t1, completed_at: t1 },
      { id: "r2", type: "prototype_revision", title: "Rev two", status: "completed", revision_index: 2, parent_run_id: "r1", created_at: t2, completed_at: t2 },
    ],
  };
}

beforeEach(() => {
  mockGetToken.mockReset().mockReturnValue("test-token");
  mockGetWorkflows.mockReset();
  mockGetWorkflow.mockReset();
  mockDeleteWorkflow.mockReset();
  mockGetRunFamily.mockReset();
});

describe("Revision Families (B2) — history grouping (D3)", () => {
  it("groups a multi-run family into one card with a v{N} pill; standalone stays a plain row; expand shows chronological rows with revises microcopy", async () => {
    const runs = [
      ...familyRuns(),
      makeRun({ id: "solo", title: "Solo run", type: "ppt", parentRunId: null, rootRunId: "solo", createdAt: t3, output: "<html>solo</html>" }),
    ];
    mockGetWorkflows.mockResolvedValue({ runs: runs, total: runs.length });
    mockGetRunFamily.mockResolvedValue(familyPayload());

    render(<WorkflowHistory onBack={vi.fn()} />);

    // Standalone renders as a plain row (present).
    await screen.findByText("Solo run");
    // Exactly ONE v3 count pill for the family (aria-label "3 versions").
    expect(screen.getByLabelText("3 versions")).toBeInTheDocument();
    // The family root title renders on the collapsed card.
    expect(screen.getByText("Root run")).toBeInTheDocument();
    // Child version rows are hidden until expanded.
    expect(screen.queryByText("Rev one")).toBeNull();

    // Expand the family.
    fireEvent.click(screen.getByLabelText("Show versions"));

    // Three chronological version rows appear with the revises microcopy.
    await waitFor(() => expect(screen.getByText("Rev one")).toBeInTheDocument());
    expect(screen.getByText("Rev two")).toBeInTheDocument();
    expect(screen.getByText("↳ revises v1")).toBeInTheDocument(); // rev1 revises root = v1
    expect(screen.getByText("↳ revises v2")).toBeInTheDocument(); // rev2 revises rev1 = v2
  });

  it("child version row is a native button (aria-label) that opens the version on activation (§8 keyboard)", async () => {
    mockGetWorkflows.mockResolvedValue({ runs: familyRuns(), total: familyRuns().length });
    mockGetRunFamily.mockResolvedValue(familyPayload());
    const byId: Record<string, WorkflowRun> = Object.fromEntries(familyRuns().map((r) => [r.id, r]));
    mockGetWorkflow.mockImplementation((_t, id) => Promise.resolve(byId[id]));

    render(<WorkflowHistory onBack={vi.fn()} />);

    await screen.findByText("Root run");
    // Expand the family.
    fireEvent.click(screen.getByLabelText("Show versions"));

    // The child version row is a native BUTTON carrying the a11y label (v2 = "Rev one").
    const row = await screen.findByRole("button", { name: /Version 2, completed/ });
    // Activating it opens that version (onSelectRun → detail view): the family
    // fetches and the version timeline renders its radio chips.
    fireEvent.click(row);
    await waitFor(() => expect(screen.getAllByRole("radio")).toHaveLength(3));
  });

  it("renders a single-member (standalone) family as a plain row — no pill, no expander (zero regression)", async () => {
    const solo = makeRun({ id: "solo", title: "Just me", type: "ppt", parentRunId: null, rootRunId: "solo", createdAt: t0, output: "<html>solo</html>" });
    mockGetWorkflows.mockResolvedValue({ runs: [solo], total: 1 });

    render(<WorkflowHistory onBack={vi.fn()} />);

    await screen.findByText("Just me");
    // No expander.
    expect(screen.queryByLabelText("Show versions")).toBeNull();
    // No "v{N}" count pill.
    expect(screen.queryByLabelText(/\d+ versions/)).toBeNull();
  });

  it("KAN-105: a chained run (different base type) is shown as a separate workflow entry, not as a version of the source", async () => {
    // Simulate: user ran a prototype (id="proto"), then chained to user_stories
    // (id="chain"). Both share rootRunId="proto" because the backend's
    // parent_run_id walk treats them the same. They must render as TWO
    // independent entries in the history list, not as "v2" under the prototype.
    const protoRun = makeRun({
      id: "proto",
      title: "My Prototype",
      type: "prototype",
      parentRunId: null,
      rootRunId: "proto",
      createdAt: t0,
      output: "<html>proto</html>",
    });
    const chainedRun = makeRun({
      id: "chain",
      title: "Chained Stories",
      type: "user_stories",
      parentRunId: "proto",
      rootRunId: "proto",   // ← same rootRunId as proto (the bug scenario)
      createdAt: t1,
      output: "## User Stories",
    });
    mockGetWorkflows.mockResolvedValue({ runs: [protoRun, chainedRun], total: 2 });

    render(<WorkflowHistory onBack={vi.fn()} />);

    // Both titles must appear as separate rows.
    await screen.findByText("My Prototype");
    await screen.findByText("Chained Stories");

    // No "v2" count pill — the chained run must NOT be shown as a version of the prototype.
    expect(screen.queryByLabelText(/\d+ versions/)).toBeNull();
    // No expander on either row.
    expect(screen.queryByLabelText("Show versions")).toBeNull();
  });
});

describe("Revision Families (B2) — detail version timeline (D4)", () => {
  async function openLatestDetail() {
    mockGetWorkflows.mockResolvedValue({ runs: familyRuns(), total: familyRuns().length });
    mockGetRunFamily.mockResolvedValue(familyPayload());
    render(<WorkflowHistory onBack={vi.fn()} />);
    // Click the family root card body → opens the latest member (v3 = r2).
    const card = await screen.findByText("Root run");
    fireEvent.click(card);
    // Wait for the version chips to render (family fetched on open).
    await waitFor(() => expect(screen.getAllByRole("radio")).toHaveLength(3));
  }

  it("renders 3 chronological chips, the active chip matches the loaded version, and shows the extracted instruction preview", async () => {
    await openLatestDetail();

    const chips = screen.getAllByRole("radio");
    expect(chips).toHaveLength(3);
    // Opened the latest = v3 → the 3rd chip is active.
    expect(chips[2].getAttribute("aria-checked")).toBe("true");
    expect(chips[0].getAttribute("aria-checked")).toBe("false");
    // The context line shows the extracted revision instruction.
    expect(screen.getByText(/make the header blue/)).toBeInTheDocument();
    // Unified lowercase microcopy: the timeline context line reads "↳ revises v{n}"
    // (previously capitalized "Revises"), matching the list child-row form.
    expect(screen.getByText(/↳ revises v/)).toBeInTheDocument();
  });

  it("clicking a sibling chip loads that version via getWorkflow and the active chip follows", async () => {
    // (I1 fix) key getWorkflow by id so clicking v1 resolves an object whose
    // id === the v1 member id — otherwise the active chip never re-matches.
    const byId: Record<string, WorkflowRun> = Object.fromEntries(familyRuns().map((r) => [r.id, r]));
    mockGetWorkflow.mockImplementation((_t, id) => Promise.resolve(byId[id]));

    await openLatestDetail();

    // Click the v1 sibling chip (first radio).
    fireEvent.click(screen.getAllByRole("radio")[0]);

    // getWorkflow fetched the v1 member by id.
    await waitFor(() => expect(mockGetWorkflow).toHaveBeenCalledWith("test-token", "root"));
    // The active chip follows the loaded version → v1 checked, v3 unchecked.
    await waitFor(() => {
      const chips = screen.getAllByRole("radio");
      expect(chips[0].getAttribute("aria-checked")).toBe("true");
      expect(chips[2].getAttribute("aria-checked")).toBe("false");
    });
  });

  it("exposes the chip row as a radiogroup with radio chips carrying aria-checked (a11y)", async () => {
    await openLatestDetail();

    expect(screen.getByRole("radiogroup")).toBeInTheDocument();
    const chips = screen.getAllByRole("radio");
    expect(chips.length).toBeGreaterThanOrEqual(2);
    for (const chip of chips) {
      expect(chip.hasAttribute("aria-checked")).toBe(true);
    }
  });
});
