import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Button } from "../Button";
import { Card } from "../Card";
import { Pill } from "../Pill";

// Retired palette that must NEVER appear in a primitive's rendered output —
// primitives derive from the plan-01 token layer, not hardcoded hex (SC-1, D-15).
const RETIRED_HEX = /#1B2A4A|#2563eb/i;

describe("Button primitive", () => {
  it("renders primary variant with brand fill token class", () => {
    render(<Button variant="primary">Go</Button>);
    const btn = screen.getByRole("button", { name: "Go" });
    expect(btn.className).toContain("bg-brand");
    expect(btn.className).toContain("rounded-[var(--radius-button)]");
    expect(btn.className).toContain("font-semibold");
  });

  it("renders secondary variant with distinct surface + line token classes", () => {
    render(<Button variant="secondary">Cancel</Button>);
    const btn = screen.getByRole("button", { name: "Cancel" });
    expect(btn.className).toContain("bg-surface-card");
    expect(btn.className).toContain("border-line-control");
    expect(btn.className).toContain("text-ink-900");
  });

  it("primary and secondary render different token classes", () => {
    const { container: primary } = render(<Button variant="primary">A</Button>);
    const { container: secondary } = render(<Button variant="secondary">B</Button>);
    const pClass = primary.querySelector("button")!.className;
    const sClass = secondary.querySelector("button")!.className;
    expect(pClass).not.toEqual(sClass);
  });

  it("defaults to the primary variant", () => {
    render(<Button>Default</Button>);
    const btn = screen.getByRole("button", { name: "Default" });
    expect(btn.className).toContain("bg-brand");
  });

  it("passes through onClick, disabled and data-testid", () => {
    const onClick = vi.fn();
    render(
      <Button onClick={onClick} disabled data-testid="submit-btn">
        Submit
      </Button>,
    );
    const btn = screen.getByTestId("submit-btn");
    expect(btn).toBeDisabled();
    fireEvent.click(btn);
    // disabled button does not fire click
    expect(onClick).not.toHaveBeenCalled();
  });

  it("fires onClick when enabled", () => {
    const onClick = vi.fn();
    render(
      <Button onClick={onClick} data-testid="live-btn">
        Click
      </Button>,
    );
    fireEvent.click(screen.getByTestId("live-btn"));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("merges a caller className", () => {
    render(<Button className="w-full">Wide</Button>);
    expect(screen.getByRole("button", { name: "Wide" }).className).toContain("w-full");
  });

  it("contains no retired palette hex in rendered output", () => {
    const { container } = render(
      <>
        <Button variant="primary">P</Button>
        <Button variant="secondary">S</Button>
      </>,
    );
    expect(container.innerHTML).not.toMatch(RETIRED_HEX);
  });
});

describe("Card primitive", () => {
  it("renders a card surface with token surface, line and radius classes", () => {
    const { container } = render(<Card>content</Card>);
    const card = container.firstElementChild as HTMLElement;
    expect(card.className).toContain("bg-surface-card");
    expect(card.className).toContain("border-line-border");
    expect(card.className).toContain("rounded-[var(--radius-card)]");
  });

  it("forwards children and className", () => {
    const { container } = render(<Card className="p-6">hi there</Card>);
    const card = container.firstElementChild as HTMLElement;
    expect(card.className).toContain("p-6");
    expect(card.textContent).toBe("hi there");
  });

  it("contains no retired palette hex in rendered output", () => {
    const { container } = render(<Card>x</Card>);
    expect(container.innerHTML).not.toMatch(RETIRED_HEX);
  });
});

describe("Pill primitive", () => {
  it("renders with pill radius and line-control border token classes", () => {
    const { container } = render(<Pill>tag</Pill>);
    const pill = container.firstElementChild as HTMLElement;
    expect(pill.className).toContain("rounded-[var(--radius-pill)]");
    expect(pill.className).toContain("border-line-control");
  });

  it("forwards children and className", () => {
    const { container } = render(<Pill className="ml-2">chip</Pill>);
    const pill = container.firstElementChild as HTMLElement;
    expect(pill.className).toContain("ml-2");
    expect(pill.textContent).toBe("chip");
  });

  it("contains no retired palette hex in rendered output", () => {
    const { container } = render(<Pill>y</Pill>);
    expect(container.innerHTML).not.toMatch(RETIRED_HEX);
  });
});
