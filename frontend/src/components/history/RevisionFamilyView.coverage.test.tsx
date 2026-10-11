/**
 * RevisionFamilyView — branch/interaction coverage for the exported helpers
 * (grouping, divert links, date buckets, sorting, preview), FamilyGroupCard
 * (single / multi-member rows, title cleaning, menus, divert breadcrumbs),
 * ChainLineageBadge and VersionTimeline.
 *
 * The real Redux store supplies the workflow catalog (no hook mocking); only
 * the motion shim is replaced so role/label queries see plain DOM.
 */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React, { useState } from "react";
import type { FamilyMember, RunFamily, WorkflowRun, WorkflowStatus } from "@/types/index";
import globalReducer from "@/store/slices/globalSlice";
import { renderWithProviders } from "@/test/renderWithProviders";

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

import {
  ChainLineageBadge,
  FamilyGroupCard,
  VersionTimeline,
  baseWorkflowType,
  bucketAndSortFamilies,
  buildDivertLinks,
  dateBucketOf,
  extractRevisionInstructionPreview,
  filterBucketFor,
  groupRunsByFamily,
  statusDotClass,
  type DivertLink,
  type FamilyGroup,
} from "./RevisionFamilyView";

// ─── Builders ────────────────────────────────────────────────────────────────
function makeRun(overrides: Partial<WorkflowRun> & { id: string }): WorkflowRun {
  return {
    title: `Run ${overrides.id}`,
    type: "prototype",
    status: "completed",
    input: "",
    createdAt: "2026-05-12T10:00:00.000Z",
    agentCount: 3,
    parentRunId: null,
    rootRunId: overrides.id,
    ...overrides,
  } as WorkflowRun;
}

function groupOf(members: WorkflowRun[], rootRunId = members[0].id): FamilyGroup {
  return { rootRunId, root: members[0], members, latest: members[members.length - 1] };
}

function member(overrides: Partial<FamilyMember> & { id: string }): FamilyMember {
  return {
    type: "prototype",
    title: overrides.id,
    status: "completed",
    revision_index: 1,
    parent_run_id: null,
    created_at: "2026-07-01T10:00:00",
    completed_at: null,
    ...overrides,
  };
}

function catalogState(workflows: Array<{ id: string; name: string; short_name?: string }>) {
  const base = globalReducer(undefined, { type: "@@init" });
  return {
    global: {
      ...base,
      workflows: workflows.map((w) => ({
        display_name: w.name, description: "", step_count: 1, steps: [], ...w,
      })) as unknown as typeof base.workflows,
    },
  };
}

interface CardHandlers {
  onToggle: () => void;
  onSelectRun: (run: WorkflowRun) => void;
  onToggleMenu: (runId: string, e?: React.MouseEvent) => void;
  onDeleteClick: (runId: string, e?: React.MouseEvent) => void;
}

function renderCard(
  group: FamilyGroup,
  opts: {
    expanded?: boolean;
    openMenuId?: string | null;
    divertLinks?: Map<string, DivertLink>;
    preloadedState?: ReturnType<typeof catalogState>;
  } = {},
) {
  const handlers: CardHandlers = {
    onToggle: vi.fn(),
    onSelectRun: vi.fn(),
    onToggleMenu: vi.fn(),
    onDeleteClick: vi.fn(),
  };
  renderWithProviders(
    <FamilyGroupCard
      group={group}
      index={0}
      expanded={opts.expanded ?? false}
      openMenuId={opts.openMenuId ?? null}
      divertLinks={opts.divertLinks}
      {...handlers}
    />,
    { preloadedState: opts.preloadedState },
  );
  return handlers;
}

// ─── Pure helpers ────────────────────────────────────────────────────────────
describe("baseWorkflowType / filterBucketFor", () => {
  it("strips the _revision suffix", () => {
    expect(baseWorkflowType("ppt_revision")).toBe("ppt");
    expect(baseWorkflowType("ppt")).toBe("ppt");
  });

  it.each([
    ["user_stories", "user_stories"],
    ["user_stories_revision", "user_stories"],
    ["ppt", "ppt"],
    ["prototype_revision", "prototype"],
    ["app_builder", "app_builder"],
    ["custom", "custom"],
    ["sample_conditional_branch_new", "custom"],
  ])("maps %s to the %s filter bucket", (type, bucket) => {
    expect(filterBucketFor(type)).toBe(bucket);
  });
});

describe("statusDotClass", () => {
  it.each<[WorkflowStatus, string]>([
    ["completed", "bg-status-done"],
    ["cancelled", "bg-status-amber"],
    ["failed", "bg-status-failed"],
    ["degraded", "bg-status-failed"],
    ["diverted", "bg-brand"],
    ["running", "bg-status-running"],
    ["revising", "bg-status-running"],
    ["planning", "bg-status-running"],
  ])("returns the semantic dot colour for %s", (status, expected) => {
    expect(statusDotClass(status).split(" ")).toContain(expected);
  });
});

