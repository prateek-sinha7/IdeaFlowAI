import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CheckResult, ToolActivity } from "@/types/workflowBuilder";

import type { TurnStep } from "./builderReducer";
import { BuilderProgress } from "./BuilderProgress";

function tool(overrides: Partial<ToolActivity> = {}): ToolActivity {
  return {
    call_id: "c1",
    tool: "read_file",
    kind: "read",
    label: "Read the catalog",
    status: "ok",
    duration_ms: 740,
    command: null,
    exit_code: null,
    summary: null,
    ...overrides,
  };
}

const CHECK: CheckResult = {
  source: "skill_validator",
  verdict: "valid",
  errors: 0,
  warnings: 1,
  attempt: null,
  attempts_left: null,
};

/** One run of tool calls over the given call ids, in order. */
function toolsStep(...callIds: string[]): TurnStep {
  return { kind: "tools", id: "tools-1", callIds };
}

describe("BuilderProgress live mode", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-01T00:00:00Z"));
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows the stage label with the elapsed time and ticks every second", () => {
    const startedAt = Date.now();
    render(
      <BuilderProgress
        mode="live"
        label="Checking the workflow"
        startedAt={startedAt}
        activity={[]}
        steps={[]}
        warnings={[]}
      />,
    );
    expect(screen.getByText("Checking the workflow · 0 s")).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(65_000);
    });
    expect(screen.getByText("Checking the workflow · 1 min 5 s")).toBeInTheDocument();
  });

  it("lists activity lines with status and duration", () => {
    render(
      <BuilderProgress
        mode="live"
        label="Reading"
        startedAt={Date.now()}
        activity={[
          tool(),
          tool({ call_id: "c2", label: "Write the draft", status: "running", duration_ms: null }),
        ]}
        steps={[toolsStep("c1", "c2")]}
        warnings={[]}
      />,
    );
    const list = screen.getByRole("list", { name: "Tool calls" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("Read the catalog");
    expect(rows[0]).toHaveTextContent("Done");
    expect(rows[0]).toHaveTextContent("740 ms");
    expect(rows[1]).toHaveTextContent("Write the draft");
    expect(rows[1]).toHaveTextContent("Running");
    expect(screen.getByText("2 tool calls")).toBeInTheDocument();
  });

  it("shows the command of a script call and nothing else from its call", async () => {
    vi.useRealTimers();
    const user = userEvent.setup();
    render(
      <BuilderProgress
        mode="live"
        label="Checking"
        startedAt={Date.now()}
        activity={[
          tool({
            kind: "script",
            label: "Ran the validator",
            command: "python validate.py draft.yaml",
            summary: "Found no problems",
          }),
        ]}
        steps={[toolsStep("c1")]}
        warnings={[]}
      />,
    );
    const row = within(screen.getByRole("list", { name: "Tool calls" })).getByRole("listitem");
    const details = row.querySelector("details");
    expect(details).not.toHaveAttribute("open");
    await user.click(within(row).getByText("Ran the validator"));
    expect(details).toHaveAttribute("open");
    expect(within(row).getByText("python validate.py draft.yaml")).toBeInTheDocument();
    expect(within(row).getByText("Found no problems")).toBeInTheDocument();
  });

  it("renders a call without summary or command as a plain line", () => {
    render(
      <BuilderProgress
        mode="live"
        label="Reading"
        startedAt={Date.now()}
        activity={[tool()]}
        steps={[toolsStep("c1")]}
        warnings={[]}
      />,
    );
    const row = within(screen.getByRole("list", { name: "Tool calls" })).getByRole("listitem");
    expect(row.querySelector("details")).toBeNull();
  });

  it("shows check lines and limit notices", () => {
    render(
      <BuilderProgress
        mode="live"
        label="Checking"
        startedAt={Date.now()}
        activity={[]}
        steps={[{ kind: "check", id: "check-1", check: CHECK }]}
        warnings={[{ kind: "time", used: 420, limit: 600 }]}
      />,
    );
    expect(screen.getByText("Skill validator: VALID, 1 warning")).toBeInTheDocument();
    expect(screen.getByText("About 3 minutes left in this turn")).toBeInTheDocument();
  });

  it("renders steps in arrival order, with a tool group between two thoughts", () => {
    const { container } = render(
      <BuilderProgress
        mode="live"
        label="Reading"
        startedAt={Date.now()}
        activity={[tool({ call_id: "c1", label: "Read A" }), tool({ call_id: "c2", label: "Read B" })]}
        steps={[
          { kind: "thinking", id: "th-1", text: "First thought" },
          { kind: "tools", id: "tl-1", callIds: ["c1"] },
          { kind: "thinking", id: "th-2", text: "Second thought" },
          { kind: "tools", id: "tl-2", callIds: ["c2"] },
          { kind: "text", id: "tx-1", text: "Final answer" },
        ]}
        warnings={[]}
      />,
    );
    const text = container.textContent ?? "";
    const positions = ["First thought", "Read A", "Second thought", "Read B", "Final answer"].map(
      (mark) => text.indexOf(mark),
    );
    expect(positions.every((p) => p >= 0)).toBe(true);
    expect(positions).toEqual([...positions].sort((a, b) => a - b));
    expect(screen.getAllByText("1 tool call")).toHaveLength(2);
  });

  it("labels a call the turn stopped as Stopped, not Failed", () => {
    render(
      <BuilderProgress
        mode="live"
        label="Reading"
        startedAt={Date.now()}
        activity={[tool({ status: "stopped", label: "Looked up the catalog", duration_ms: 523 })]}
        steps={[toolsStep("c1")]}
        warnings={[]}
      />,
    );
    const row = within(screen.getByRole("list", { name: "Tool calls" })).getByRole("listitem");
    expect(row).toHaveTextContent("Stopped");
    expect(row).not.toHaveTextContent("Failed");
  });

  it("skips a tool step whose calls are not in the activity list", () => {
    render(
      <BuilderProgress
        mode="live"
        label="Reading"
        startedAt={Date.now()}
        activity={[]}
        steps={[toolsStep("missing")]}
        warnings={[]}
      />,
    );
    expect(screen.queryByText(/tool call/)).toBeNull();
  });

  it("renders activity text as text, not HTML", () => {
    const { container } = render(
      <BuilderProgress
        mode="live"
        label="Reading"
        startedAt={Date.now()}
        activity={[tool({ label: "<img src=x onerror=alert(1)>" })]}
        steps={[toolsStep("c1")]}
        warnings={[]}
      />,
    );
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("<img src=x onerror=alert(1)>");
  });
});

describe("BuilderProgress ended mode", () => {
  it("collapses to the one-line summary and expands to activity and checks", async () => {
    const user = userEvent.setup();
    render(
      <BuilderProgress
        mode="ended"
        summary={{ actions: 14, checks: 2, duration_ms: 100_000 }}
        activity={[tool()]}
        checks={[CHECK]}
      />,
    );
    const summary = screen.getByText("14 actions, 2 checks, 1 min 40 s");
    const details = summary.closest("details");
    expect(details).not.toHaveAttribute("open");
    await user.click(summary);
    expect(details).toHaveAttribute("open");
    expect(screen.getByRole("list", { name: "Activity" })).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Checks" })).toBeInTheDocument();
  });

  it("uses singular nouns for a single action and check", () => {
    render(
      <BuilderProgress
        mode="ended"
        summary={{ actions: 1, checks: 1, duration_ms: 40_000 }}
        activity={[]}
        checks={[]}
      />,
    );
    expect(screen.getByText("1 action, 1 check, 40 s")).toBeInTheDocument();
  });
});
