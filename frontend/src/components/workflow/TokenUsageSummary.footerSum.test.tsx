import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";
import { TokenUsageSummary } from "./TokenUsageSummary";
import type { PipelineRunState } from "@/types/index";

// ISS-278 — the Steps tab "TOKEN USAGE" footer shows `total · input · output`,
// but when caching is active the visible "input" figure is the uncached
// remainder (input - cacheRead - cacheWrite), not the full input that `total`
// was computed from. So input + output can never reconstruct the stated
// total (e.g. real run: 141.3K + 192.8K = 334.1K vs a stated 3.1M total).
// The correct full input value is already in scope (it's what feeds the
// element's own tooltip) — it's just not what's rendered as the label.

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

describe("TokenUsageSummary — footer input+output must reconstruct total (ISS-278)", () => {
  it(
    "ISS-278: shows the full input figure (not the uncached remainder) when caching is active, mirroring the reported run",
    () => {
      render(
        <TokenUsageSummary
          pipelineState={{
            ...base,
            totalTokens: 3105278,
            totalInputTokens: 2915058,
            totalOutputTokens: 190220,
            cacheReadTokens: 2443873,
            cacheWriteTokens: 332250,
          } as PipelineRunState}
        />,
      );

      // The visible "input" label must be the FULL input total (the same value
      // `total` was derived from), so input + output reconstructs total.
      expect(screen.getByText("2.9M input")).toBeTruthy();
    },
  );

  it(
    "ISS-278: shows the full input figure (not the uncached remainder) — smaller fixture",
    () => {
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

      expect(screen.getByText("70.0K input")).toBeTruthy();
    },
  );
});