describe("groupRunsByFamily", () => {
  it("groups a revision chain under its root, ordered v1..vN, newest family first", () => {
    const root = makeRun({ id: "r1", createdAt: "2026-05-01T10:00:00.000Z" });
    const rev = makeRun({ id: "r2", parentRunId: "r1", rootRunId: "r1", createdAt: "2026-05-02T10:00:00.000Z" });
    const solo = makeRun({ id: "s1", createdAt: "2026-05-10T10:00:00.000Z" });

    const groups = groupRunsByFamily([rev, solo, root]);

    expect(groups.map((g) => g.rootRunId)).toEqual(["s1", "r1"]);
    expect(groups[1].members.map((m) => m.id)).toEqual(["r1", "r2"]);
    expect(groups[1].root.id).toBe("r1");
    expect(groups[1].latest.id).toBe("r2");
  });

  it("breaks created_at ties by id so version numbers are deterministic", () => {
    const a = makeRun({ id: "a", rootRunId: "root", parentRunId: "root" });
    const b = makeRun({ id: "b", rootRunId: "root", parentRunId: "root" });

    const [group] = groupRunsByFamily([b, a]);

    expect(group.members.map((m) => m.id)).toEqual(["a", "b"]);
  });

  it("falls back to the earliest present member as root when the real root is outside the page", () => {
    const child = makeRun({ id: "c1", parentRunId: "missing", rootRunId: "missing" });

    const [group] = groupRunsByFamily([child]);

    expect(group.rootRunId).toBe("missing");
    expect(group.root.id).toBe("c1");
  });

  it("does not stitch a divert target into its source's family", () => {
    const source = makeRun({ id: "src", status: "diverted", createdAt: "2026-05-01T10:00:00.000Z" });
    const target = makeRun({ id: "tgt", parentRunId: "src", rootRunId: "src", createdAt: "2026-05-01T11:00:00.000Z" });

    const groups = groupRunsByFamily([source, target]);

    expect(groups).toHaveLength(2);
    expect(groups.map((g) => g.members.map((m) => m.id))).toEqual([["tgt"], ["src"]]);
  });

  it("walks past intermediate revisions to the real root", () => {
    const v1 = makeRun({ id: "v1", createdAt: "2026-05-01T10:00:00.000Z" });
    const v2 = makeRun({ id: "v2", parentRunId: "v1", rootRunId: "v1", createdAt: "2026-05-02T10:00:00.000Z" });
    const v3 = makeRun({ id: "v3", parentRunId: "v2", rootRunId: "v1", createdAt: "2026-05-03T10:00:00.000Z" });

    const groups = groupRunsByFamily([v3, v2, v1]);

    expect(groups).toHaveLength(1);
    expect(groups[0].members.map((m) => m.id)).toEqual(["v1", "v2", "v3"]);
  });
});

describe("buildDivertLinks", () => {
  it("links a diverted source to its target in both directions, carrying the step id", () => {
    const source = makeRun({ id: "src", status: "diverted", divertedAtStepId: "gate-1" });
    const target = makeRun({ id: "tgt", parentRunId: "src" });

    const links = buildDivertLinks([source, target]);

    expect(links.get("src")).toEqual({ direction: "source", other: target });
    expect(links.get("tgt")).toEqual({ direction: "target", other: source, stepId: "gate-1" });
  });

  it("leaves stepId undefined for legacy rows without a persisted step", () => {
    const source = makeRun({ id: "src", status: "diverted", divertedAtStepId: null });
    const target = makeRun({ id: "tgt", parentRunId: "src" });

    expect(buildDivertLinks([source, target]).get("tgt")?.stepId).toBeUndefined();
  });

  it("skips a diverted run whose target is outside the loaded page", () => {
    const links = buildDivertLinks([makeRun({ id: "src", status: "diverted" })]);

    expect(links.size).toBe(0);
  });

  it("ignores runs that are not diverted", () => {
    const links = buildDivertLinks([makeRun({ id: "a" }), makeRun({ id: "b", parentRunId: "a" })]);

    expect(links.size).toBe(0);
  });
});

describe("dateBucketOf", () => {
  const now = new Date(2026, 4, 20, 15, 0, 0);

  it("puts earlier-today in Today", () => {
    expect(dateBucketOf(new Date(2026, 4, 20, 1, 0, 0).toISOString(), now)).toBe("Today");
  });

  it("puts yesterday and the last 7 days in Earlier", () => {
    expect(dateBucketOf(new Date(2026, 4, 19, 23, 0, 0).toISOString(), now)).toBe("Earlier");
    expect(dateBucketOf(new Date(2026, 4, 13, 0, 0, 0).toISOString(), now)).toBe("Earlier");
  });

  it("puts anything before the 7-day window in Older", () => {
    expect(dateBucketOf(new Date(2026, 4, 12, 23, 59, 0).toISOString(), now)).toBe("Older");
  });
});

