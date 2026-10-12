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
    "ISS-278: input + output reconstructs total, cache reads never shown — the reported run",
    () => {
      render(
        <TokenUsageSummary
          pipelineState={{
            ...base,
            totalTokens: 661405,
            totalInputTokens: 471185,
            totalOutputTokens: 190220,
            cacheReadTokens: 2443873,
            cacheWriteTokens: 332250,
          } as PipelineRunState}
        />,
      );

      // input + output reconstructs total; cache reads are never shown.
      expect(screen.getByText("471.2K input")).toBeTruthy();
      expect(screen.getByText("661.4K total")).toBeTruthy();
      expect(screen.queryByText(/cached/i)).toBeNull();
    },
  );

  it(
    "ISS-278: input + output reconstructs total — smaller fixture",
    () => {
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

      expect(screen.getByText("10.0K input")).toBeTruthy();
      expect(screen.getByText("40.0K total")).toBeTruthy();
    },
  );
});
