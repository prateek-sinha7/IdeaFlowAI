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

describe("TokenUsageSummary — Steps bar (cache detail removed, shown on Analytics page)", () => {
  // Cache tokens are NO LONGER shown inline in the Steps bar — they live on the
  // Analytics page. The Steps bar shows total · uncached-input · output.
  // When caching is active, "input" = uncached portion; the tooltip carries the gross.

  it("Spec A: with cacheReadTokens > 0 shows uncached input (gross - cache_read)", () => {
    // input=70K, cacheRead=60K → uncached = 70K - 60K = 10K = "10.0K input"
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
    // No "cached" label in Steps bar — that lives on Analytics
    expect(screen.queryByText(/cached/i)).toBeNull();
    expect(screen.getByText(/input/i)).toBeTruthy();
    // output still shown
    expect(screen.getByText(/30\.0K output/)).toBeTruthy();
  });

  it("Spec B: no caching — shows gross input unchanged", () => {
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
    expect(screen.getByText(/70\.0K input/)).toBeTruthy();
    expect(screen.getByText(/30\.0K output/)).toBeTruthy();
  });

  it("Spec B2: cacheReadTokens=0 shows gross input (no caching active)", () => {
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
    expect(screen.getByText(/70\.0K input/)).toBeTruthy();
  });

  it("Spec C: with cacheWriteTokens > 0 no 'written' label in Steps bar", () => {
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
    // "written" is only on the Analytics page, never in the Steps bar
    expect(screen.queryByText(/written/i)).toBeNull();
    expect(screen.queryByText(/cached/i)).toBeNull();
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
