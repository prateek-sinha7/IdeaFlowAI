import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import type { DesignSystemListItem } from "@/lib/prototype-api";

// ─────────────────────────────────────────────────────────────────
// Reskin parity + LOCK-F contract for the design-system picker (plan 35-04).
//
// The picker is ALREADY richer than the mock (real search, real category
// grouping, a real detail modal, real onSelect wiring). This test pins that
// wired behaviour through the token reskin so it can never be downgraded:
//   1. LOCK-F — every count the picker shows is derived from the real
//      `systems` prop length (render N=14 → shows 14), NEVER a fabricated 150.
//   2. Typing in the search box FILTERS the rendered chip set (real filter).
//   3. Clicking a system chip opens the real detail modal whose "Use this
//      system" drives onSelect(id) (real select, not inert).
//   4. No retired / stray-stock palette leaks into the rendered class strings.
// ─────────────────────────────────────────────────────────────────

// The detail modal reads the auth token via `getToken()` (localStorage) on
// mount. jsdom in this suite has no functional localStorage — stub a minimal
// in-memory one so the real modal path (open → "Use this system" → onSelect)
// runs without throwing. Not a behaviour change; only an environment shim.
const memStore: Record<string, string> = {};
vi.stubGlobal("localStorage", {
  getItem: (k: string) => (k in memStore ? memStore[k] : null),
  setItem: (k: string, v: string) => { memStore[k] = String(v); },
  removeItem: (k: string) => { delete memStore[k]; },
  clear: () => { for (const k of Object.keys(memStore)) delete memStore[k]; },
  key: () => null,
  length: 0,
} as unknown as Storage);

import { DesignSystemPicker } from "./DesignSystemPicker";

function makeDS(partial: Partial<DesignSystemListItem> & { id: string; name: string }): DesignSystemListItem {
  return {
    category: "General",
    description: "",
    has_preview: false,
    ...partial,
  };
}

// A REAL-sized fixture (14 systems — the live catalogue is ~14). LOCK-F: the
// picker must report 14, proving the count follows the prop, not a hardcoded
// "150 systems".
const SYSTEMS: DesignSystemListItem[] = [
  makeDS({ id: "linear", name: "Linear", category: "Product", description: "crisp product ui" }),
  makeDS({ id: "stripe", name: "Stripe", category: "Product", description: "payments elegance" }),
  makeDS({ id: "vercel", name: "Vercel", category: "Product", description: "black + geist" }),
  makeDS({ id: "notion", name: "Notion", category: "Product", description: "soft docs" }),
  makeDS({ id: "material", name: "Material", category: "System", description: "google material" }),
  makeDS({ id: "carbon", name: "Carbon", category: "System", description: "ibm carbon" }),
  makeDS({ id: "fluent", name: "Fluent", category: "System", description: "microsoft fluent" }),
  makeDS({ id: "apple", name: "Apple HIG", category: "System", description: "human interface" }),
  makeDS({ id: "brutalist", name: "Brutalist", category: "Editorial", description: "raw type" }),
  makeDS({ id: "swiss", name: "Swiss", category: "Editorial", description: "grid + helvetica" }),
  makeDS({ id: "editorial", name: "Editorial", category: "Editorial", description: "magazine" }),
  makeDS({ id: "playful", name: "Playful", category: "Expressive", description: "bright + round" }),
  makeDS({ id: "neon", name: "Neon", category: "Expressive", description: "cyberpunk glow" }),
  makeDS({ id: "pastel", name: "Pastel", category: "Expressive", description: "muted calm" }),
];

describe("DesignSystemPicker reskin — LOCK-F real count + real search/select preserved", () => {
  it("LOCK-F: the footer count is derived from the real systems prop (14), never a fabricated 150", () => {
    const { container } = render(
      <DesignSystemPicker systems={SYSTEMS} selectedId={null} onSelect={vi.fn()} onSelectCustom={vi.fn()} />,
    );
    // The footer reflects the prop length exactly.
    expect(screen.getByText(/14 design systems/i)).toBeInTheDocument();
    // No catalogue-inflation string leaks anywhere.
    expect(container.innerHTML).not.toMatch(/150/);
  });

  it("typing in the search box reduces the rendered chip set (real filter)", () => {
    render(
      <DesignSystemPicker systems={SYSTEMS} selectedId={null} onSelect={vi.fn()} onSelectCustom={vi.fn()} />,
    );

    expect(screen.getByText("Linear")).toBeInTheDocument();
    expect(screen.getByText("Stripe")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText(/search by brand/i), {
      target: { value: "Linear" },
    });

    expect(screen.getByText("Linear")).toBeInTheDocument();
    expect(screen.queryByText("Stripe")).not.toBeInTheDocument();
  });

  it("clicking a system chip opens the detail modal whose Use-this-system calls onSelect(id)", () => {
    const onSelect = vi.fn();
    render(
      <DesignSystemPicker systems={SYSTEMS} selectedId={null} onSelect={onSelect} onSelectCustom={vi.fn()} />,
    );

    fireEvent.click(screen.getByText("Stripe"));
    const dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByText(/use this system/i));

    expect(onSelect).toHaveBeenCalledWith("stripe");
  });

  it("renders no retired / stray-stock palette in the class strings", () => {
    const { container } = render(
      <DesignSystemPicker systems={SYSTEMS} selectedId="linear" onSelect={vi.fn()} onSelectCustom={vi.fn()} />,
    );
    const html = container.innerHTML;
    expect(html).not.toMatch(/#1B2A4A/);
    expect(html).not.toMatch(/\btext-gray-/);
    expect(html).not.toMatch(/\bbg-gray-/);
    expect(html).not.toMatch(/\bborder-gray-/);
  });
});
