import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { CanvasNode } from "./CanvasNode";
import type { AgentDef } from "@/types/index";

// The avatar mark follows the rail's fan-out lever (`selection.strategy`), not
// the manifest as loaded — flipping the lever must change the card at once.
const agent = { id: "readers", name: "Readers", role: "Custom agent", isCustom: true } as unknown as AgentDef;
const base = {
  agent, pipelineType: "custom" as never, selected: false, modelOptions: [], isChild: false,
  hasChildren: false, cardWidth: 280, left: 0, top: 0, onSelect: vi.fn(), onRemove: vi.fn(),
};

describe("CanvasNode kind mark", () => {
  it.each([
    [undefined, "AI agent"],
    ["wave_scheduler", "Wave agent"],
    ["fanout_batch", "Fan-out agent"],
    ["task_loop", "Task loop agent"],
  ] as const)("strategy %s shows %s", (strategy, label) => {
    render(<CanvasNode {...base} selection={strategy ? { strategy } : undefined} />);
    expect(screen.getByLabelText(label)).toBeInTheDocument();
  });

  it("a code step shows the code mark whatever the lever says", () => {
    render(<CanvasNode {...base} agent={{ ...agent, mechanical: "publish" }} selection={{ strategy: "wave_scheduler" }} />);
    expect(screen.getByLabelText("Code step")).toBeInTheDocument();
  });
});
