/**
 * Phase 38 plan-02 (B4-02) — BarChart render + a11y contract (RED-first).
 *
 * Encodes the a11y invariant the extracted primitive must satisfy: the bar
 * chart advertises role="img" with an aria-label carrying the data summary
 * (T-38-A11Y), and it renders exactly one bar element per datum. Authored
 * BEFORE ./BarChart exists, so the import is unresolved (RED); Task 2 creates
 * the component and turns it GREEN.
 *
 * Mirrors the render-test + motion-proxy conventions in
 * SavedWorkflowsPage.test.tsx (motion/react stripped so role queries resolve).
 */

import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

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

import { BarChart } from "./BarChart";

const DATA = [
  { label: "Mon", value: 120 },
  { label: "Tue", value: 340 },
  { label: "Wed", value: 90 },
];

describe("BarChart — render + a11y", () => {
  it("exposes a role='img' element whose aria-label reflects the data summary", () => {
    render(<BarChart data={DATA} ariaLabel="Token usage over 3 days, peak 340" />);
    const img = screen.getByRole("img");
    expect(img).toBeInTheDocument();
    expect(img).toHaveAttribute("aria-label", expect.stringContaining("340"));
  });

  it("renders exactly one bar element per datum", () => {
    render(<BarChart data={DATA} ariaLabel="Token usage over 3 days" />);
    expect(screen.getAllByTestId("bar-chart-bar")).toHaveLength(DATA.length);
  });

  it("renders nothing for an empty data array without throwing", () => {
    const { container } = render(<BarChart data={[]} ariaLabel="No data" />);
    expect(container).toBeInTheDocument();
    expect(screen.queryAllByTestId("bar-chart-bar")).toHaveLength(0);
  });
});
