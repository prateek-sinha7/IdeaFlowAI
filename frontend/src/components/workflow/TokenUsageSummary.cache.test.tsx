import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { TokenUsageSummary } from "./TokenUsageSummary";
import type { PipelineRunState } from "@/types/index";

// Mock `motion/react` — it doesn't run reliably under jsdom and none of these
// render assertions care about animation. Each `motion.X` access returns a
// component rendering the same underlying HTML tag, with motion-specific props
// stripped so React doesn't warn about unknown DOM attributes.
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

const base = {
  isRunning: false,
  pipeline_type: "prototype",
  agents: [],
  currentAgentIndex: 0,
  totalDuration: 1000,
  completedCount: 0,
} as PipelineRunState;

describe("TokenUsageSummary — total · input · output as the backend counts them, never cache reads", () => {
  // The backend's input already excludes cache reads (agents/capabilities/
  // token_usage.py): input = uncached + cache write, total = input + output.

  it("Spec A: shows the fields as sent — cache reads appear nowhere", () => {
    render(
      <TokenUsageSummary
        pipelineState={{
          ...base,
          totalTokens: 40000,
          totalInputTokens: 10000,
          totalOutputTokens: 30000,
          cacheReadTokens: 60000,
          cacheWriteTokens: 5000,
        } as PipelineRunState}
      />,
    );
    expect(screen.getByText("40.0K total")).toBeTruthy();
    expect(screen.getByText("10.0K input")).toBeTruthy();
    expect(screen.getByText("30.0K output")).toBeTruthy();
    expect(screen.queryByText(/cached|cache read|written/i)).toBeNull();
  });

  it("Spec B: live — a running wave's finished members count before the engine's totals exist", () => {
    render(
      <TokenUsageSummary
        pipelineState={{
          ...base,
          totalTokens: 1_300_000,
          totalInputTokens: 1_200_000,
          totalOutputTokens: 100_000,
          agents: [
            { status: "done", inputTokens: 1_200_000, outputTokens: 100_000 },
            { status: "running", waveWorkers: [
              { taskId: "a", status: "done", inputTokens: 500_000, outputTokens: 50_000 },
              { taskId: "b", status: "running" },
            ] },
          ],
        } as unknown as PipelineRunState}
      />,
    );
    expect(screen.getByText("1.7M input")).toBeTruthy();
    expect(screen.getByText("150.0K output")).toBeTruthy();
    expect(screen.getByText("1.9M total")).toBeTruthy();
  });

  it("Spec C: the engine's totals win when larger — they include calls made outside any step", () => {
    render(
      <TokenUsageSummary
        pipelineState={{
          ...base,
          totalTokens: 1_121_000,
          totalInputTokens: 896_000,
          totalOutputTokens: 225_000,
          agents: [{ status: "done", inputTokens: 416_000, outputTokens: 80_000 }],
        } as unknown as PipelineRunState}
      />,
    );
    expect(screen.getByText("896.0K input")).toBeTruthy();
    expect(screen.getByText("225.0K output")).toBeTruthy();
    expect(screen.getByText("1.1M total")).toBeTruthy();
  });

  it("Spec D: total is always rendered", () => {
    render(
      <TokenUsageSummary
        pipelineState={{
          ...base,
          totalTokens: 100000,
          totalInputTokens: 70000,
          totalOutputTokens: 30000,
        } as PipelineRunState}
      />,
    );
    expect(screen.getByText(/100\.0K total/)).toBeTruthy();
  });
});
