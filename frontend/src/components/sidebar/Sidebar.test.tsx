import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Sidebar } from "./Sidebar";
import type { WorkflowRun } from "@/types/index";

// Local noon on a fixed day; only Date is faked so user-event/async stay real.
const NOW = new Date(2025, 5, 15, 12, 0, 0);
const DAY = 86400000;

function makeRun(overrides: Partial<WorkflowRun> = {}): WorkflowRun {
  return {
    id: "run-1",
    title: "Run One",
    type: "prototype",
    status: "completed",
    input: "some input",
    parentRunId: null,
    rootRunId: "run-1",
    createdAt: NOW.toISOString(),
    agentCount: 1,
    ...overrides,
  };
}

describe("Sidebar", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(NOW);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows the empty state when there are no runs", () => {
    render(<Sidebar />);
    expect(screen.getByText("No projects yet")).toBeInTheDocument();
    expect(screen.getByText("Start a workflow to see your history here")).toBeInTheDocument();
  });

  it("renders branding and search input", () => {
    render(<Sidebar />);
    expect(screen.getByRole("heading", { name: "VelocityAI" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Search projects" })).toBeInTheDocument();
  });

  it("calls onOpenWorkflow when New Project is clicked", async () => {
    const user = userEvent.setup();
    const onOpenWorkflow = vi.fn();
    render(<Sidebar onOpenWorkflow={onOpenWorkflow} />);
    await user.click(screen.getByRole("button", { name: "New Project" }));
    expect(onOpenWorkflow).toHaveBeenCalledTimes(1);
  });

  it("hides collapse and logout buttons when callbacks are absent", () => {
    render(<Sidebar />);
    expect(screen.queryByRole("button", { name: "Close sidebar" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Log out" })).not.toBeInTheDocument();
  });

  it("calls onCollapse when Close sidebar is clicked", async () => {
    const user = userEvent.setup();
    const onCollapse = vi.fn();
    render(<Sidebar onCollapse={onCollapse} />);
    await user.click(screen.getByRole("button", { name: "Close sidebar" }));
    expect(onCollapse).toHaveBeenCalledTimes(1);
  });

  it("calls onLogout when Log out is clicked", async () => {
    const user = userEvent.setup();
    const onLogout = vi.fn();
    render(<Sidebar onLogout={onLogout} />);
    await user.click(screen.getByRole("button", { name: "Log out" }));
    expect(onLogout).toHaveBeenCalledTimes(1);
  });

  it("renders a run with its type label and duration, without empty state", () => {
    render(<Sidebar recentRuns={[makeRun({ duration: 42 })]} />);
    const btn = screen.getByRole("button", { name: /Run One/ });
    expect(btn).toHaveTextContent("Prototype • 42s");
    expect(screen.queryByText("No projects yet")).not.toBeInTheDocument();
  });

  it("omits duration when absent", () => {
    render(<Sidebar recentRuns={[makeRun({ duration: undefined, type: "ppt" })]} />);
    const btn = screen.getByRole("button", { name: /Run One/ });
    expect(btn).toHaveTextContent("Presentation");
    expect(btn).not.toHaveTextContent("•");
  });

  it("calls onSelectRun with the clicked run", async () => {
    const user = userEvent.setup();
    const onSelectRun = vi.fn();
    const run = makeRun();
    render(<Sidebar recentRuns={[run]} onSelectRun={onSelectRun} />);
    await user.click(screen.getByRole("button", { name: /Run One/ }));
    expect(onSelectRun).toHaveBeenCalledExactlyOnceWith(run);
  });

  it("does not throw when a run is clicked without onSelectRun", async () => {
    const user = userEvent.setup();
    render(<Sidebar recentRuns={[makeRun()]} />);
    await user.click(screen.getByRole("button", { name: /Run One/ }));
    expect(screen.getByRole("button", { name: /Run One/ })).toBeInTheDocument();
  });

  it("falls back to the first 40 chars of input when title is empty", () => {
    const input = "a".repeat(50);
    render(<Sidebar recentRuns={[makeRun({ title: "", input })]} />);
    expect(screen.getByText("a".repeat(40))).toBeInTheDocument();
  });

  it("shows the brief when title contains markers and no revision", () => {
    const title = "Build a dashboard\n=== Attached: a.txt ===\nbody\n=== End: a.txt ===";
    render(<Sidebar recentRuns={[makeRun({ title })]} />);
    expect(screen.getByText("Build a dashboard")).toBeInTheDocument();
  });

  it("shows the revision instruction first line when title contains a revision request", () => {
    const title = "Original brief\n=== REVISION REQUEST ===\nMake it blue\nand bigger\n=== END REQUEST ===";
    render(<Sidebar recentRuns={[makeRun({ title })]} />);
    expect(screen.getByText("Make it blue")).toBeInTheDocument();
  });

  it("falls back to the raw title when parsing yields an empty brief", () => {
    const title = "=== Attached: a.txt ===\nbody\n=== End: a.txt ===";
    render(<Sidebar recentRuns={[makeRun({ title })]} />);
    const btn = screen.getByRole("button", { name: /Attached: a\.txt/ });
    expect(btn).toBeInTheDocument();
  });

  it.each([
    ["Today", 0],
    ["Yesterday", DAY],
    ["This Week", 3 * DAY],
    ["Earlier", 30 * DAY],
  ])("groups a run into %s", (group, offset) => {
    const created = new Date(NOW.getTime() - offset).toISOString();
    render(<Sidebar recentRuns={[makeRun({ id: "g", title: `in-${group}`, createdAt: created })]} />);
    expect(screen.getByText(group)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: new RegExp(`in-${group}`) })).toBeInTheDocument();
  });

  it("renders multiple runs of the same group under one heading", () => {
    render(
      <Sidebar
        recentRuns={[makeRun({ id: "a", title: "Alpha" }), makeRun({ id: "b", title: "Beta", type: "custom" })]}
      />,
    );
    expect(screen.getAllByText("Today")).toHaveLength(1);
    expect(screen.getByRole("button", { name: /Beta/ })).toHaveTextContent("Custom");
  });

  it("filters runs by title case-insensitively", async () => {
    const user = userEvent.setup();
    render(
      <Sidebar recentRuns={[makeRun({ id: "a", title: "Alpha" }), makeRun({ id: "b", title: "Beta" })]} />,
    );
    await user.type(screen.getByRole("textbox", { name: "Search projects" }), "ALP");
    expect(screen.getByRole("button", { name: /Alpha/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Beta/ })).not.toBeInTheDocument();
  });

  it("filters by input when title is empty", async () => {
    const user = userEvent.setup();
    render(
      <Sidebar
        recentRuns={[
          makeRun({ id: "a", title: "", input: "needle in input" }),
          makeRun({ id: "b", title: "Other", input: "x" }),
        ]}
      />,
    );
    await user.type(screen.getByRole("textbox", { name: "Search projects" }), "needle");
    expect(screen.getByRole("button", { name: /needle in input/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Other/ })).not.toBeInTheDocument();
  });

  it("shows no run buttons and no empty state when search matches nothing", async () => {
    const user = userEvent.setup();
    render(<Sidebar recentRuns={[makeRun()]} />);
    await user.type(screen.getByRole("textbox", { name: "Search projects" }), "zzz");
    expect(screen.queryByRole("button", { name: /Run One/ })).not.toBeInTheDocument();
    expect(screen.queryByText("No projects yet")).not.toBeInTheDocument();
  });

  it.each([
    ["running"],
    ["completed"],
    ["failed"],
    ["cancelled"],
    ["degraded"],
    ["revising"],
    ["planning"],
    ["generating"],
    ["waiting_for_user"],
    ["clarifying"],
    ["analyzing"],
    ["diverted"],
  ] as const)("renders a run with status %s", (status) => {
    render(<Sidebar recentRuns={[makeRun({ status })]} />);
    const btn = screen.getByRole("button", { name: /Run One/ });
    expect(within(btn).getByText(/Prototype/)).toBeInTheDocument();
  });

  it("spins the status icon only for running runs", () => {
    const { rerender } = render(<Sidebar recentRuns={[makeRun({ status: "running" })]} />);
    expect(screen.getByRole("button", { name: /Run One/ }).querySelector(".animate-spin")).not.toBeNull();
    rerender(<Sidebar recentRuns={[makeRun({ status: "completed" })]} />);
    expect(screen.getByRole("button", { name: /Run One/ }).querySelector(".animate-spin")).toBeNull();
  });

  it.each([
    ["user_stories", "User Stories"],
    ["ppt_v2", "Presentation (v2)"],
    ["app_builder", "App Builder"],
    ["mulesoft_to_springboot", "Mulesoft → Spring Boot"],
    ["dotnet_to_azure", ".NET → Azure"],
  ] as const)("shows the label for workflow type %s", (type, label) => {
    render(<Sidebar recentRuns={[makeRun({ type })]} />);
    expect(screen.getByRole("button", { name: /Run One/ })).toHaveTextContent(label);
  });
});