describe("bucketAndSortFamilies", () => {
  const now = new Date(2026, 4, 20, 15, 0, 0);
  const at = (d: number, h = 9) => new Date(2026, 4, d, h, 0, 0).toISOString();
  const tokens = (n: number) => ({
    total_input_tokens: 0, total_output_tokens: 0, total_tokens: n, estimated_cost_usd: 0,
  });

  const today1 = groupOf([makeRun({ id: "t1", createdAt: at(20, 8), tokenUsage: tokens(100), duration: 30 })]);
  const today2 = groupOf([makeRun({ id: "t2", createdAt: at(20, 12), tokenUsage: tokens(900), duration: 10 })]);
  const earlier = groupOf([makeRun({ id: "e1", createdAt: at(17) })]);
  const older = groupOf([makeRun({ id: "o1", createdAt: at(1) })]);

  it("returns only non-empty buckets in Today → Earlier → Older order", () => {
    const sections = bucketAndSortFamilies([older, today1, earlier], "recent", now);

    expect(sections.map((s) => s.bucket)).toEqual(["Today", "Earlier", "Older"]);
    expect(bucketAndSortFamilies([earlier], "recent", now).map((s) => s.bucket)).toEqual(["Earlier"]);
    expect(bucketAndSortFamilies([], "recent", now)).toEqual([]);
  });

  it("sorts recent by newest latest member", () => {
    const [today] = bucketAndSortFamilies([today1, today2], "recent", now);

    expect(today.groups.map((g) => g.rootRunId)).toEqual(["t2", "t1"]);
  });

  it("sorts by tokens descending", () => {
    const [today] = bucketAndSortFamilies([today1, today2], "tokens", now);

    expect(today.groups.map((g) => g.rootRunId)).toEqual(["t2", "t1"]);
  });

  it("sorts by duration descending", () => {
    const [today] = bucketAndSortFamilies([today2, today1], "duration", now);

    expect(today.groups.map((g) => g.rootRunId)).toEqual(["t1", "t2"]);
  });

  it("falls back to recency when the chosen metric ties (including missing metrics)", () => {
    const a = groupOf([makeRun({ id: "a", createdAt: at(20, 8) })]);
    const b = groupOf([makeRun({ id: "b", createdAt: at(20, 11) })]);

    expect(bucketAndSortFamilies([a, b], "tokens", now)[0].groups.map((g) => g.rootRunId)).toEqual(["b", "a"]);
    expect(bucketAndSortFamilies([a, b], "duration", now)[0].groups.map((g) => g.rootRunId)).toEqual(["b", "a"]);
  });

  it("breaks a full tie by root id, descending", () => {
    const a = groupOf([makeRun({ id: "a", createdAt: at(20, 8) })]);
    const b = groupOf([makeRun({ id: "b", createdAt: at(20, 8) })]);

    expect(bucketAndSortFamilies([a, b], "recent", now)[0].groups.map((g) => g.rootRunId)).toEqual(["b", "a"]);
  });
});

describe("extractRevisionInstructionPreview", () => {
  it("returns an empty string for empty input", () => {
    expect(extractRevisionInstructionPreview("")).toBe("");
  });

  it("prefers the revision instruction over the brief", () => {
    const input = "Original brief\n=== REVISION REQUEST ===\nMake the header blue\n=== END REQUEST ===";

    expect(extractRevisionInstructionPreview(input)).toBe("Make the header blue");
  });

  it("falls back to the first non-blank brief line", () => {
    expect(extractRevisionInstructionPreview("\n\n   \nBuild a dashboard\nwith charts")).toBe("Build a dashboard");
  });

  it("clamps lines longer than 60 characters with an ellipsis", () => {
    const preview = extractRevisionInstructionPreview("x".repeat(80));

    expect(preview).toBe(`${"x".repeat(60)}…`);
  });

  it("returns an empty string when the input has no meaningful line", () => {
    expect(extractRevisionInstructionPreview("   \n  \n")).toBe("");
  });
});

