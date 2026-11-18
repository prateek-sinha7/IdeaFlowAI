import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ToolCallsSection, formatCallTime } from "./AgentDetailPanel";
import type { ToolCallEntry } from "@/types/index";

const calls: ToolCallEntry[] = [
  { tool: "read_file", args: { file_path: "spec.md" }, result: "ok", timestamp: "2026-11-11T21:01:00Z" },
  { tool: "edit_file", args: { file_path: "prototype.html" }, result: "ok", timestamp: "2026-11-11T21:02:30Z" },
  { tool: "run_acceptance", args: { ids: "G1" }, result: null, timestamp: "2026-11-11T21:03:45Z" },
];

describe("ToolCallsSection", () => {
  it("lists the newest call first", () => {
    render(<ToolCallsSection toolCalls={calls} />);
    const rows = screen.getAllByRole("button", { expanded: false });
    expect(rows.map((r) => within(r).queryByText(/read_file|edit_file|run_acceptance/)?.textContent)).toEqual([
      "run_acceptance",
      "edit_file",
      "read_file",
    ]);
  });

  it("shows each call's date and time from its own timestamp", () => {
    render(<ToolCallsSection toolCalls={calls} />);
    const times = screen.getAllByTestId("tool-call-time");
    expect(times).toHaveLength(3);
    expect(times[0]).toHaveAttribute("dateTime", "2026-11-11T21:03:45Z");
    expect(times[0].textContent).toBe(formatCallTime("2026-11-11T21:03:45Z"));
  });

  it("sorts by date and time, not arrival order", () => {
    const outOfOrder: ToolCallEntry[] = [
      { tool: "grep", args: {}, result: "ok", timestamp: "2026-11-11T22:10:00Z" },
      { tool: "ls", args: {}, result: "ok", timestamp: "2026-11-11T22:30:00Z" },
      { tool: "glob", args: {}, result: "ok", timestamp: "2026-11-11T22:20:00Z" },
    ];
    render(<ToolCallsSection toolCalls={outOfOrder} />);
    expect(screen.getAllByTestId("tool-call-time").map((t) => t.getAttribute("dateTime"))).toEqual([
      "2026-11-11T22:30:00Z",
      "2026-11-11T22:20:00Z",
      "2026-11-11T22:10:00Z",
    ]);
  });

  it("keeps the list in a scrolling window of about 20 rows", () => {
    render(<ToolCallsSection toolCalls={calls} />);
    const list = screen.getByTestId("tool-calls-list");
    expect(list.className).toContain("overflow-y-auto");
    expect(list.className).toMatch(/max-h-\[\d+px\]/);
  });

  it("formats a bad or missing timestamp as empty", () => {
    expect(formatCallTime(undefined)).toBe("");
    expect(formatCallTime("not a date")).toBe("");
    expect(formatCallTime("2026-11-11T21:03:45Z")).toMatch(/11 .*\d{2}:\d{2}:\d{2}/);
  });
});
