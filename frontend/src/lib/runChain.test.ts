import { describe, expect, it } from "vitest";
import { stepActivity, toolCallFailed, toolKind } from "./runChain";

const call = (tool: string, args: Record<string, unknown> = {}, result: string | null = "ok") => ({ tool, args, result });

describe("stepActivity", () => {
  it("a reason-only agent yields [reason]", () => {
    expect(stepActivity({ thinkingText: "thinking…", toolCalls: [] })).toEqual([{ kind: "reason", count: 1 }]);
  });

  it("three read_file calls then one write_file collapse to read ×3, write, with their paths", () => {
    const runs = stepActivity({
      toolCalls: [
        call("read_file", { path: "spec.md" }),
        call("read_file", { path: "build/screens.json" }),
        call("read_file", { path: "spec.md" }),
        call("write_file", { path: "design.md" }),
      ],
    });
    expect(runs.map((r) => [r.kind, r.count])).toEqual([["read", 3], ["write", 1]]);
    expect(runs[0].paths).toEqual(["spec.md", "build/screens.json"]);
    expect(runs[1].paths).toEqual(["design.md"]);
  });

  it("maps this backend's tools: ls → search, file_info → read, edit_file → write, playwright → browse, ask_user → ask", () => {
    expect(toolKind("ls")).toBe("search");
    expect(toolKind("file_info")).toBe("read");
    expect(toolKind("edit_file")).toBe("write");
    expect(toolKind("playwright_navigate")).toBe("browse");
    expect(toolKind("ask_user")).toBe("ask");
    expect(toolKind("bash")).toBe("run");
    expect(toolKind("mystery")).toBe("tool");
  });

  it("an agent with output ends with output, and report_task_complete is not a box", () => {
    const runs = stepActivity({ toolCalls: [call("report_task_complete")], output: "done" });
    expect(runs).toEqual([{ kind: "output", count: 1 }]);
  });

  it("a pending result (null) is not a failure; an error result is", () => {
    expect(toolCallFailed(null)).toBe(false);
    expect(toolCallFailed("Error: no such file spec.md")).toBe(true);
    const runs = stepActivity({
      toolCalls: [call("read_file", { path: "a.md" }, null), call("read_file", { path: "b.md" }, "Error: not found")],
    });
    expect(runs).toHaveLength(1);
    expect(runs[0].hasFailed).toBe(true);
  });

  it("path collection stops at five distinct paths", () => {
    const runs = stepActivity({
      toolCalls: Array.from({ length: 8 }, (_, i) => call("read_file", { path: `f${i}.md` })),
    });
    expect(runs[0].count).toBe(8);
    expect(runs[0].paths).toHaveLength(5);
  });
});
