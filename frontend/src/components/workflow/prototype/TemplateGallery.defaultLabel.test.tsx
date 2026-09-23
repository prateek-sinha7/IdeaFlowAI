import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { PrototypeTemplate } from "@/lib/prototype-api";

// ISS-694 — the pre-selected blank-canvas card in the prototype wizard's
// template grid reads "No template", which describes the ABSENCE of a
// selection rather than "this is the default starting point" it actually is.
// Pins the correct copy so the fix can land and this test go green.

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

const TEMPLATES: PrototypeTemplate[] = [
  {
    id: "alpha",
    name: "Alpha Dashboard",
    description: "",
    mode: null,
    platform: null,
    scenario: "design",
    triggers: [],
    craft_required: [],
    example_prompt: null,
    has_preview: true,
    has_thumbnail: false,
  },
];

describe("TemplateGallery blank-canvas card label (ISS-694)", () => {
  it("labels the pre-selected default card 'Default Template', not 'No template'", () => {
    render(<TemplateGallery templates={TEMPLATES} selectedId={null} onSelect={vi.fn()} />);

    expect(screen.getByText("Default Template")).toBeInTheDocument();
    expect(screen.queryByText("No template")).not.toBeInTheDocument();
  });
});
