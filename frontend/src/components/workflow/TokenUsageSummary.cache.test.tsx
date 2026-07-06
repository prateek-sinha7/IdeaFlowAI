import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
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

import React from "react";

const base = {
  isRunning: false,
  pipeline_type: "prototype",
  agents: [],
  currentAgentIndex: 0,
  totalDuration: 1000,
  completedCount: 0,
} as PipelineRunState;

describe("TokenUsageSummary — prompt-cache breakdown", () => {
  it("Spec A: renders the cached segment when cacheReadTokens > 0", () => {
    render(
      <TokenUsageSummary
        pipelineState={{
          ...base,
          totalTokens: 100000,
          totalInputTokens: 70000,
          totalOutputTokens: 30000,
          cacheReadTokens: 60000,
        } as PipelineRunState}
      />,
    );
    // pct = Math.round(60000 / 70000 * 100) = 86; formatTokens(60000) = "60.0K"
    expect(screen.getByText(/cached/i)).toBeTruthy();
    const cached = screen.getByText(/cached/i).textContent ?? "";
    expect(cached).toContain("86%");
    expect(cached).toContain("60.0K");
  });

  it("Spec B: renders no cached segment (zero regression) when cacheReadTokens undefined", () => {
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
    expect(screen.queryByText(/cached/i)).toBeNull();
    // input/output still present
    expect(screen.getByText(/70\.0K input/)).toBeTruthy();
    expect(screen.getByText(/30\.0K output/)).toBeTruthy();
  });

  it("Spec B2: renders no cached segment when cacheReadTokens is 0", () => {
    render(
      <TokenUsageSummary
        pipelineState={{
          ...base,
          totalTokens: 100000,
          totalInputTokens: 70000,
          totalOutputTokens: 30000,
          cacheReadTokens: 0,
        } as PipelineRunState}
      />,
    );
    expect(screen.queryByText(/cached/i)).toBeNull();
  });

  it("Spec C: renders a 'written' fragment when cacheWriteTokens > 0", () => {
    render(
      <TokenUsageSummary
        pipelineState={{
          ...base,
          totalTokens: 100000,
          totalInputTokens: 70000,
          totalOutputTokens: 30000,
          cacheReadTokens: 60000,
          cacheWriteTokens: 5000,
        } as PipelineRunState}
      />,
    );
    expect(screen.getByText(/written/i)).toBeTruthy();
  });

  it("Spec C2: renders no 'written' fragment when cacheWriteTokens is 0", () => {
    render(
      <TokenUsageSummary
        pipelineState={{
          ...base,
          totalTokens: 100000,
          totalInputTokens: 70000,
          totalOutputTokens: 30000,
          cacheReadTokens: 60000,
          cacheWriteTokens: 0,
        } as PipelineRunState}
      />,
    );
    expect(screen.queryByText(/written/i)).toBeNull();
  });
});
