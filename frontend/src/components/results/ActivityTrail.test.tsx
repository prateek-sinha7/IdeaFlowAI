import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ActivityTrail } from "./ActivityTrail";
import type { ActivityRun } from "@/lib/runChain";

const runs: ActivityRun[] = [
  { kind: "reason", count: 1 },
  { kind: "read", count: 4, paths: ["spec.md", "build/screens.json"], tools: ["read_file"] },
  { kind: "write", count: 1, paths: ["design.md"], tools: ["write_file"] },
  { kind: "output", count: 1 },
];

describe("ActivityTrail", () => {
  it("a live step renders one labelled pill per run with its count, newest first", () => {
    render(<ActivityTrail runs={runs} status="running" />);
    const boxes = screen.getAllByTestId("activity-box");
    expect(boxes.map((b) => b.getAttribute("data-kind"))).toEqual(["output", "write", "read", "reason"]);
    expect(boxes[2]).toHaveTextContent("read×4");
    expect(screen.getByTestId("activity-trail")).toHaveAttribute(
      "aria-label",
      "Activity, latest first: output, before that write, before that read 4 times, before that reason",
    );
  });

  it("the tooltip names the tool and the files it touched", () => {
    render(<ActivityTrail runs={runs} status="running" />);
    const read = screen.getAllByTestId("activity-box")[2];
    expect(read).toHaveAttribute("title", "read ×4 · read_file\nspec.md\n…/screens.json\n+2 more");
  });

  it("a failed group shows the failed tone and a mark", () => {
    render(<ActivityTrail runs={[{ kind: "read", count: 2, hasFailed: true, tools: ["read_file"] }]} />);
    const box = screen.getByTestId("activity-box");
    expect(box.className).toContain("status-failed");
    expect(box).toHaveTextContent("!");
    expect(box.getAttribute("title")).toContain("a call returned an error");
  });

  it("the newest (first) pill pulses only while the step runs", () => {
    const { rerender } = render(<ActivityTrail runs={runs} status="running" />);
    let boxes = screen.getAllByTestId("activity-box");
    expect(boxes[0].className).toContain("animate-pulse");
    expect(boxes[3].className).not.toContain("animate-pulse");
    rerender(<ActivityTrail runs={runs} status="done" />);
    boxes = screen.getAllByTestId("activity-box");
    expect(boxes[0].className).not.toContain("animate-pulse");
  });

  it("folds a long trail by hiding the lightest pills, keeping the ends and the heavy ones", () => {
    const long: ActivityRun[] = [
      { kind: "reason", count: 1 },
      ...Array.from({ length: 18 }, (_, i) => ({ kind: (i % 2 ? "read" : "write") as ActivityRun["kind"], count: i === 5 ? 66 : 1 })),
      { kind: "output", count: 1 },
    ];
    render(<ActivityTrail runs={long} maxPills={8} status="done" />);
    const shown = screen.getAllByTestId("activity-box");
    expect(shown.length).toBeLessThanOrEqual(8);
    // newest first: the last run (output) leads, the first run (reason) closes the row
    expect(shown[0]).toHaveAttribute("data-kind", "output");
    expect(shown[shown.length - 1]).toHaveAttribute("data-kind", "reason");
    expect(shown.some((b) => b.textContent?.includes("×66"))).toBe(true);
    const folds = screen.getAllByTestId("activity-more");
    expect(folds.reduce((n, f) => n + Number(f.textContent!.replace("+", "")), 0)).toBe(long.length - shown.length);
    expect(screen.getByTestId("activity-trail").className).toContain("whitespace-nowrap");
  });

  it("live shows labels, done summarises to icons; both stay on one line", () => {
    const { rerender } = render(<ActivityTrail runs={runs} status="running" />);
    expect(screen.getAllByTestId("activity-box")[2]).toHaveTextContent("read×4");
    expect(screen.getByTestId("activity-trail").className).toContain("whitespace-nowrap");
    expect(screen.getByTestId("activity-trail").className).not.toContain("flex-wrap");
    rerender(<ActivityTrail runs={runs} status="done" />);
    const box = screen.getAllByTestId("activity-box")[2];
    expect(box).toHaveTextContent("×4");
    expect(box).not.toHaveTextContent("read");
    expect(box.getAttribute("title")).toContain("read ×4");
    expect(screen.getByTestId("activity-trail").className).toContain("whitespace-nowrap");
  });

  it("renders nothing for an empty trail", () => {
    const { container } = render(<ActivityTrail runs={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("a very long trail keeps every pill on one row that scrolls sideways", () => {
    const long: ActivityRun[] = Array.from({ length: 200 }, (_, i) => ({
      kind: i % 2 ? "read" : "write",
      count: 1,
    }));
    render(<ActivityTrail runs={long} status="done" />);
    expect(screen.getAllByTestId("activity-box")).toHaveLength(200);
    expect(screen.queryByTestId("activity-more")).toBeNull();
    const trail = screen.getByTestId("activity-trail");
    expect(trail.className).toContain("overflow-x-auto");
    expect(trail.className).toContain("whitespace-nowrap");
  });
});
