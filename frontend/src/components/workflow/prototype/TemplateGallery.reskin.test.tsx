import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import type { PrototypeTemplate } from "@/lib/prototype-api";

// ─────────────────────────────────────────────────────────────────
// Reskin parity + a11y contract for the template picker (plan 35-03).
//
// The picker is ALREADY richer than the mock (real search, real category
// filtering, a real detail modal, and real onSelect wiring). This test pins
// that wired behaviour through the token reskin so it can NEVER be downgraded
// to the mock's inert cards (D-15 keep-richer-behaviour):
//   1. Typing in the search box FILTERS the rendered template set (not inert).
//   2. Category tabs expose role=tab and switching a category re-filters.
//   3. A card click drives real onSelect (blank-canvas card + detail-modal
//      "Use this template").
//   4. No retired palette leaks into the rendered class strings.
// ─────────────────────────────────────────────────────────────────

// jsdom has no IntersectionObserver — CompactTemplateCard lazily mounts its
// preview iframe through one. Stub it so the cards render (name/label still
// render outside the observer gate; the iframe simply never mounts).
class MockIO {
  observe() {}
  disconnect() {}
  unobserve() {}
  takeRecords() {
    return [];
  }
}
vi.stubGlobal("IntersectionObserver", MockIO as unknown as typeof IntersectionObserver);

import { TemplateGallery } from "./TemplateGallery";

function makeTemplate(partial: Partial<PrototypeTemplate> & { id: string; name: string }): PrototypeTemplate {
  return {
    description: "",
    mode: null,
    platform: null,
    scenario: null,
    triggers: [],
    craft_required: [],
    example_prompt: null,
    has_preview: true,
    ...partial,
  };
}

const TEMPLATES: PrototypeTemplate[] = [
  makeTemplate({ id: "alpha", name: "Alpha Dashboard", scenario: "design", description: "a design surface" }),
  makeTemplate({ id: "beta", name: "Beta Report", scenario: "marketing", description: "a marketing brief" }),
];

describe("TemplateGallery reskin — real search / filter / select preserved", () => {
  it("typing in the search box reduces the rendered template set (real filter)", () => {
    render(<TemplateGallery templates={TEMPLATES} selectedId={null} onSelect={vi.fn()} />);

    // Both built-ins render initially in the All tab.
    expect(screen.getByText("Alpha Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Beta Report")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText(/search templates/i), {
      target: { value: "Alpha" },
    });

    expect(screen.getByText("Alpha Dashboard")).toBeInTheDocument();
    expect(screen.queryByText("Beta Report")).not.toBeInTheDocument();
  });

  it("category tabs expose role=tab and switching a category re-filters the set", () => {
    render(<TemplateGallery templates={TEMPLATES} selectedId={null} onSelect={vi.fn()} />);

    const tabs = screen.getAllByRole("tab");
    // All + 6 buckets + Custom = 8 category tabs.
    expect(tabs.length).toBe(8);

    const marketingTab = tabs.find((t) => within(t).queryByText("Marketing"));
    expect(marketingTab).toBeTruthy();
    fireEvent.click(marketingTab!);

    // Marketing bucket -> only Beta (marketing) survives; Alpha (design) drops.
    expect(screen.getByText("Beta Report")).toBeInTheDocument();
    expect(screen.queryByText("Alpha Dashboard")).not.toBeInTheDocument();
  });

  it("clicking the blank-canvas card calls onSelect(null)", () => {
    const onSelect = vi.fn();
    render(<TemplateGallery templates={TEMPLATES} selectedId="alpha" onSelect={onSelect} />);

    fireEvent.click(screen.getByText("No template"));
    expect(onSelect).toHaveBeenCalledWith(null);
  });

  it("selecting a built-in via the detail modal calls onSelect with its id", () => {
    const onSelect = vi.fn();
    render(<TemplateGallery templates={TEMPLATES} selectedId={null} onSelect={onSelect} />);

    // Card click opens the detail modal (real, not inert).
    fireEvent.click(screen.getByText("Alpha Dashboard"));
    const dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByText(/use this template/i));

    expect(onSelect).toHaveBeenCalledWith("alpha");
  });

  it("renders no retired palette in the class strings", () => {
    const { container } = render(
      <TemplateGallery templates={TEMPLATES} selectedId={null} onSelect={vi.fn()} />,
    );
    const html = container.innerHTML;
    expect(html).not.toMatch(/#1B2A4A/);
    expect(html).not.toMatch(/\btext-gray-/);
    expect(html).not.toMatch(/\bbg-gray-/);
  });
});