// ─── FamilyGroupCard — single member ────────────────────────────────────────
describe("FamilyGroupCard — single-member family", () => {
  it("opens the run on click and shows title, type label, agent count and duration", async () => {
    const user = userEvent.setup();
    const run = makeRun({ id: "r1", title: "Sales deck", type: "ppt", agentCount: 1, duration: 125 });
    const { onSelectRun } = renderCard(groupOf([run]));

    expect(screen.getByText("Presentation · 1 agent")).toBeInTheDocument();
    expect(screen.getByText("2m 5s")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open Sales deck, completed" }));

    expect(onSelectRun).toHaveBeenCalledWith(run);
  });

  it("omits the duration chip when the run has no duration", () => {
    renderCard(groupOf([makeRun({ id: "r1", duration: undefined })]));

    expect(screen.queryByText("·")).not.toBeInTheDocument();
  });

  it.each([["{Enter}"], [" "]])("opens the run when %j is pressed on the focused row", async (key) => {
    const user = userEvent.setup();
    const run = makeRun({ id: "r1", title: "Keyboard run" });
    const { onSelectRun } = renderCard(groupOf([run]));

    screen.getByRole("button", { name: /^Open Keyboard run/ }).focus();
    await user.keyboard(key);

    expect(onSelectRun).toHaveBeenCalledWith(run);
  });

  it("ignores a keydown bubbling from a nested control (only the row itself opens the run)", () => {
    const { onSelectRun } = renderCard(groupOf([makeRun({ id: "r1" })]));

    // fireEvent: user-event turns Enter on a native button into a click, which would
    // exercise the click path instead of the row's own keydown guard.
    fireEvent.keyDown(screen.getByRole("button", { name: "Run actions" }), { key: "Enter" });

    expect(onSelectRun).not.toHaveBeenCalled();
  });

  it("does not open the run on unrelated keys", async () => {
    const user = userEvent.setup();
    const { onSelectRun } = renderCard(groupOf([makeRun({ id: "r1", title: "Keys" })]));

    screen.getByRole("button", { name: /^Open Keys/ }).focus();
    await user.keyboard("a");

    expect(onSelectRun).not.toHaveBeenCalled();
  });

  it("resolves an off-catalog type through the live catalog's short name", () => {
    renderCard(groupOf([makeRun({ id: "r1", type: "ex_a2_branch" as WorkflowRun["type"], agentCount: 2 })]), {
      preloadedState: catalogState([{ id: "ex_a2_branch", name: "Branch Demo", short_name: "Branch Short" }]),
    });

    expect(screen.getByText("Branch Short · 2 agents")).toBeInTheDocument();
  });

  it("humanizes an unknown type that is absent from the catalog", () => {
    renderCard(groupOf([makeRun({ id: "r1", type: "sample_conditional_branch_new" as WorkflowRun["type"] })]));

    expect(screen.getByText("Sample Conditional Branch New · 3 agents")).toBeInTheDocument();
  });

  it("labels the literal custom type 'Custom' without a catalog lookup", () => {
    renderCard(groupOf([makeRun({ id: "r1", type: "custom" })]));

    expect(screen.getByText("Custom · 3 agents")).toBeInTheDocument();
  });

  describe("title cleaning", () => {
    it("strips a leading 'Title: ' prefix", () => {
      renderCard(groupOf([makeRun({ id: "r1", title: "Title: Clean me" })]));

      expect(screen.getByText("Clean me")).toBeInTheDocument();
    });

    it("falls back to the type label when the title is empty and there is no input", () => {
      renderCard(groupOf([makeRun({ id: "r1", title: "", type: "ppt" })]));

      expect(screen.getByText("Presentation", { selector: "p" })).toBeInTheDocument();
    });

    it("derives the title from the run input when the title is empty", () => {
      renderCard(groupOf([makeRun({ id: "r1", title: "", input: "Title: Brief headline\nmore detail" })]));

      expect(screen.getByText("Brief headline")).toBeInTheDocument();
    });

    it("derives the title from the revision instruction when the title is a polluted marker block", () => {
      const input = "base\n=== REVISION REQUEST ===\nAdd a footer\n=== END REQUEST ===";
      renderCard(groupOf([makeRun({ id: "r1", title: "=== EXISTING HTML ===", input })]));

      expect(screen.getByText("Add a footer")).toBeInTheDocument();
    });

    it("falls back to the type label when a polluted title has no usable input", () => {
      renderCard(groupOf([makeRun({ id: "r1", title: "=== EXISTING HTML ===", input: "", type: "prototype" })]));

      expect(screen.getByText("Prototype", { selector: "p" })).toBeInTheDocument();
    });

    it("recovers a revision instruction embedded after normal text in the title", () => {
      renderCard(groupOf([makeRun({ id: "r1", title: "Intro\n=== REVISION REQUEST ===\nShrink logo" })]));

      expect(screen.getByText("Shrink logo")).toBeInTheDocument();
    });

    it("falls back to the type label when the input yields an empty headline", () => {
      renderCard(groupOf([makeRun({ id: "r1", title: "", input: "   \n  ", type: "ppt" })]));

      expect(screen.getByText("Presentation", { selector: "p" })).toBeInTheDocument();
    });
  });

  describe("row stats", () => {
    it("shows the compact token count when the run recorded usage", () => {
      const tokenUsage = { total_input_tokens: 0, total_output_tokens: 0, total_tokens: 12_345, estimated_cost_usd: 0 };
      renderCard(groupOf([makeRun({ id: "r1", tokenUsage })]));

      expect(screen.getByText("12.3K")).toBeInTheDocument();
    });

    it("shows only the relative time when there is no usage datum", () => {
      renderCard(groupOf([makeRun({ id: "r1", tokenUsage: undefined, createdAt: new Date(Date.now() - 5 * 60_000).toISOString() })]));

      expect(screen.getByText("5m ago")).toBeInTheDocument();
      expect(screen.queryByText(/K$|M$/)).not.toBeInTheDocument();
    });

    it.each([
      ["a few seconds ago", () => new Date(Date.now() - 5_000).toISOString(), "Just now"],
      ["3 hours ago", () => new Date(Date.now() - 3 * 3_600_000).toISOString(), "3h ago"],
      ["2 days ago", () => new Date(Date.now() - 2 * 86_400_000 - 60_000).toISOString(), "2d ago"],
    ])("renders %s as a relative label", (_label, iso, expected) => {
      renderCard(groupOf([makeRun({ id: "r1", createdAt: iso() })]));

      expect(screen.getByText(expected)).toBeInTheDocument();
    });

    it("renders a short calendar date for runs older than a week", () => {
      renderCard(groupOf([makeRun({ id: "r1", createdAt: "2020-01-15T12:00:00.000Z" })]));

      expect(screen.getByText("Jan 15")).toBeInTheDocument();
    });
  });

  describe("status pills", () => {
    it.each<[WorkflowStatus, string]>([
      ["completed", "Done"],
      ["cancelled", "Cancelled"],
      ["diverted", "Diverted"],
      ["running", "Running"],
      ["revising", "Running"],
    ])("shows %s as '%s'", (status, label) => {
      renderCard(groupOf([makeRun({ id: "r1", status })]));

      expect(screen.getByTestId("status-pill")).toHaveTextContent(label);
    });
  });

  describe("divert breadcrumb", () => {
    const source = makeRun({ id: "src", status: "diverted", type: "prototype", title: "Source run" });
    const target = makeRun({ id: "tgt", parentRunId: "src", type: "ppt", title: "Target run" });
    const links = buildDivertLinks([{ ...source, divertedAtStepId: "gate-7" }, target]);

    it("shows 'Diverted to X →' on the source and opens the target without opening the source", async () => {
      const user = userEvent.setup();
      const { onSelectRun } = renderCard(groupOf([source]), { divertLinks: links });

      await user.click(screen.getByRole("button", { name: "Diverted to Presentation, open triggered run" }));

      expect(screen.getByText("Diverted to Presentation →")).toBeInTheDocument();
      expect(onSelectRun).toHaveBeenCalledTimes(1);
      expect(onSelectRun).toHaveBeenCalledWith(target);
    });

    it("shows '← Continued from X, step S' on the target and opens the originating run", async () => {
      const user = userEvent.setup();
      const { onSelectRun } = renderCard(groupOf([target]), { divertLinks: links });

      await user.click(screen.getByRole("button", { name: "Continued from Prototype, open originating run" }));

      expect(screen.getByText("← Continued from Prototype, step gate-7")).toBeInTheDocument();
      expect(onSelectRun).toHaveBeenCalledWith(expect.objectContaining({ id: "src" }));
    });

    it("omits the step clause when the divert step is unknown", () => {
      const legacy = buildDivertLinks([{ ...source, divertedAtStepId: null }, target]);
      renderCard(groupOf([target]), { divertLinks: legacy });

      expect(screen.getByText("← Continued from Prototype")).toBeInTheDocument();
    });

    it("renders no breadcrumb when the run has no link", () => {
      renderCard(groupOf([makeRun({ id: "plain" })]), { divertLinks: links });

      expect(screen.queryByText(/Diverted to|Continued from/)).not.toBeInTheDocument();
    });
  });

  describe("row menu", () => {
    it("opens the delete menu for the open row and deletes without opening the run", async () => {
      const user = userEvent.setup();
      const { onDeleteClick, onSelectRun } = renderCard(groupOf([makeRun({ id: "r1" })]), { openMenuId: "r1" });

      expect(screen.getByRole("button", { name: "Run actions" })).toHaveAttribute("aria-expanded", "true");
      await user.click(screen.getByRole("menuitem", { name: "Delete" }));

      expect(onDeleteClick).toHaveBeenCalledWith("r1", expect.anything());
      expect(onSelectRun).not.toHaveBeenCalled();
    });

    it("keeps the menu closed when another row owns it", () => {
      renderCard(groupOf([makeRun({ id: "r1" })]), { openMenuId: "other" });

      expect(screen.queryByRole("menu")).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Run actions" })).toHaveAttribute("aria-expanded", "false");
    });

    it("closes the open menu on Escape without bubbling to the row", async () => {
      const user = userEvent.setup();
      const { onToggleMenu } = renderCard(groupOf([makeRun({ id: "r1" })]), { openMenuId: "r1" });

      await user.click(screen.getByRole("menuitem", { name: "Delete" }));
      screen.getByRole("button", { name: "Run actions" }).focus();
      await user.keyboard("{Escape}");

      expect(onToggleMenu).toHaveBeenCalledWith("r1");
    });

    it("ignores Escape when the menu is already closed", async () => {
      const user = userEvent.setup();
      const { onToggleMenu } = renderCard(groupOf([makeRun({ id: "r1" })]), { openMenuId: null });

      screen.getByRole("button", { name: "Run actions" }).focus();
      await user.keyboard("{Escape}");

      expect(onToggleMenu).not.toHaveBeenCalled();
    });
  });
});

// ─── FamilyGroupCard — multi-member ─────────────────────────────────────────
describe("FamilyGroupCard — multi-member family", () => {
  const v1 = makeRun({ id: "v1", title: "First cut", createdAt: "2026-05-01T10:00:00.000Z", type: "prototype" });
  const v2 = makeRun({
    id: "v2", title: "Second cut", parentRunId: "v1", rootRunId: "v1", status: "failed",
    createdAt: "2026-05-02T10:00:00.000Z", type: "prototype_revision", duration: 61,
  });
  const v3 = makeRun({
    id: "v3", title: "Third cut", parentRunId: "v2", rootRunId: "v1", status: "running",
    createdAt: "2026-05-03T10:00:00.000Z", type: "prototype_revision",
  });
  const family = groupOf([v1, v2, v3]);

  it("summarises the family with a version pill, root title and the latest member's status", () => {
    renderCard(family);

    expect(screen.getByText("First cut")).toBeInTheDocument();
    expect(screen.getByLabelText("3 versions")).toHaveTextContent("v3");
    expect(screen.getByRole("button", { name: "Open First cut (latest version), running" })).toBeInTheDocument();
    expect(screen.getByTestId("status-pill")).toHaveTextContent("Running");
  });

  it("shows the latest member's duration when it has one", () => {
    renderCard(groupOf([v1, v2]));

    expect(screen.getByText("1m 1s")).toBeInTheDocument();
  });

  it("opens the latest member when the row is clicked", async () => {
    const user = userEvent.setup();
    const { onSelectRun } = renderCard(family);

    await user.click(screen.getByRole("button", { name: /^Open First cut \(latest version\)/ }));

    expect(onSelectRun).toHaveBeenCalledWith(v3);
  });

  it.each([["{Enter}"], [" "]])("opens the latest member when %j is pressed on the row", async (key) => {
    const user = userEvent.setup();
    const { onSelectRun } = renderCard(family);

    screen.getByRole("button", { name: /^Open First cut \(latest version\)/ }).focus();
    await user.keyboard(key);

    expect(onSelectRun).toHaveBeenCalledWith(v3);
  });

  it("ignores keys pressed on nested controls", async () => {
    const user = userEvent.setup();
    const { onSelectRun } = renderCard(family);

    screen.getByRole("button", { name: "Show versions" }).focus();
    await user.keyboard("{Enter}");

    expect(onSelectRun).not.toHaveBeenCalled();
  });

  it("toggles expansion from the version pill without opening a run", async () => {
    const user = userEvent.setup();
    const { onToggle, onSelectRun } = renderCard(family);

    await user.click(screen.getByRole("button", { name: "Show versions" }));

    expect(onToggle).toHaveBeenCalledTimes(1);
    expect(onSelectRun).not.toHaveBeenCalled();
  });

  it("labels the toggle 'Collapse versions' when expanded", () => {
    renderCard(family, { expanded: true });

    expect(screen.getByRole("button", { name: "Collapse versions" })).toHaveAttribute("aria-expanded", "true");
  });

  it("lists every version when expanded, with revision lineage, and opens the chosen one", async () => {
    const user = userEvent.setup();
    const { onSelectRun } = renderCard(family, { expanded: true });

    expect(screen.getByRole("button", { name: "Version 1, completed" })).toBeInTheDocument();
    expect(screen.getByText("↳ revises v1")).toBeInTheDocument();
    expect(screen.getByText("↳ revises v2")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Version 2, failed" }));

    expect(onSelectRun).toHaveBeenCalledWith(v2);
  });

  it("falls back to the previous sibling when a member's parent is not in the family", () => {
    const orphanChild = makeRun({
      id: "v2", title: "Orphan revision", parentRunId: "not-here", rootRunId: "v1",
      createdAt: "2026-05-02T10:00:00.000Z",
    });
    renderCard(groupOf([v1, orphanChild]), { expanded: true });

    expect(screen.getByText("↳ revises v1")).toBeInTheDocument();
  });

  it("gives each version row its own actions menu wired to that run id", async () => {
    const user = userEvent.setup();
    const { onDeleteClick } = renderCard(family, { expanded: true, openMenuId: "v2" });

    const menu = screen.getByRole("menu");
    await user.click(within(menu).getByRole("menuitem", { name: "Delete" }));

    expect(onDeleteClick).toHaveBeenCalledWith("v2", expect.anything());
  });

  it("targets the root id from the family-level actions menu", async () => {
    const user = userEvent.setup();
    const { onToggleMenu } = renderCard(family);

    await user.click(screen.getAllByRole("button", { name: "Run actions" })[0]);

    expect(onToggleMenu).toHaveBeenCalledWith("v1", expect.anything());
  });

  it("shows a divert breadcrumb for the latest member when it is a divert source", async () => {
    const user = userEvent.setup();
    const diverted = makeRun({
      id: "v3", title: "Third cut", parentRunId: "v2", rootRunId: "v1", status: "diverted",
      createdAt: "2026-05-03T10:00:00.000Z",
    });
    const target = makeRun({ id: "t", parentRunId: "v3", type: "ppt" });
    const links = buildDivertLinks([v1, v2, diverted, target]);
    const { onSelectRun } = renderCard(groupOf([v1, v2, diverted]), { divertLinks: links });

    await user.click(screen.getByRole("button", { name: "Diverted to Presentation, open triggered run" }));

    expect(onSelectRun).toHaveBeenCalledWith(target);
  });

  it("derives the root title from the root's input when its title is empty", () => {
    const blankRoot = makeRun({ id: "v1", title: "", input: "Original brief line" });
    renderCard(groupOf([blankRoot, v2]));

    expect(screen.getByText("Original brief line")).toBeInTheDocument();
  });
});

// ─── ChainLineageBadge ───────────────────────────────────────────────────────
describe("ChainLineageBadge", () => {
  it("renders nothing unless the chain payload was installed", () => {
    const { container } = renderWithProviders(
      <ChainLineageBadge chain_context_installed={false} chain_source_workflow_id="ppt" />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when there is neither a source workflow id nor a short id", () => {
    const { container } = renderWithProviders(<ChainLineageBadge chain_context_installed />);

    expect(container).toBeEmptyDOMElement();
  });

  it("uses the catalog short name and the visible tag", () => {
    renderWithProviders(
      <ChainLineageBadge
        chain_context_installed
        chain_source_workflow_id="user_stories"
        chain_source_visible_tag="v2"
        chain_source_short_id="abc"
      />,
      { preloadedState: catalogState([{ id: "user_stories", name: "User Stories", short_name: "Stories" }]) },
    );

    expect(screen.getByLabelText("Chained from Stories v2")).toBeInTheDocument();
  });

  it("humanizes the workflow id when the catalog does not know it", () => {
    renderWithProviders(
      <ChainLineageBadge chain_context_installed chain_source_workflow_id="spanish_greeter" chain_source_visible_tag="v1" />,
    );

    expect(screen.getByLabelText("Chained from Spanish Greeter v1")).toBeInTheDocument();
  });

  it("shows short id and published status for an untagged, non-terminal source", () => {
    renderWithProviders(
      <ChainLineageBadge
        chain_context_installed
        chain_source_workflow_id="ppt"
        chain_source_short_id="9f8e7d"
        chain_source_published_status="draft"
        chain_source_visible_tag={null}
      />,
    );

    expect(screen.getByLabelText("Chained from Ppt 9f8e7d (draft)")).toBeInTheDocument();
  });

  it("shows just the short id when no published status is known", () => {
    renderWithProviders(
      <ChainLineageBadge chain_context_installed chain_source_workflow_id="ppt" chain_source_short_id="9f8e7d" />,
    );

    expect(screen.getByLabelText("Chained from Ppt 9f8e7d")).toBeInTheDocument();
  });

  it("says 'no version tag' when only the workflow id is known", () => {
    renderWithProviders(<ChainLineageBadge chain_context_installed chain_source_workflow_id="ppt" />);

    expect(screen.getByLabelText("Chained from Ppt no version tag")).toBeInTheDocument();
  });

  it("labels a source with only a short id as 'Unknown Workflow'", () => {
    renderWithProviders(
      <ChainLineageBadge chain_context_installed chain_source_short_id="abc" chain_source_published_status="published" />,
    );

    expect(screen.getByLabelText("Chained from Unknown Workflow abc (published)")).toBeInTheDocument();
  });
});

// ─── VersionTimeline ─────────────────────────────────────────────────────────
describe("VersionTimeline", () => {
  const family: RunFamily = {
    root_id: "a",
    members: [
      member({ id: "c", revision_index: 3, parent_run_id: "b", status: "failed", git_tag: "v3" }),
      member({ id: "a", revision_index: 1 }),
      member({ id: "b", revision_index: 2, parent_run_id: "a", status: "running" }),
    ],
  };

  function Harness({
    initial = "a", input = "", fam = family, onSelect,
  }: { initial?: string; input?: string; fam?: RunFamily | null; onSelect?: (id: string) => void }) {
    const [active, setActive] = useState(initial);
    return (
      <VersionTimeline
        family={fam}
        activeRunId={active}
        activeInput={input}
        onSelectVersion={(id) => { onSelect?.(id); setActive(id); }}
      />
    );
  }

  it("renders nothing when there is no family", () => {
    const { container } = renderWithProviders(<Harness fam={null} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing for a single-member family", () => {
    const { container } = renderWithProviders(
      <Harness fam={{ root_id: "a", members: [member({ id: "a" })] }} />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("renders chips in revision order with lineage names, tags and a single tab stop", () => {
    renderWithProviders(<Harness initial="b" />);

    const chips = screen.getAllByRole("radio");
    expect(chips.map((c) => c.getAttribute("aria-label"))).toEqual([
      "Version 1, completed",
      "Version 2, revises version 1, running",
      "Version 3, revises version 2, failed",
    ]);
    expect(chips[1]).toBeChecked();
    expect(chips[1]).toHaveAttribute("tabindex", "0");
    expect(chips[0]).toHaveAttribute("tabindex", "-1");
    expect(screen.getByLabelText("Tagged v3")).toBeInTheDocument();
  });

  it("selects a version on click and moves focus to the newly active chip", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    renderWithProviders(<Harness onSelect={onSelect} />);

    await user.click(screen.getByRole("radio", { name: /^Version 3/ }));

    expect(onSelect).toHaveBeenCalledWith("c");
    expect(screen.getByRole("radio", { name: /^Version 3/ })).toHaveFocus();
  });

  it("does not steal focus on the initial mount", () => {
    renderWithProviders(<Harness initial="b" />);

    expect(screen.getByRole("radio", { name: /^Version 2/ })).not.toHaveFocus();
  });

  it.each([["{ArrowRight}"], ["{ArrowDown}"]])("%s moves to the next version", async (key) => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    renderWithProviders(<Harness initial="a" onSelect={onSelect} />);

    screen.getByRole("radio", { name: /^Version 1/ }).focus();
    await user.keyboard(key);

    expect(onSelect).toHaveBeenCalledWith("b");
  });

  it.each([["{ArrowLeft}"], ["{ArrowUp}"]])("%s moves to the previous version", async (key) => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    renderWithProviders(<Harness initial="c" onSelect={onSelect} />);

    screen.getByRole("radio", { name: /^Version 3/ }).focus();
    await user.keyboard(key);

    expect(onSelect).toHaveBeenCalledWith("b");
  });

  it("does not wrap past the first or last version", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    renderWithProviders(<Harness initial="a" onSelect={onSelect} />);
    screen.getByRole("radio", { name: /^Version 1/ }).focus();
    await user.keyboard("{ArrowLeft}");
    expect(onSelect).not.toHaveBeenCalled();

    await user.click(screen.getByRole("radio", { name: /^Version 3/ }));
    onSelect.mockClear();
    await user.keyboard("{ArrowRight}");

    expect(onSelect).not.toHaveBeenCalled();
  });

  it.each([["{Enter}"], [" "]])("%j re-selects the current version", async (key) => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    renderWithProviders(<Harness initial="b" onSelect={onSelect} />);

    screen.getByRole("radio", { name: /^Version 2/ }).focus();
    await user.keyboard(key);

    expect(onSelect).toHaveBeenCalledWith("b");
  });

  it("ignores other keys", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    renderWithProviders(<Harness initial="b" onSelect={onSelect} />);

    screen.getByRole("radio", { name: /^Version 2/ }).focus();
    await user.keyboard("x");

    expect(onSelect).not.toHaveBeenCalled();
  });

  it("ignores arrow keys when the active run is not part of the family", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    renderWithProviders(<Harness initial="zzz" onSelect={onSelect} />);

    screen.getAllByRole("radio")[0].focus();
    await user.keyboard("{ArrowRight}");

    expect(onSelect).not.toHaveBeenCalled();
  });

  it("explains what a revision changed, quoting the instruction", () => {
    const input = "Base\n=== REVISION REQUEST ===\nUse a darker theme\n=== END REQUEST ===";
    renderWithProviders(<Harness initial="b" input={input} />);

    expect(screen.getByText(/↳ revises v1/)).toHaveTextContent("↳ revises v1 — ‘Use a darker theme’");
  });

  it("omits the quoted instruction when the input is empty", () => {
    renderWithProviders(<Harness initial="b" input="" />);

    expect(screen.getByText(/↳ revises v1/).textContent).toBe("↳ revises v1");
  });

  it("shows no revision context for the root version", () => {
    renderWithProviders(<Harness initial="a" input="anything" />);

    expect(screen.queryByText(/↳ revises/)).not.toBeInTheDocument();
  });

  it("shows the chain lineage for an active member whose chain payload was installed", () => {
    const chained: RunFamily = {
      root_id: "a",
      members: [
        member({
          id: "a", revision_index: 1, chain_context_installed: true,
          chain_source_workflow_id: "ppt", chain_source_visible_tag: "v1",
        }),
        member({ id: "b", revision_index: 2, parent_run_id: "a" }),
      ],
    };
    renderWithProviders(<Harness initial="a" fam={chained} />);

    expect(screen.getByLabelText("Chained from Ppt v1")).toBeInTheDocument();
  });
});
