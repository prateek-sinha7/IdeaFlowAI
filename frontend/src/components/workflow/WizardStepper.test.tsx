import { describe, expect, it, vi } from "vitest";
import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import type { PrototypeTemplate } from "@/lib/prototype-api";
import type { PPTTemplate } from "@/lib/ppt-api";

// ─────────────────────────────────────────────────────────────────
// WizardStepper (plan 37-04) — the ONE genuine new component.
//
// The stepper is CHROME ONLY: it reuses the shipped gallery bodies
// (TemplateGallery for Web, PPTTemplateGallery for Deck) against the
// live registries, wires back/next navigation across three steps, and
// exposes typed render slots (dsSlot, discoverySlot) that plan 37-05
// injects WITHOUT editing the stepper. It is keyed on a GENERIC mode
// prop + toggle value — never a prototype/deck workflow-name branch
// (SC-001 / INV-1). This test pins:
//   1. The Web/Deck toggle swaps the template-step body between the two
//      reused galleries (not a rebuilt grid).
//   2. Back/next navigates Template -> Design System -> Discovery.
//   3. The injected dsSlot / discoverySlot render their content.
//   4. No retired palette leaks into the rendered class strings.
// ─────────────────────────────────────────────────────────────────

// jsdom has no IntersectionObserver — the gallery cards lazily mount their
// preview iframe through one. Stub it so the cards render.
class MockIO {
  observe() {}
  disconnect() {}
  unobserve() {}
  takeRecords() {
    return [];
  }
}
vi.stubGlobal("IntersectionObserver", MockIO as unknown as typeof IntersectionObserver);

import { WizardStepper, type WizardMode } from "./WizardStepper";

function makeWebTemplate(
  partial: Partial<PrototypeTemplate> & { id: string; name: string },
): PrototypeTemplate {
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

function makeDeckTemplate(
  partial: Partial<PPTTemplate> & { id: string; name: string },
): PPTTemplate {
  return {
    description: "",
    mode: null,
    platform: null,
    scenario: null,
    triggers: [],
    craft_required: [],
    example_prompt: null,
    has_preview: true,
    design_system: {},
    ...partial,
  };
}

const WEB_TEMPLATES: PrototypeTemplate[] = [
  makeWebTemplate({ id: "web-alpha", name: "Web Alpha Dashboard" }),
];
const DECK_TEMPLATES: PPTTemplate[] = [
  makeDeckTemplate({ id: "deck-beta", name: "Deck Beta Pitch" }),
];

function Harness() {
  const [mode, setMode] = useState<WizardMode>("web");
  return (
    <WizardStepper
      mode={mode}
      onModeChange={setMode}
      webTemplates={WEB_TEMPLATES}
      webSelectedId={null}
      onWebSelect={vi.fn()}
      deckTemplates={DECK_TEMPLATES}
      deckSelectedId={null}
      onDeckSelect={vi.fn()}
      dsSlot={<div>INJECTED DESIGN SYSTEM STEP</div>}
      discoverySlot={<div>INJECTED DISCOVERY STEP</div>}
    />
  );
}

describe("WizardStepper — toggle swaps reused galleries + slot nav", () => {
  it("Web/Deck toggle swaps the template-step body between the two reused galleries", () => {
    render(<Harness />);

    // Web mode (default): the web gallery body renders; the deck one does not.
    expect(screen.getByText("Web Alpha Dashboard")).toBeInTheDocument();
    expect(screen.queryByText("Deck Beta Pitch")).not.toBeInTheDocument();

    // Flip to Deck: the deck gallery swaps in, the web one drops out.
    fireEvent.click(screen.getByRole("button", { name: /deck/i }));
    expect(screen.getByText("Deck Beta Pitch")).toBeInTheDocument();
    expect(screen.queryByText("Web Alpha Dashboard")).not.toBeInTheDocument();
  });

  it("back/next navigates Template -> Design System -> Discovery over the injected slots", () => {
    render(<Harness />);

    // Step 1 — Template: gallery visible, slots not.
    expect(screen.getByText("Web Alpha Dashboard")).toBeInTheDocument();
    expect(screen.queryByText("INJECTED DESIGN SYSTEM STEP")).not.toBeInTheDocument();

    // Next -> Step 2 — Design System slot.
    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    expect(screen.getByText("INJECTED DESIGN SYSTEM STEP")).toBeInTheDocument();
    expect(screen.queryByText("Web Alpha Dashboard")).not.toBeInTheDocument();

    // Next -> Step 3 — Discovery slot.
    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    expect(screen.getByText("INJECTED DISCOVERY STEP")).toBeInTheDocument();
    expect(screen.queryByText("INJECTED DESIGN SYSTEM STEP")).not.toBeInTheDocument();

    // Back -> Step 2 again.
    fireEvent.click(screen.getByRole("button", { name: /back/i }));
    expect(screen.getByText("INJECTED DESIGN SYSTEM STEP")).toBeInTheDocument();
    expect(screen.queryByText("INJECTED DISCOVERY STEP")).not.toBeInTheDocument();
  });

  it("renders no retired palette in the class strings", () => {
    const { container } = render(<Harness />);
    const html = container.innerHTML;
    expect(html).not.toMatch(/#1B2A4A/);
    expect(html).not.toMatch(/#f5f5f0/);
    expect(html).not.toMatch(/Fraunces/i);
  });
});
