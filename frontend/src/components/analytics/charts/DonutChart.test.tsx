/**
 * Phase 38 plan-02 (B4-02) — DonutChart render + a11y contract (RED-first).
 *
 * Encodes the a11y invariant the extracted primitive must satisfy: the donut
 * SVG advertises role="img" with an aria-label carrying the numeric summary
 * (T-38-A11Y), and it renders without throwing at the boundary fractions
 * (0% / 100%). Authored BEFORE ./DonutChart exists, so the import is
 * unresolved (RED); Task 2 creates the component and turns it GREEN.
 *
 * Mirrors the render-test + motion-proxy conventions in
 * SavedWorkflowsPage.test.tsx (motion/react stripped so role queries resolve).
 */

import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

// motion.circle carries animation props that jsdom cannot render; proxy each
// motion.* to its plain SVG/HTML tag so role/aria queries resolve unchanged.
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

import { DonutChart } from "./DonutChart";

describe("DonutChart — render + a11y", () => {
  it("exposes a role='img' element whose aria-label carries the numeric summary", () => {
    render(<DonutChart percent={87} ariaLabel="Success rate 87 percent" />);
    const img = screen.getByRole("img");
    expect(img).toBeInTheDocument();
    expect(img).toHaveAttribute("aria-label", expect.stringContaining("87"));
  });

  it("does not throw at the 0% boundary fraction", () => {
    expect(() =>
      render(<DonutChart percent={0} ariaLabel="Success rate 0 percent" />),
    ).not.toThrow();
    expect(screen.getByRole("img")).toHaveAttribute(
      "aria-label",
      expect.stringContaining("0"),
    );
  });

  it("does not throw at the 100% boundary fraction", () => {
    expect(() =>
      render(<DonutChart percent={100} ariaLabel="Success rate 100 percent" />),
    ).not.toThrow();
    expect(screen.getByRole("img")).toHaveAttribute(
      "aria-label",
      expect.stringContaining("100"),
    );
  });
});
